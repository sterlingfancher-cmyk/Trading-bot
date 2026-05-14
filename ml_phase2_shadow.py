"""ML Phase 2 shadow learning for the trading bot.

Shadow-only: logs/ranks opportunities, labels rows with paper-trade outcomes,
and never places trades or overrides live rules/risk controls.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sys
import threading
from typing import Any, Dict, List, Tuple

VERSION = "ml-phase2-shadow-2026-05-14"
PHASE = "phase_2_shadow_learning"
ENABLED = os.environ.get("ML2_SHADOW_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_OUTCOME_ROWS = int(os.environ.get("ML2_MIN_OUTCOME_ROWS_FOR_MODEL", "25"))
MAX_ROWS = int(os.environ.get("ML2_MAX_DATASET_ROWS", "6000"))
LIVE_DECIDER = False
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_LOCK = threading.RLock()
_PATCHING = False


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _hash(obj: Any) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        raw = str(obj)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _module() -> Any:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(mod: Any = None) -> str:
    try:
        return mod.today_key()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _nested(obj: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def _load_file() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            obj = json.load(handle)
        return obj if isinstance(obj, dict) else {}
    except BaseException:
        return {}


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else _load_file()
    except BaseException:
        state = _load_file()
    return (state if isinstance(state, dict) else {}), mod


def _ensure(state: Dict[str, Any]) -> Dict[str, Any]:
    ml2 = state.setdefault("ml_phase2", {})
    ml2.update({"version": VERSION, "phase": PHASE, "enabled": ENABLED, "live_trade_decider": False})
    ml2.setdefault("dataset", [])
    ml2.setdefault("model", {})
    ml2.setdefault("last_predictions", [])
    ml2.setdefault("notes", ["ML2 is shadow-only.", "Rules, stops, self-defense, and risk controls remain live authority."])
    return ml2


def _market(state: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(state.get("last_market") or _nested(state, "auto_runner", "last_result", default={}))


def _entry_floor(state: Dict[str, Any]) -> float:
    return _f(_nested(state, "feedback_loop", "dynamic_min_long_score"), _f(_nested(state, "explain", "current_permission", "active_min_entry_score"), 0.0))


def _candidate_items(state: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str]]:
    out: List[Tuple[Dict[str, Any], str]] = []
    for source in (_dict(state.get("scanner_audit")), _dict(state.get("scanner_log")), _market(state)):
        for key, decision in (("accepted_entries", "accepted"), ("entries", "accepted"), ("blocked_entries", "blocked"), ("rejected_signals", "rejected")):
            for item in _list(source.get(key)):
                if isinstance(item, dict):
                    out.append((item, decision))
        seen = {str(item.get("symbol") or item.get("ticker") or "").upper() for item, _ in out}
        for sym in _list(source.get("long_signals")):
            if isinstance(sym, str) and sym.upper() not in seen:
                out.append(({"symbol": sym, "side": "long"}, "signal"))
        for sym in _list(source.get("short_signals")):
            if isinstance(sym, str) and sym.upper() not in seen:
                out.append(({"symbol": sym, "side": "short"}, "signal"))
        if out:
            break
    positions = state.get("positions")
    if isinstance(positions, dict):
        for sym, pos in positions.items():
            if isinstance(pos, dict):
                item = dict(pos)
                item.setdefault("symbol", sym)
                out.append((item, "open_position"))
    return out


def _feature_row(item: Dict[str, Any], decision: str, state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    sym = str(item.get("symbol") or item.get("ticker") or "").upper()
    side = str(item.get("side") or item.get("direction") or "long").lower()
    bucket_map = getattr(mod, "SYMBOL_BUCKET", {}) if mod is not None else {}
    sector_map = getattr(mod, "SYMBOL_SECTOR", {}) if mod is not None else {}
    market = _market(state)
    feedback = _dict(state.get("feedback_loop"))
    risk = _dict(state.get("risk_controls"))
    perf = _dict(state.get("performance"))
    score = _f(item.get("score"), _f(_nested(item, "quality_info", "score"), 0.0))
    floor = _entry_floor(state)
    futures = _dict(market.get("futures_bias") or feedback.get("futures_bias") or state.get("futures_bias"))
    row = {
        "logged_local": _now(mod), "date": _today(mod), "symbol": sym, "side": side,
        "bucket": item.get("bucket") or (bucket_map.get(sym) if isinstance(bucket_map, dict) else None) or "unknown",
        "sector": item.get("sector") or (sector_map.get(sym) if isinstance(sector_map, dict) else None) or "unknown",
        "decision": decision, "rule_score": round(score, 6), "entry_floor": round(floor, 6), "score_edge": round(score - floor, 6),
        "reason": item.get("reason") or item.get("entry_block_reason") or _nested(item, "quality_info", "reason", default=""),
        "market_mode": market.get("market_mode") or state.get("market_mode"), "regime": market.get("regime") or state.get("regime"),
        "futures_action": futures.get("action") or futures.get("bias") or "",
        "self_defense_active": bool(risk.get("self_defense_active") or feedback.get("self_defense_mode")),
        "realized_pnl_today": round(_f(perf.get("realized_pnl_today"), 0.0), 2),
        "daily_loss_pct": round(_f(risk.get("daily_loss_pct"), 0.0), 5),
        "intraday_drawdown_pct": round(_f(risk.get("intraday_drawdown_pct"), 0.0), 5),
        "future_outcome_pending": True, "future_pnl_dollars": None, "future_pnl_pct": None, "future_win": None,
        "outcome_source": None, "source_hash": _hash(item),
    }
    row["row_id"] = _hash({"d": row["date"], "s": sym, "side": side, "decision": decision, "score": row["rule_score"], "src": row["source_hash"]})
    return row


def _legacy_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _list(_dict(state.get("ml_shadow")).get("feature_log")):
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        r = dict(row)
        r["symbol"] = str(r.get("symbol") or "").upper()
        r["rule_score"] = _f(r.get("rule_score"), _f(r.get("score"), 0.0))
        r["entry_floor"] = _f(r.get("entry_floor"), 0.0)
        r["score_edge"] = _f(r.get("score_edge"), r["rule_score"] - r["entry_floor"])
        r.setdefault("future_outcome_pending", True)
        r.setdefault("future_pnl_dollars", None)
        r.setdefault("future_pnl_pct", None)
        r.setdefault("future_win", None)
        r.setdefault("outcome_source", None)
        r["row_id"] = str(r.get("row_id") or _hash(r))
        r["source_phase"] = r.get("source_phase") or "ml_phase1_migrated"
        rows.append(r)
    return rows


def _trade_stats(state: Dict[str, Any]) -> Tuple[int, Dict[Tuple[str, str], Dict[str, Any]]]:
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    outcome_count = 0
    for trade in _list(state.get("trades")):
        if not isinstance(trade, dict):
            continue
        action = str(trade.get("action") or trade.get("type") or "").lower()
        reason = str(trade.get("exit_reason") or trade.get("reason") or "").lower()
        is_exit = action in {"exit", "sell", "close"} or "exit" in reason or "stop" in reason or trade.get("pnl_dollars") is not None or trade.get("pnl_pct") is not None
        sym = str(trade.get("symbol") or trade.get("ticker") or "").upper()
        if not is_exit or not sym:
            continue
        outcome_count += 1
        side = str(trade.get("side") or "long").lower()
        key = (sym, side)
        pnl_dollars = _f(trade.get("pnl_dollars"), 0.0)
        pnl_pct = _f(trade.get("pnl_pct"), 0.0)
        g = grouped.setdefault(key, {"count": 0, "wins": 0, "pnl_dollars": 0.0, "pnl_pct": 0.0, "last_reason": None})
        g["count"] += 1; g["wins"] += 1 if (pnl_dollars > 0 or pnl_pct > 0) else 0
        g["pnl_dollars"] += pnl_dollars; g["pnl_pct"] += pnl_pct; g["last_reason"] = trade.get("exit_reason") or trade.get("reason")
    for g in grouped.values():
        n = max(1, _i(g.get("count"), 1))
        g["win_rate"] = round(g["wins"] / n, 4)
        g["avg_pnl_dollars"] = round(g["pnl_dollars"] / n, 4)
        g["avg_pnl_pct"] = round(g["pnl_pct"] / n, 4)
    return outcome_count, grouped


def _merge_rows(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for row in group:
            if isinstance(row, dict):
                row_id = str(row.get("row_id") or _hash(row)); row["row_id"] = row_id; by_id[row_id] = row
    rows = list(by_id.values()); rows.sort(key=lambda r: str(r.get("logged_local") or r.get("date") or ""))
    return rows[-MAX_ROWS:]


def _label(rows: List[Dict[str, Any]], stats: Dict[Tuple[str, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    labeled = []
    for row in rows:
        r = dict(row); key = (str(r.get("symbol") or "").upper(), str(r.get("side") or "long").lower()); stat = stats.get(key)
        if stat:
            r.update({"future_outcome_pending": False, "future_pnl_dollars": stat.get("avg_pnl_dollars"), "future_pnl_pct": stat.get("avg_pnl_pct"), "future_win": bool(_f(stat.get("win_rate"), 0.0) >= 0.5), "outcome_source": "symbol_side_trade_outcome", "outcome_count": stat.get("count"), "last_exit_reason": stat.get("last_reason")})
        labeled.append(r)
    return labeled


def _group(rows: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("future_outcome_pending"):
            continue
        key = str(row.get(field) or "unknown"); g = out.setdefault(key, {"rows": 0, "wins": 0, "pnl_pct": 0.0})
        g["rows"] += 1; g["wins"] += 1 if row.get("future_win") else 0; g["pnl_pct"] += _f(row.get("future_pnl_pct"), 0.0)
    for g in out.values():
        n = max(1, _i(g.get("rows"), 1)); g["win_rate"] = round(g["wins"] / n, 4); g["avg_pnl_pct"] = round(g["pnl_pct"] / n, 4)
    return out


def _score_bucket(edge: float) -> str:
    return "strong_edge" if edge >= 0.010 else "positive_edge" if edge >= 0.003 else "near_floor" if edge >= -0.003 else "below_floor"


def _model(rows: List[Dict[str, Any]], outcome_count: int) -> Dict[str, Any]:
    labeled = []
    for row in rows:
        if not row.get("future_outcome_pending"):
            r = dict(row); r["score_bucket"] = _score_bucket(_f(r.get("score_edge"), 0.0)); labeled.append(r)
    wins = sum(1 for r in labeled if r.get("future_win")); n = len(labeled); baseline = wins / n if n else 0.50
    return {"version": VERSION, "training_mode": "shadow_heuristic_plus_outcome_labels", "live_trade_decider": False, "rows_total": len(rows), "labeled_outcome_rows": n, "trade_outcomes": outcome_count, "baseline_win_rate": round(baseline, 4), "readiness": "insufficient_outcomes" if n < MIN_OUTCOME_ROWS else "developing_shadow_model", "readiness_reason": f"Need {MIN_OUTCOME_ROWS}+ labeled outcome rows before ML can be considered for any weighting." if n < MIN_OUTCOME_ROWS else "Enough data for shadow diagnostics only; not live-authoritative.", "groups": {"bucket": _group(labeled, "bucket"), "sector": _group(labeled, "sector"), "decision": _group(labeled, "decision"), "score_bucket": _group(labeled, "score_bucket")}, "outcome_summary": {"wins": wins, "losses": max(0, n - wins), "avg_pnl_pct": round(sum(_f(r.get("future_pnl_pct"), 0.0) for r in labeled) / max(1, n), 4)}}


def _adj(groups: Dict[str, Any], field: str, key: str, baseline: float) -> float:
    g = _dict(_dict(groups.get(field)).get(str(key or "unknown")))
    return 0.0 if _i(g.get("rows"), 0) < 3 else max(-0.10, min(0.10, _f(g.get("win_rate"), baseline) - baseline))


def _predict(row: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
    baseline = _f(model.get("baseline_win_rate"), 0.50); groups = _dict(model.get("groups")); edge = _f(row.get("score_edge"), _f(row.get("rule_score"), 0.0) - _f(row.get("entry_floor"), 0.0))
    p = baseline + max(-0.08, min(0.10, edge * 5.0)) + 0.45 * _adj(groups, "bucket", row.get("bucket"), baseline) + 0.25 * _adj(groups, "sector", row.get("sector"), baseline) + 0.25 * _adj(groups, "decision", row.get("decision"), baseline) + 0.35 * _adj(groups, "score_bucket", _score_bucket(edge), baseline)
    if str(row.get("futures_action") or "") in {"gap_chase_protection", "bearish_caution", "risk_off"}: p -= 0.035
    if row.get("self_defense_active"): p -= 0.08
    if str(row.get("decision")) == "blocked": p -= 0.02
    labeled = _i(model.get("labeled_outcome_rows"), 0)
    confidence = "low_data_shadow" if labeled < MIN_OUTCOME_ROWS else "developing_shadow" if labeled < MIN_OUTCOME_ROWS * 3 else "usable_shadow_not_live"
    if labeled < MIN_OUTCOME_ROWS: p = 0.50 + (p - 0.50) * 0.35
    elif labeled < MIN_OUTCOME_ROWS * 3: p = 0.50 + (p - 0.50) * 0.65
    p = max(0.05, min(0.95, p))
    return {"symbol": row.get("symbol"), "side": row.get("side"), "bucket": row.get("bucket"), "sector": row.get("sector"), "decision_seen": row.get("decision"), "rule_score": row.get("rule_score"), "entry_floor": row.get("entry_floor"), "score_edge": round(edge, 6), "score_bucket": _score_bucket(edge), "ml2_shadow_probability": round(p, 4), "ml2_shadow_edge": round(p - 0.50, 4), "confidence": confidence, "shadow_action": "rank_higher" if p >= 0.57 else "rank_lower" if p <= 0.45 else "neutral", "live_trade_decider": False}


def _recommend(model: Dict[str, Any], predictions: List[Dict[str, Any]]) -> List[str]:
    actions = ["Keep ML2 shadow-only; do not let it place trades or override risk controls yet.", "Use /paper/self-check as the normal post-push test; use /paper/ml2-review only for deeper ML inspection."]
    if _i(model.get("labeled_outcome_rows"), 0) < MIN_OUTCOME_ROWS: actions.append(f"Collect more completed paper trades/opportunity rows; target at least {MIN_OUTCOME_ROWS} labeled outcomes before threshold tuning.")
    if predictions: actions.append("Compare ML2's top-ranked symbols against actual rule entries/exits over the next sessions before enabling any live weighting.")
    return actions


def _update(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if not ENABLED or not isinstance(state, dict): return state
    ml2 = _ensure(state); current = [_feature_row(item, decision, state, mod) for item, decision in _candidate_items(state)]; current = [r for r in current if r.get("symbol")]
    outcome_count, stats = _trade_stats(state); rows = _merge_rows([r for r in _list(ml2.get("dataset")) if isinstance(r, dict)], _legacy_rows(state), current); rows = _label(rows, stats); model = _model(rows, outcome_count)
    predictions = sorted([_predict(r, model) for r in current], key=lambda r: r.get("ml2_shadow_probability", 0.0), reverse=True)[:25]
    ml2.update({"version": VERSION, "phase": PHASE, "enabled": ENABLED, "live_trade_decider": False, "dataset": rows, "model": model, "last_predictions": predictions, "last_updated_local": _now(mod), "rows_total": len(rows), "labeled_outcome_rows": model.get("labeled_outcome_rows"), "trade_outcomes": model.get("trade_outcomes"), "readiness": model.get("readiness"), "recommended_actions": _recommend(model, predictions)})
    return state


def _status(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    ml2 = _ensure(state); model = _dict(ml2.get("model"))
    return {"status": "ok", "type": "ml_phase2_status", "version": VERSION, "phase": PHASE, "generated_local": _now(mod), "enabled": ENABLED, "live_trade_decider": False, "rows_total": ml2.get("rows_total", len(_list(ml2.get("dataset")))), "labeled_outcome_rows": ml2.get("labeled_outcome_rows", model.get("labeled_outcome_rows", 0)), "trade_outcomes": ml2.get("trade_outcomes", model.get("trade_outcomes", 0)), "readiness": ml2.get("readiness", model.get("readiness")), "readiness_reason": model.get("readiness_reason"), "baseline_win_rate": model.get("baseline_win_rate"), "latest_predictions_count": len(_list(ml2.get("last_predictions"))), "top_shadow_predictions": _list(ml2.get("last_predictions"))[:10], "recommended_actions": ml2.get("recommended_actions") or _recommend(model, _list(ml2.get("last_predictions"))), "state_file": STATE_FILE}


def _patch_save_state(mod: Any = None) -> bool:
    global _PATCHING
    mod = mod or _module()
    if mod is None or not hasattr(mod, "save_state") or id(mod) in PATCHED_MODULE_IDS: return False
    original = mod.save_state
    def patched_save_state(state):
        global _PATCHING
        if _PATCHING: return original(state)
        try:
            with _LOCK:
                _PATCHING = True; _update(state, mod)
        except BaseException as exc:
            try: _ensure(state)["last_error"] = str(exc)
            except BaseException: pass
        finally:
            _PATCHING = False
        return original(state)
    patched_save_state._ml2_phase2_patched = True
    mod.save_state = patched_save_state; PATCHED_MODULE_IDS.add(id(mod)); return True


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None: return {"status": "error", "version": VERSION, "error": "flask_app missing"}
    if id(flask_app) in REGISTERED_APP_IDS: _patch_save_state(module); return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify, request
    try: existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except BaseException: existing = set()
    module = module or _module(); _patch_save_state(module)
    if "/paper/ml2-status" not in existing:
        def ml2_status():
            state, mod = _load_state(module); _update(state, mod); _patch_save_state(mod); return jsonify(_status(state, mod))
        flask_app.add_url_rule("/paper/ml2-status", "paper_ml2_status", ml2_status)
    if "/paper/ml2-review" not in existing:
        def ml2_review():
            state, mod = _load_state(module); _update(state, mod); ml2 = _ensure(state); return jsonify({"status": "ok", "type": "ml_phase2_review", "version": VERSION, "generated_local": _now(mod), "ml_phase2": {"enabled": ml2.get("enabled"), "live_trade_decider": False, "rows_total": ml2.get("rows_total"), "labeled_outcome_rows": ml2.get("labeled_outcome_rows"), "trade_outcomes": ml2.get("trade_outcomes"), "model": ml2.get("model"), "last_predictions": ml2.get("last_predictions"), "recommended_actions": ml2.get("recommended_actions")}})
        flask_app.add_url_rule("/paper/ml2-review", "paper_ml2_review", ml2_review)
    if "/paper/ml2-predictions" not in existing:
        def ml2_predictions():
            state, mod = _load_state(module); _update(state, mod); ml2 = _ensure(state); return jsonify({"status": "ok", "type": "ml_phase2_predictions", "version": VERSION, "generated_local": _now(mod), "mode": "shadow_only", "live_trade_decider": False, "predictions": _list(ml2.get("last_predictions")), "readiness": ml2.get("readiness")})
        flask_app.add_url_rule("/paper/ml2-predictions", "paper_ml2_predictions", ml2_predictions)
    if "/paper/ml2-dataset" not in existing:
        def ml2_dataset():
            state, mod = _load_state(module); _update(state, mod); ml2 = _ensure(state)
            try: limit = max(1, min(int(request.args.get("limit", "250")), 1000))
            except BaseException: limit = 250
            rows = _list(ml2.get("dataset")); return jsonify({"status": "ok", "type": "ml_phase2_dataset", "version": VERSION, "generated_local": _now(mod), "rows_total": len(rows), "rows_returned": min(limit, len(rows)), "dataset_tail": rows[-limit:]})
        flask_app.add_url_rule("/paper/ml2-dataset", "paper_ml2_dataset", ml2_dataset)
    REGISTERED_APP_IDS.add(id(flask_app)); return {"status": "ok", "version": VERSION, "phase": PHASE, "routes": ["/paper/ml2-status", "/paper/ml2-review", "/paper/ml2-predictions", "/paper/ml2-dataset"], "live_trade_decider": False}


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module(); patched = _patch_save_state(module); flask_app = getattr(module, "app", None) if module is not None else None; routes = register_routes(flask_app, module) if flask_app is not None else {"status": "skipped", "reason": "flask_app_not_found_yet"}
    return {"status": "ok", "version": VERSION, "phase": PHASE, "enabled": ENABLED, "live_trade_decider": False, "save_state_patched": patched or (id(module) in PATCHED_MODULE_IDS if module is not None else False), "route_status": routes}
