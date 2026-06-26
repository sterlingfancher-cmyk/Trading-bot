"""ML-vs-rules shadow comparison log.

Advisory telemetry only. This module records cases where ML2 shadow rankings
preferred a current candidate that rules blocked or rejected, then labels those
comparison events from later realized outcomes when available.

It does not patch trade functions, place trades, change sizing, override risk,
or grant ML authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sys
import threading
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "ml-vs-rules-shadow-log-2026-06-26-v1"
PHASE = "phase_2_5_ml_vs_rules_shadow_evidence"
ENABLED = os.environ.get("ML_VS_RULES_SHADOW_LOG_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_ML_PROBABILITY = float(os.environ.get("ML_VS_RULES_MIN_PROBABILITY", "0.60"))
MIN_ML_EDGE = float(os.environ.get("ML_VS_RULES_MIN_EDGE", "0.08"))
MAX_EVENTS = int(os.environ.get("ML_VS_RULES_MAX_EVENTS", "1000"))
MAX_NEW_EVENTS_PER_SAVE = int(os.environ.get("ML_VS_RULES_MAX_NEW_EVENTS_PER_SAVE", "25"))
SCORECARD_MIN_ROWS = int(os.environ.get("ML_VS_RULES_SCORECARD_MIN_ROWS", "3"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_LOCK = threading.RLock()
_PATCHING = False


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return str(mod.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(mod: Any = None) -> str:
    try:
        return str(mod.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any | None]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return state if isinstance(state, dict) else {}, mod


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        v = float(value)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower().strip() or "long"


def _hash(obj: Any) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        raw = str(obj)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _event_date(row: Dict[str, Any]) -> str:
    for key in ("event_date", "date", "local_date", "day"):
        if row.get(key):
            return str(row.get(key))[:10]
    return ""


def _trade_date(row: Dict[str, Any]) -> str:
    for key in ("date", "local_date", "day"):
        if row.get(key):
            return str(row.get(key))[:10]
    for key in ("exit_time", "entry_time", "time", "timestamp", "ts"):
        if row.get(key) is not None:
            try:
                return dt.datetime.fromtimestamp(float(row.get(key))).strftime("%Y-%m-%d")
            except Exception:
                pass
    return ""


def _trades(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in _l(state.get("trades")) if isinstance(r, dict)]


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _trades(state):
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        has_pnl = row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None or row.get("pnl") is not None
        if action in {"exit", "sell", "close"} or "exit" in reason or "stop" in reason or has_pnl:
            rows.append(row)
    return rows


def _pnl_dollars(row: Dict[str, Any]) -> float:
    return _f(row.get("pnl_dollars"), _f(row.get("pnl"), 0.0))


def _pnl_pct(row: Dict[str, Any]) -> float:
    return _f(row.get("pnl_pct"), 0.0)


def _quality_reason(row: Dict[str, Any]) -> str:
    if row.get("reason"):
        return str(row.get("reason"))
    quality = _d(row.get("quality_info"))
    if quality.get("reason"):
        return str(quality.get("reason"))
    valve = _d(row.get("participation_valve"))
    if valve.get("quality_reason"):
        return str(valve.get("quality_reason"))
    return "unknown"


def _ml_predictions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = [r for r in _l(_d(state.get("ml_phase2")).get("last_predictions")) if isinstance(r, dict)]
    rows.sort(key=lambda r: _f(r.get("ml2_shadow_probability"), 0.0), reverse=True)
    return rows


def _prediction_index(state: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rank, row in enumerate(_ml_predictions(state), start=1):
        symbol = _symbol(row)
        side = _side(row)
        if not symbol:
            continue
        key = (symbol, side)
        current = out.get(key)
        if current is None or _f(row.get("ml2_shadow_probability"), 0.0) > _f(current.get("ml2_shadow_probability"), 0.0):
            item = dict(row)
            item["ml_rank"] = rank
            out[key] = item
    return out


def _current_rule_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    scanner = _d(state.get("scanner_audit"))
    core = _d(state.get("core_entry_pipeline"))
    for key, decision in (("blocked_entries", "blocked"), ("rejected_signals", "rejected"), ("accepted_entries", "accepted")):
        for row in _l(scanner.get(key)):
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault("rule_decision", decision)
                item.setdefault("source", "scanner_audit")
                rows.append(item)
    for row in _l(core.get("top_candidates")):
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("rule_decision", "top_candidate")
            item.setdefault("source", "core_entry_pipeline")
            rows.append(item)
    for row in _l(core.get("participation_valve_attempts")):
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("rule_decision", "participation_valve_review")
            item.setdefault("source", "core_entry_pipeline")
            rows.append(item)
    return [r for r in rows if _symbol(r)]


def _is_rule_blocked(row: Dict[str, Any]) -> bool:
    decision = str(row.get("rule_decision") or row.get("decision") or "").lower()
    reason = str(row.get("reason") or _quality_reason(row) or "").lower()
    return decision in {"blocked", "rejected", "participation_valve_review"} or "block" in reason or "rejected" in reason


def _ml_prefers(prediction: Dict[str, Any]) -> bool:
    prob = _f(prediction.get("ml2_shadow_probability"), 0.0)
    edge = _f(prediction.get("ml2_shadow_edge"), prob - 0.50)
    action = str(prediction.get("shadow_action") or "").lower()
    return prob >= MIN_ML_PROBABILITY or edge >= MIN_ML_EDGE or action == "rank_higher"


def _build_new_events(state: Dict[str, Any], mod: Any = None) -> List[Dict[str, Any]]:
    prediction_by_key = _prediction_index(state)
    today = _today(mod)
    generated = _now(mod)
    events: List[Dict[str, Any]] = []
    for row in _current_rule_rows(state):
        symbol = _symbol(row)
        side = _side(row)
        pred = prediction_by_key.get((symbol, side))
        if not pred or not _is_rule_blocked(row) or not _ml_prefers(pred):
            continue
        event = {
            "version": VERSION,
            "event_date": today,
            "event_local": generated,
            "symbol": symbol,
            "side": side,
            "rule_decision": row.get("rule_decision") or row.get("decision") or "blocked",
            "rule_reason": _quality_reason(row),
            "rule_score": row.get("score") or row.get("rule_score"),
            "rank_score": row.get("rank_score") or row.get("core_entry_rank_score"),
            "source": row.get("source") or "state_snapshot",
            "ml_rank": pred.get("ml_rank"),
            "ml_probability": pred.get("ml2_shadow_probability"),
            "ml_edge": pred.get("ml2_shadow_edge"),
            "ml_shadow_action": pred.get("shadow_action"),
            "ml_confidence": pred.get("confidence"),
            "bucket": row.get("bucket") or pred.get("bucket"),
            "sector": row.get("sector") or pred.get("sector"),
            "regime": pred.get("regime") or row.get("regime"),
            "outcome_pending": True,
            "outcome_source": None,
            "future_pnl_dollars": None,
            "future_pnl_pct": None,
            "future_win": None,
        }
        event["event_id"] = _hash({
            "date": event.get("event_date"),
            "symbol": symbol,
            "side": side,
            "rule_reason": event.get("rule_reason"),
            "ml_probability": round(_f(event.get("ml_probability")), 4),
            "source": event.get("source"),
        })
        events.append(event)
        if len(events) >= MAX_NEW_EVENTS_PER_SAVE:
            break
    return events


def _matching_outcomes(state: Dict[str, Any], event: Dict[str, Any]) -> List[Dict[str, Any]]:
    symbol = _symbol(event)
    side = _side(event)
    event_date = _event_date(event)
    rows = []
    for trade in _exit_rows(state):
        if _symbol(trade) != symbol or _side(trade) != side:
            continue
        trade_date = _trade_date(trade)
        if event_date and trade_date and trade_date < event_date:
            continue
        rows.append(trade)
    rows.sort(key=lambda r: _trade_date(r))
    return rows


def _label_events(state: Dict[str, Any], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    labeled = []
    for event in events:
        item = dict(event)
        outcomes = _matching_outcomes(state, item)
        if outcomes:
            first = outcomes[0]
            item.update({
                "outcome_pending": False,
                "outcome_source": "later_symbol_side_realized_exit",
                "outcome_date": _trade_date(first),
                "future_pnl_dollars": round(_pnl_dollars(first), 4),
                "future_pnl_pct": round(_pnl_pct(first), 5),
                "future_win": bool(_pnl_dollars(first) > 0 or _pnl_pct(first) > 0),
                "matched_outcome_count": len(outcomes),
            })
        labeled.append(item)
    return labeled


def _merge_events(existing: List[Dict[str, Any]], new_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in existing + new_events:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("event_id") or _hash(row))
        row = dict(row)
        row["event_id"] = event_id
        old = by_id.get(event_id)
        if old is None or (old.get("outcome_pending") and not row.get("outcome_pending")):
            by_id[event_id] = row
    events = list(by_id.values())
    events.sort(key=lambda r: str(r.get("event_local") or r.get("event_date") or ""))
    return events[-MAX_EVENTS:]


def _event_metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [r for r in rows if isinstance(r, dict)]
    labeled = [r for r in rows if not r.get("outcome_pending")]
    wins = sum(1 for r in labeled if bool(r.get("future_win")))
    losses = max(0, len(labeled) - wins)
    avg_pnl = sum(_f(r.get("future_pnl_dollars"), 0.0) for r in labeled) / max(1, len(labeled))
    avg_pct = sum(_f(r.get("future_pnl_pct"), 0.0) for r in labeled) / max(1, len(labeled))
    return {
        "events": len(rows),
        "labeled_events": len(labeled),
        "pending_events": max(0, len(rows) - len(labeled)),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / max(1, len(labeled)), 4) if labeled else 0.0,
        "avg_pnl_dollars": round(avg_pnl, 4),
        "avg_pnl_pct": round(avg_pct, 5),
    }


def _scorecard(events: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        if event.get("outcome_pending"):
            continue
        key = str(event.get(field) or (event.get("symbol") if field == "symbol" else "unknown"))
        groups.setdefault(key, []).append(event)
    cards = []
    for key, rows in groups.items():
        metrics = _event_metrics(rows)
        cards.append({"name": key, **metrics, "usable": bool(metrics.get("labeled_events", 0) >= SCORECARD_MIN_ROWS)})
    cards.sort(key=lambda r: (_i(r.get("labeled_events")), _f(r.get("win_rate")), _f(r.get("avg_pnl_pct"))), reverse=True)
    return cards[:25]


def _summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        **_event_metrics(events),
        "scorecards": {
            "by_symbol": _scorecard(events, "symbol"),
            "by_bucket": _scorecard(events, "bucket"),
            "by_sector": _scorecard(events, "sector"),
            "by_regime": _scorecard(events, "regime"),
            "by_rule_reason": _scorecard(events, "rule_reason"),
        },
    }


def _ensure(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = state.setdefault("ml_vs_rules_shadow_log", {})
    section.setdefault("events", [])
    section.update({
        "version": VERSION,
        "phase": PHASE,
        "enabled": bool(ENABLED),
        "live_trade_decider": False,
        "ml_authority": "shadow_only",
        "policy": {
            "advisory_only": True,
            "patches_save_state_only": True,
            "does_not_patch_trade_functions": True,
            "does_not_place_trades": True,
            "does_not_change_sizing": True,
            "does_not_override_risk_controls": True,
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
        },
    })
    return section


def update_state(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if not ENABLED or not isinstance(state, dict):
        return state
    section = _ensure(state, mod)
    existing = [r for r in _l(section.get("events")) if isinstance(r, dict)]
    new_events = _build_new_events(state, mod)
    merged = _merge_events(existing, new_events)
    labeled = _label_events(state, merged)
    summary = _summary(labeled)
    section.update({
        "events": labeled,
        "summary": summary,
        "last_updated_local": _now(mod),
        "new_events_last_update": len(new_events),
        "thresholds": {"min_ml_probability": MIN_ML_PROBABILITY, "min_ml_edge": MIN_ML_EDGE, "max_events": MAX_EVENTS},
    })
    return state


def status_payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    update_state(state, mod)
    section = _ensure(state, mod)
    events = [r for r in _l(section.get("events")) if isinstance(r, dict)]
    summary = section.get("summary") if isinstance(section.get("summary"), dict) else _summary(events)
    return {
        "status": "ok",
        "type": "ml_vs_rules_shadow_log_status",
        "version": VERSION,
        "phase": PHASE,
        "generated_local": _now(mod),
        "enabled": bool(ENABLED),
        "live_trade_decider": False,
        "ml_authority": "shadow_only",
        "events_total": len(events),
        "events_tail": events[-20:],
        "summary": summary,
        "policy": section.get("policy"),
        "next_actions": [
            "Review labeled ML-preferred/rules-blocked events before changing weighting.",
            "Keep ML shadow-only until comparison events prove repeatable outperformance.",
            "Use the scorecard to identify which blocked reasons were actually costly versus protective.",
        ],
    }


def _patch_save_state(mod: Any = None) -> bool:
    global _PATCHING
    mod = mod or _module()
    if mod is None or not hasattr(mod, "save_state") or id(mod) in PATCHED_MODULE_IDS:
        return False
    original = mod.save_state
    def patched_save_state(state):
        global _PATCHING
        if _PATCHING:
            return original(state)
        try:
            with _LOCK:
                _PATCHING = True
                update_state(state, mod)
        except Exception as exc:
            try:
                state.setdefault("ml_vs_rules_shadow_log", {})["last_error"] = str(exc)
            except Exception:
                pass
        finally:
            _PATCHING = False
        return original(state)
    patched_save_state._ml_vs_rules_shadow_log_patched = True  # type: ignore[attr-defined]
    mod.save_state = patched_save_state
    PATCHED_MODULE_IDS.add(id(mod))
    return True


def apply(mod: Any = None) -> Dict[str, Any]:
    mod = mod or _module()
    patched = _patch_save_state(mod)
    return {"status": "ok", "version": VERSION, "enabled": bool(ENABLED), "save_state_patched": bool(patched or (id(mod) in PATCHED_MODULE_IDS if mod is not None else False)), "live_trade_decider": False, "ml_authority": "shadow_only"}


def apply_runtime_overrides(mod: Any = None) -> Dict[str, Any]:
    return apply(mod)


def register_routes(flask_app: Any, mod: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    mod = mod or _module()
    apply(mod)
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, module = _load_state(mod)
        return jsonify(status_payload(state, module))

    def events_route():
        state, module = _load_state(mod)
        payload = status_payload(state, module)
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 1000))
        except Exception:
            limit = 100
        events = _l(_d(state.get("ml_vs_rules_shadow_log")).get("events"))
        return jsonify({"status": "ok", "type": "ml_vs_rules_shadow_events", "version": VERSION, "generated_local": _now(module), "events_total": len(events), "events": events[-limit:], "summary": payload.get("summary")})

    def scorecard_route():
        state, module = _load_state(mod)
        payload = status_payload(state, module)
        return jsonify({"status": "ok", "type": "ml_vs_rules_shadow_scorecard", "version": VERSION, "generated_local": _now(module), "summary": payload.get("summary")})

    if "/paper/ml-vs-rules-shadow-status" not in existing:
        flask_app.add_url_rule("/paper/ml-vs-rules-shadow-status", "paper_ml_vs_rules_shadow_status", status_route)
    if "/paper/ml-vs-rules-events" not in existing:
        flask_app.add_url_rule("/paper/ml-vs-rules-events", "paper_ml_vs_rules_events", events_route)
    if "/paper/ml-vs-rules-scorecard" not in existing:
        flask_app.add_url_rule("/paper/ml-vs-rules-scorecard", "paper_ml_vs_rules_scorecard", scorecard_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/ml-vs-rules-shadow-status", "/paper/ml-vs-rules-events", "/paper/ml-vs-rules-scorecard"], "live_trade_decider": False}


try:
    apply(_module())
except Exception:
    pass
