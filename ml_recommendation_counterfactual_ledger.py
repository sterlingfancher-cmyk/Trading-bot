"""ML recommendation and counterfactual outcome ledger.

This module lets the shadow ML system make an independent recommendation for
every scored candidate while keeping the rules engine and all risk controls
authoritative for execution.

It records four decision classes:
- rules allow / ML recommends
- rules allow / ML opposes
- rules block / ML recommends
- rules block / ML opposes

Pending recommendations are labeled from subsequent market bars at 15 minutes,
60 minutes, end of session, and next-session close.  Executed outcomes remain
stronger evidence than counterfactual market-path labels.  Counterfactual labels
are admitted to the Phase-2 shadow model at a deliberately reduced weight and
never count toward execution/outcome promotion gates.

The module never places orders, patches entry/exit functions, changes sizing,
lowers thresholds, overrides a rule rejection, or grants live authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sys
import threading
import time
from typing import Any, Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo

VERSION = "ml-recommendation-counterfactual-ledger-2026-08-04-v1"
PHASE = "phase_2_5_rules_gated_ml_recommendation_evidence"
ENABLED = os.environ.get("ML_COUNTERFACTUAL_LEDGER_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
MIN_RECOMMEND_PROBABILITY = float(
    os.environ.get("ML_COUNTERFACTUAL_MIN_RECOMMEND_PROBABILITY", "0.57")
)
MAX_OPPOSE_PROBABILITY = float(
    os.environ.get("ML_COUNTERFACTUAL_MAX_OPPOSE_PROBABILITY", "0.45")
)
COUNTERFACTUAL_WEIGHT_60M = float(
    os.environ.get("ML_COUNTERFACTUAL_WEIGHT_60M", "0.20")
)
COUNTERFACTUAL_WEIGHT_EOD = float(
    os.environ.get("ML_COUNTERFACTUAL_WEIGHT_EOD", "0.35")
)
COUNTERFACTUAL_WEIGHT_NEXT_SESSION = float(
    os.environ.get("ML_COUNTERFACTUAL_WEIGHT_NEXT_SESSION", "0.45")
)
MAX_EVENTS = int(os.environ.get("ML_COUNTERFACTUAL_MAX_EVENTS", "3000"))
MAX_NEW_EVENTS_PER_CYCLE = int(
    os.environ.get("ML_COUNTERFACTUAL_MAX_NEW_EVENTS_PER_CYCLE", "40")
)
MAX_MARKET_DATA_SYMBOLS = int(
    os.environ.get("ML_COUNTERFACTUAL_MAX_MARKET_DATA_SYMBOLS", "30")
)
MARKET_DATA_INTERVAL_SECONDS = int(
    os.environ.get("ML_COUNTERFACTUAL_REFRESH_SECONDS", "300")
)
EVENT_RETENTION_DAYS = int(
    os.environ.get("ML_COUNTERFACTUAL_EVENT_RETENTION_DAYS", "20")
)
MARKET_TZ = ZoneInfo("America/New_York")

_LOCK = threading.RLock()
_PATCHING_STATE = False
_PATCHED_CORE_IDS: set[int] = set()
_PATCHED_ML2_IDS: set[int] = set()
REGISTERED_APP_IDS: set[int] = set()
WATCHDOG_CORE_IDS: set[int] = set()
_BOOTSTRAP_STARTED = False
_LAST: Dict[str, Any] = {}


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
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _hash(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:22]


def _module() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if (
            module is not None
            and getattr(module, "app", None) is not None
            and hasattr(module, "load_state")
        ):
            return module
    return None


def _now_epoch() -> float:
    return time.time()


def _now_text(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _symbol(row: Dict[str, Any]) -> str:
    raw = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
    clean = raw.replace(".", "").replace("-", "")
    return raw if raw and len(raw) <= 12 and clean.isalnum() else ""


def _side(row: Dict[str, Any]) -> str:
    side = str(row.get("side") or row.get("direction") or "long").lower().strip()
    return side if side in {"long", "short"} else "long"


def _event_dt(epoch: Any) -> dt.datetime:
    return dt.datetime.fromtimestamp(_f(epoch, _now_epoch()), tz=dt.timezone.utc)


def _state(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is not None:
        try:
            state = getattr(core, "portfolio", None)
            if isinstance(state, dict):
                return state
        except Exception:
            pass
        try:
            state = core.load_state()
            if isinstance(state, dict):
                return state
        except Exception:
            pass
    return {}


def _ensure(state: Dict[str, Any]) -> Dict[str, Any]:
    section = state.setdefault("ml_counterfactual_recommendation_ledger", {})
    if not isinstance(section, dict):
        section = {}
        state["ml_counterfactual_recommendation_ledger"] = section
    section.setdefault("events", [])
    section.setdefault("training_rows", [])
    section.update(
        {
            "version": VERSION,
            "phase": PHASE,
            "enabled": bool(ENABLED),
            "ml_authority": "shadow_recommendation_only",
            "execution_authority": False,
            "rules_remain_execution_gate": True,
            "live_trade_decider": False,
        }
    )
    return section


def _market(state: Dict[str, Any]) -> Dict[str, Any]:
    last_market = _d(state.get("last_market"))
    auto = _d(_d(state.get("auto_runner")).get("last_result"))
    out = dict(last_market)
    for key, value in auto.items():
        out.setdefault(key, value)
    return out


def _cycle_id(state: Dict[str, Any]) -> str:
    candidates = (
        _d(_d(state.get("auto_runner")).get("last_result")).get("cycle_id"),
        _d(state.get("cycle_completion_contract")).get("last_completed_cycle_id"),
        _d(state.get("shared_cycle_identity")).get("cycle_id"),
        _d(state.get("last_run_report")).get("cycle_id"),
    )
    for candidate in candidates:
        if candidate:
            return str(candidate)
    auto = _d(state.get("auto_runner"))
    stamp = auto.get("last_success") or auto.get("last_run") or auto.get(
        "last_successful_run_local"
    )
    return str(stamp or _today())


def _rule_reason(row: Dict[str, Any]) -> str:
    quality = _d(row.get("quality_info"))
    valve = _d(row.get("participation_valve"))
    return str(
        row.get("reason")
        or row.get("entry_block_reason")
        or row.get("quality_reason")
        or quality.get("reason")
        or valve.get("quality_reason")
        or "unknown"
    )


def _decision_allows(row: Dict[str, Any]) -> bool:
    decision = str(
        row.get("rule_decision") or row.get("decision") or row.get("status") or ""
    ).lower()
    if row.get("blocked") is True or row.get("eligible") is False:
        return False
    if decision in {"accepted", "allowed", "eligible", "entry", "entered", "approved"}:
        return True
    if decision in {
        "blocked",
        "rejected",
        "denied",
        "ineligible",
        "participation_valve_review",
    }:
        return False
    reason = _rule_reason(row).lower()
    if any(token in reason for token in ("block", "reject", "denied", "not_met")):
        return False
    return bool(row.get("eligible") is True or row.get("allowed") is True)


def _rule_rows(state: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    scanner = _d(state.get("scanner_audit"))
    core = _d(state.get("core_entry_pipeline"))
    decision_audit = _d(state.get("decision_audit"))
    sources = (
        (scanner, "scanner_audit"),
        (core, "core_entry_pipeline"),
        (decision_audit, "decision_audit"),
    )
    key_specs = (
        ("accepted_entries", "accepted"),
        ("entries", "accepted"),
        ("blocked_entries", "blocked"),
        ("rejected_signals", "rejected"),
        ("top_candidates", "candidate"),
        ("participation_valve_attempts", "participation_valve_review"),
        ("candidates", "candidate"),
    )
    for source, source_name in sources:
        for key, decision in key_specs:
            for raw in _l(source.get(key)):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                item.setdefault("rule_decision", decision)
                item.setdefault("source", source_name)
                rows.append(item)

    indexed: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        symbol = _symbol(row)
        if not symbol:
            continue
        key = (symbol, _side(row))
        current = indexed.get(key)
        if current is None:
            indexed[key] = row
            continue
        current_priority = (
            2 if _decision_allows(current) else 1,
            _f(current.get("score"), _f(current.get("rule_score"), 0.0)),
        )
        new_priority = (
            2 if _decision_allows(row) else 1,
            _f(row.get("score"), _f(row.get("rule_score"), 0.0)),
        )
        if new_priority > current_priority:
            indexed[key] = row
    return indexed


def _entry_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _l(state.get("trades")):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("type") or "").lower()
        if action in {"entry", "buy", "open"}:
            rows.append(row)
    return rows


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _l(state.get("trades")):
        if not isinstance(row, dict):
            continue
        text = " ".join(
            str(row.get(key) or "").lower()
            for key in ("action", "type", "reason", "exit_reason")
        )
        if (
            row.get("pnl_dollars") is not None
            or row.get("pnl_pct") is not None
            or any(token in text for token in ("exit", "sell", "close", "stop"))
        ):
            rows.append(row)
    return rows


def _trade_epoch(row: Dict[str, Any]) -> float | None:
    for key in ("time", "timestamp", "ts", "entry_time", "exit_time", "created_at"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            try:
                parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                return parsed.timestamp()
            except Exception:
                pass
    return None


def _price_from_rows(*rows: Dict[str, Any]) -> float | None:
    keys = (
        "price",
        "last_price",
        "current_price",
        "mark",
        "close",
        "entry",
        "entry_price",
        "signal_price",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            value = _f(row.get(key), 0.0)
            if value > 0:
                return value
    return None


def _risk_parameter(state: Dict[str, Any], row: Dict[str, Any], names: Iterable[str]) -> float | None:
    sources = (
        row,
        _d(row.get("quality_info")),
        _d(row.get("risk")),
        _d(state.get("risk_parameters")),
        _d(_d(state.get("auto_runner")).get("last_result")).get("risk_parameters", {}),
    )
    for source in sources:
        source = _d(source)
        for name in names:
            value = _f(source.get(name), 0.0)
            if value > 0:
                return value
    return None


def _recommendation(prediction: Dict[str, Any]) -> str:
    probability = _f(prediction.get("ml2_shadow_probability"), 0.50)
    action = str(prediction.get("shadow_action") or "").lower()
    if probability >= MIN_RECOMMEND_PROBABILITY or action == "rank_higher":
        return "recommend_enter"
    if probability <= MAX_OPPOSE_PROBABILITY or action == "rank_lower":
        return "recommend_avoid"
    return "neutral"


def _decision_class(rules_allow: bool | None, recommendation: str) -> str:
    rule = "rules_unknown" if rules_allow is None else "rules_allow" if rules_allow else "rules_block"
    ml = (
        "ml_recommends"
        if recommendation == "recommend_enter"
        else "ml_opposes"
        if recommendation == "recommend_avoid"
        else "ml_neutral"
    )
    return f"{rule}__{ml}"


def _match_execution(
    state: Dict[str, Any], symbol: str, side: str, event_epoch: float
) -> Dict[str, Any]:
    matching_entries = []
    for row in _entry_rows(state):
        if _symbol(row) != symbol or _side(row) != side:
            continue
        epoch = _trade_epoch(row)
        if epoch is None or epoch >= event_epoch - 120:
            matching_entries.append((epoch or event_epoch, row))
    matching_entries.sort(key=lambda item: item[0])
    entry = matching_entries[0][1] if matching_entries else None

    matching_exits = []
    for row in _exit_rows(state):
        if _symbol(row) != symbol or _side(row) != side:
            continue
        epoch = _trade_epoch(row)
        if epoch is None or epoch >= event_epoch:
            matching_exits.append((epoch or event_epoch, row))
    matching_exits.sort(key=lambda item: item[0])
    exit_row = matching_exits[0][1] if matching_exits else None

    result = {
        "executed": bool(entry),
        "execution_entry": dict(entry) if isinstance(entry, dict) else None,
        "realized_exit": dict(exit_row) if isinstance(exit_row, dict) else None,
        "actual_outcome_available": bool(exit_row),
    }
    if exit_row:
        pnl_pct = _f(exit_row.get("pnl_pct"), 0.0)
        pnl_dollars = _f(exit_row.get("pnl_dollars"), _f(exit_row.get("pnl"), 0.0))
        result.update(
            {
                "actual_pnl_pct": pnl_pct,
                "actual_pnl_dollars": pnl_dollars,
                "actual_win": bool(pnl_pct > 0 or pnl_dollars > 0),
                "actual_exit_reason": exit_row.get("exit_reason")
                or exit_row.get("reason"),
            }
        )
    return result


def capture_recommendations(
    state: Dict[str, Any], core: Any = None, now_epoch: float | None = None
) -> Dict[str, Any]:
    """Capture every current ML prediction and pair it with the rules decision."""
    if not ENABLED or not isinstance(state, dict):
        return state
    now_epoch = float(now_epoch if now_epoch is not None else _now_epoch())
    section = _ensure(state)
    predictions = [
        row
        for row in _l(_d(state.get("ml_phase2")).get("last_predictions"))
        if isinstance(row, dict) and _symbol(row)
    ]
    rules = _rule_rows(state)
    cycle_id = _cycle_id(state)
    market = _market(state)
    existing = {
        str(row.get("event_id")): row
        for row in _l(section.get("events"))
        if isinstance(row, dict) and row.get("event_id")
    }

    new_events: List[Dict[str, Any]] = []
    ranked_predictions = sorted(
        predictions,
        key=lambda row: _f(row.get("ml2_shadow_probability"), 0.0),
        reverse=True,
    )
    for rank, prediction in enumerate(
        ranked_predictions[:MAX_NEW_EVENTS_PER_CYCLE], start=1
    ):
        symbol = _symbol(prediction)
        side = _side(prediction)
        rule_row = rules.get((symbol, side), {})
        has_rule_row = bool(rule_row)
        rules_allow: bool | None = _decision_allows(rule_row) if has_rule_row else None
        recommendation = _recommendation(prediction)
        event_id = _hash(
            {
                "cycle_id": cycle_id,
                "symbol": symbol,
                "side": side,
                "recommendation": recommendation,
            }
        )
        if event_id in existing:
            event = existing[event_id]
            execution = _match_execution(state, symbol, side, _f(event.get("event_epoch"), now_epoch))
            event.update(execution)
            continue

        reference_price = _price_from_rows(prediction, rule_row)
        stop_loss = _risk_parameter(
            state,
            rule_row,
            ("stop_loss", "stop_loss_pct", "stop_pct", "configured_stop_loss_pct"),
        )
        profit_target = _risk_parameter(
            state,
            rule_row,
            ("take_profit", "take_profit_pct", "profit_target", "target_pct"),
        )
        execution = _match_execution(state, symbol, side, now_epoch)
        event = {
            "event_id": event_id,
            "version": VERSION,
            "cycle_id": cycle_id,
            "event_epoch": round(now_epoch, 3),
            "event_utc": _event_dt(now_epoch).isoformat(),
            "event_local": _now_text(core),
            "event_date": _today(core),
            "symbol": symbol,
            "side": side,
            "ml_rank": rank,
            "ml_recommendation": recommendation,
            "ml_probability": _f(prediction.get("ml2_shadow_probability"), 0.5),
            "ml_edge": _f(prediction.get("ml2_shadow_edge"), 0.0),
            "ml_confidence": prediction.get("confidence"),
            "ml_shadow_action": prediction.get("shadow_action"),
            "rule_decision_observed": rule_row.get("rule_decision")
            or rule_row.get("decision"),
            "rule_reason": _rule_reason(rule_row) if has_rule_row else "not_observed",
            "rule_score": rule_row.get("score")
            or rule_row.get("rule_score")
            or prediction.get("rule_score"),
            "rules_allow_execution": rules_allow,
            "decision_class": _decision_class(rules_allow, recommendation),
            "execution_eligible": bool(rules_allow is True),
            "execution_authority": "rules_only",
            "ml_execution_authority": False,
            "reference_price": reference_price,
            "reference_price_source": (
                "state_candidate_snapshot" if reference_price else "pending_market_bar"
            ),
            "stop_loss_pct": stop_loss,
            "profit_target_pct": profit_target,
            "market_mode": market.get("market_mode"),
            "regime": market.get("regime"),
            "bucket": prediction.get("bucket") or rule_row.get("bucket"),
            "sector": prediction.get("sector") or rule_row.get("sector"),
            "outcomes": {},
            "outcome_pending": True,
            "label_quality": "unlabeled",
            "training_eligible": False,
            "training_weight": 0.0,
            **execution,
        }
        existing[event_id] = event
        new_events.append(event)

    events = list(existing.values())
    cutoff = now_epoch - EVENT_RETENTION_DAYS * 86400
    events = [
        row
        for row in events
        if _f(row.get("event_epoch"), now_epoch) >= cutoff
        or not row.get("outcome_pending", True)
    ]
    events.sort(key=lambda row: _f(row.get("event_epoch"), 0.0))
    section["events"] = events[-MAX_EVENTS:]
    section["new_events_last_capture"] = len(new_events)
    section["last_capture_local"] = _now_text(core)
    section["last_cycle_id"] = cycle_id
    return state


def _normalize_epoch(value: Any) -> float | None:
    if isinstance(value, dt.datetime):
        current = value
        if current.tzinfo is None:
            current = current.replace(tzinfo=dt.timezone.utc)
        return current.timestamp()
    try:
        return float(value)
    except Exception:
        return None


def _bar_rows_from_frame(data: Any, symbol: str) -> List[Dict[str, Any]]:
    if data is None or not hasattr(data, "columns"):
        return []
    frame = data
    try:
        columns = frame.columns
        if getattr(columns, "nlevels", 1) > 1:
            level0 = {str(value).upper() for value in columns.get_level_values(0)}
            level1 = {str(value).upper() for value in columns.get_level_values(1)}
            if symbol.upper() in level0:
                frame = frame[symbol]
            elif symbol.upper() in level1:
                frame = frame.xs(symbol, axis=1, level=1)
    except Exception:
        pass

    rows: List[Dict[str, Any]] = []
    try:
        for index, raw in frame.iterrows():
            epoch = _normalize_epoch(index)
            if epoch is None:
                continue
            close = _f(raw.get("Close"), 0.0)
            high = _f(raw.get("High"), close)
            low = _f(raw.get("Low"), close)
            open_price = _f(raw.get("Open"), close)
            if close <= 0:
                continue
            rows.append(
                {
                    "epoch": epoch,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                }
            )
    except Exception:
        return []
    rows.sort(key=lambda row: row["epoch"])
    return rows


def _return_pct(reference: float, price: float, side: str) -> float:
    if reference <= 0 or price <= 0:
        return 0.0
    move = price / reference - 1.0
    return -move if side == "short" else move


def _first_bar_at_or_after(
    bars: List[Dict[str, Any]], epoch: float
) -> Dict[str, Any] | None:
    for bar in bars:
        if _f(bar.get("epoch"), 0.0) >= epoch:
            return bar
    return None


def _session_date(epoch: float) -> dt.date:
    return _event_dt(epoch).astimezone(MARKET_TZ).date()


def _session_bars(
    bars: List[Dict[str, Any]], session_date: dt.date
) -> List[Dict[str, Any]]:
    return [
        bar
        for bar in bars
        if _event_dt(_f(bar.get("epoch"), 0.0)).astimezone(MARKET_TZ).date()
        == session_date
    ]


def _path_metrics(
    bars: List[Dict[str, Any]], reference: float, side: str
) -> Dict[str, Any]:
    if not bars or reference <= 0:
        return {}
    high = max(_f(bar.get("high"), 0.0) for bar in bars)
    low = min(_f(bar.get("low"), reference) for bar in bars)
    if side == "short":
        mfe = _return_pct(reference, low, side)
        mae = _return_pct(reference, high, side)
    else:
        mfe = _return_pct(reference, high, side)
        mae = _return_pct(reference, low, side)
    return {
        "mfe_pct": round(mfe, 6),
        "mae_pct": round(mae, 6),
        "path_bar_count": len(bars),
    }


def _stop_target_sequence(
    bars: List[Dict[str, Any]],
    reference: float,
    side: str,
    stop_loss_pct: float | None,
    profit_target_pct: float | None,
) -> Dict[str, Any]:
    if reference <= 0 or not bars:
        return {"available": False}
    stop = abs(_f(stop_loss_pct, 0.0))
    target = abs(_f(profit_target_pct, 0.0))
    if stop <= 0 and target <= 0:
        return {"available": False}
    if side == "short":
        stop_price = reference * (1.0 + stop) if stop > 0 else None
        target_price = reference * (1.0 - target) if target > 0 else None
    else:
        stop_price = reference * (1.0 - stop) if stop > 0 else None
        target_price = reference * (1.0 + target) if target > 0 else None

    for bar in bars:
        high = _f(bar.get("high"), 0.0)
        low = _f(bar.get("low"), 0.0)
        stop_hit = (
            stop_price is not None
            and (high >= stop_price if side == "short" else low <= stop_price)
        )
        target_hit = (
            target_price is not None
            and (low <= target_price if side == "short" else high >= target_price)
        )
        if stop_hit and target_hit:
            return {
                "available": True,
                "first_hit": "ambiguous_same_bar",
                "hit_epoch": bar.get("epoch"),
                "stop_price": stop_price,
                "target_price": target_price,
            }
        if stop_hit:
            return {
                "available": True,
                "first_hit": "stop",
                "hit_epoch": bar.get("epoch"),
                "hypothetical_return_pct": round(-stop, 6),
                "stop_price": stop_price,
                "target_price": target_price,
            }
        if target_hit:
            return {
                "available": True,
                "first_hit": "target",
                "hit_epoch": bar.get("epoch"),
                "hypothetical_return_pct": round(target, 6),
                "stop_price": stop_price,
                "target_price": target_price,
            }
    return {
        "available": True,
        "first_hit": "neither",
        "stop_price": stop_price,
        "target_price": target_price,
    }


def apply_bars_to_event(
    event: Dict[str, Any],
    bars: List[Dict[str, Any]],
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    """Apply normalized market bars to one recommendation event."""
    item = dict(event)
    if not bars:
        return item
    now_epoch = float(now_epoch if now_epoch is not None else _now_epoch())
    event_epoch = _f(item.get("event_epoch"), now_epoch)
    side = str(item.get("side") or "long").lower()
    after = [bar for bar in bars if _f(bar.get("epoch"), 0.0) >= event_epoch]
    if not after:
        return item

    reference = _f(item.get("reference_price"), 0.0)
    if reference <= 0:
        reference = _f(after[0].get("close"), 0.0)
        item["reference_price"] = reference
        item["reference_price_source"] = "first_market_bar_at_or_after_recommendation"
    if reference <= 0:
        return item

    outcomes = dict(_d(item.get("outcomes")))
    horizons = (("15m", 15 * 60), ("60m", 60 * 60))
    for name, seconds in horizons:
        target = event_epoch + seconds
        if now_epoch < target:
            continue
        bar = _first_bar_at_or_after(after, target)
        if bar:
            outcomes[name] = {
                "price": round(_f(bar.get("close"), 0.0), 6),
                "return_pct": round(
                    _return_pct(reference, _f(bar.get("close"), 0.0), side), 6
                ),
                "bar_epoch": bar.get("epoch"),
            }

    event_date = _session_date(event_epoch)
    same_session = _session_bars(after, event_date)
    later_session_dates = sorted(
        {
            _session_date(_f(bar.get("epoch"), 0.0))
            for bar in after
            if _session_date(_f(bar.get("epoch"), 0.0)) > event_date
        }
    )
    current_et = _event_dt(now_epoch).astimezone(MARKET_TZ)
    same_session_complete = bool(
        later_session_dates
        or current_et.date() > event_date
        or (
            current_et.date() == event_date
            and (current_et.hour > 16 or (current_et.hour == 16 and current_et.minute >= 5))
        )
    )
    if same_session and same_session_complete:
        bar = same_session[-1]
        outcomes["eod"] = {
            "price": round(_f(bar.get("close"), 0.0), 6),
            "return_pct": round(
                _return_pct(reference, _f(bar.get("close"), 0.0), side), 6
            ),
            "bar_epoch": bar.get("epoch"),
            "session_date": str(event_date),
        }

    if later_session_dates:
        next_date = later_session_dates[0]
        next_bars = _session_bars(after, next_date)
        next_complete = bool(
            len(later_session_dates) > 1
            or current_et.date() > next_date
            or (
                current_et.date() == next_date
                and (current_et.hour > 16 or (current_et.hour == 16 and current_et.minute >= 5))
            )
        )
        if next_bars and next_complete:
            bar = next_bars[-1]
            outcomes["next_session"] = {
                "price": round(_f(bar.get("close"), 0.0), 6),
                "return_pct": round(
                    _return_pct(reference, _f(bar.get("close"), 0.0), side), 6
                ),
                "bar_epoch": bar.get("epoch"),
                "session_date": str(next_date),
            }

    max_path_epoch = event_epoch + 2.5 * 86400
    path = [
        bar
        for bar in after
        if _f(bar.get("epoch"), 0.0) <= max_path_epoch
    ]
    outcomes.update(_path_metrics(path, reference, side))
    outcomes["stop_target_sequence"] = _stop_target_sequence(
        path,
        reference,
        side,
        item.get("stop_loss_pct"),
        item.get("profit_target_pct"),
    )
    item["outcomes"] = outcomes

    actual = bool(item.get("actual_outcome_available"))
    if actual:
        selected_return = _f(item.get("actual_pnl_pct"), 0.0)
        item.update(
            {
                "outcome_pending": False,
                "label_quality": "executed_realized_outcome",
                "training_label_horizon": "actual_exit",
                "training_return_pct": selected_return,
                "training_win": bool(item.get("actual_win")),
                "training_eligible": True,
                "training_weight": 1.0,
            }
        )
    else:
        selected_name = None
        selected_weight = 0.0
        for name, weight in (
            ("next_session", COUNTERFACTUAL_WEIGHT_NEXT_SESSION),
            ("eod", COUNTERFACTUAL_WEIGHT_EOD),
            ("60m", COUNTERFACTUAL_WEIGHT_60M),
        ):
            if isinstance(outcomes.get(name), dict):
                selected_name = name
                selected_weight = weight
                break
        if selected_name:
            selected_return = _f(_d(outcomes.get(selected_name)).get("return_pct"), 0.0)
            item.update(
                {
                    "outcome_pending": False,
                    "label_quality": "counterfactual_market_path",
                    "training_label_horizon": selected_name,
                    "training_return_pct": selected_return,
                    "training_win": bool(selected_return > 0),
                    "training_eligible": True,
                    "training_weight": selected_weight,
                }
            )
    item["last_market_label_update_utc"] = _event_dt(now_epoch).isoformat()
    return item


def _download_bars(symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    symbols = [symbol for symbol in symbols if symbol][:MAX_MARKET_DATA_SYMBOLS]
    if not symbols:
        return {}
    try:
        import yfinance as yf  # type: ignore

        query: Any = symbols[0] if len(symbols) == 1 else symbols
        data = yf.download(
            query,
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=False,
            threads=False,
            group_by="ticker",
        )
        return {symbol: _bar_rows_from_frame(data, symbol) for symbol in symbols}
    except Exception:
        return {}


def _refresh_execution_labels(state: Dict[str, Any]) -> None:
    section = _ensure(state)
    for event in _l(section.get("events")):
        if not isinstance(event, dict):
            continue
        execution = _match_execution(
            state,
            str(event.get("symbol") or ""),
            str(event.get("side") or "long"),
            _f(event.get("event_epoch"), 0.0),
        )
        event.update(execution)


def refresh_market_outcomes(
    state: Dict[str, Any],
    core: Any = None,
    bars_by_symbol: Dict[str, List[Dict[str, Any]]] | None = None,
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    if not ENABLED or not isinstance(state, dict):
        return state
    now_epoch = float(now_epoch if now_epoch is not None else _now_epoch())
    section = _ensure(state)
    _refresh_execution_labels(state)
    events = [row for row in _l(section.get("events")) if isinstance(row, dict)]
    pending_symbols: List[str] = []
    for event in events:
        if event.get("outcome_pending", True) or not _d(event.get("outcomes")).get(
            "next_session"
        ):
            symbol = str(event.get("symbol") or "")
            if symbol and symbol not in pending_symbols:
                pending_symbols.append(symbol)
    market_bars = bars_by_symbol if bars_by_symbol is not None else _download_bars(
        pending_symbols
    )
    updated = []
    for event in events:
        bars = market_bars.get(str(event.get("symbol") or ""), [])
        updated.append(apply_bars_to_event(event, bars, now_epoch=now_epoch))
    section["events"] = updated[-MAX_EVENTS:]
    section["last_market_refresh_local"] = _now_text(core)
    section["market_refresh_symbols"] = len(market_bars)
    _build_training_rows(state)
    return state


def _training_row(event: Dict[str, Any]) -> Dict[str, Any]:
    probability = _f(event.get("ml_probability"), 0.5)
    rule_score = _f(event.get("rule_score"), 0.0)
    row = {
        "row_id": "cf_" + str(event.get("event_id") or _hash(event)),
        "logged_local": event.get("event_local"),
        "date": event.get("event_date"),
        "symbol": event.get("symbol"),
        "side": event.get("side"),
        "bucket": event.get("bucket") or "unknown",
        "sector": event.get("sector") or "unknown",
        "decision": (
            "accepted"
            if event.get("rules_allow_execution") is True
            else "blocked"
            if event.get("rules_allow_execution") is False
            else "unknown"
        ),
        "rule_score": rule_score,
        "entry_floor": _f(event.get("entry_floor"), 0.0),
        "score_edge": _f(event.get("score_edge"), 0.0),
        "reason": event.get("rule_reason"),
        "market_mode": event.get("market_mode"),
        "regime": event.get("regime"),
        "future_outcome_pending": False,
        "future_pnl_dollars": event.get("actual_pnl_dollars"),
        "future_pnl_pct": _f(event.get("training_return_pct"), 0.0),
        "future_win": bool(event.get("training_win")),
        "outcome_source": event.get("label_quality"),
        "label_quality": event.get("label_quality"),
        "training_weight": _f(event.get("training_weight"), 0.0),
        "counterfactual": event.get("label_quality") == "counterfactual_market_path",
        "executed": bool(event.get("executed")),
        "ml_probability_at_recommendation": probability,
        "ml_edge_at_recommendation": _f(event.get("ml_edge"), probability - 0.5),
        "ml_recommendation": event.get("ml_recommendation"),
        "rules_allow_execution": event.get("rules_allow_execution"),
        "decision_class": event.get("decision_class"),
        "training_label_horizon": event.get("training_label_horizon"),
        "source_phase": PHASE,
        "source_event_id": event.get("event_id"),
    }
    return row


def _build_training_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    section = _ensure(state)
    rows = [
        _training_row(event)
        for event in _l(section.get("events"))
        if isinstance(event, dict)
        and event.get("training_eligible")
        and _f(event.get("training_weight"), 0.0) > 0
    ]
    by_id = {str(row.get("row_id")): row for row in rows}
    final = list(by_id.values())
    final.sort(key=lambda row: str(row.get("logged_local") or row.get("date") or ""))
    section["training_rows"] = final[-MAX_EVENTS:]
    section["training_summary"] = {
        "rows": len(final),
        "executed_realized_rows": sum(
            1 for row in final if row.get("label_quality") == "executed_realized_outcome"
        ),
        "counterfactual_rows": sum(
            1 for row in final if row.get("label_quality") == "counterfactual_market_path"
        ),
        "effective_weight": round(
            sum(_f(row.get("training_weight"), 0.0) for row in final), 4
        ),
    }
    return section["training_rows"]


def training_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(_build_training_rows(state))


def _weighted_group(rows: List[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("future_outcome_pending"):
            continue
        key = str(row.get(field) or "unknown")
        weight = max(0.0, _f(row.get("training_weight"), 1.0))
        group = groups.setdefault(
            key,
            {
                "rows": 0,
                "effective_rows": 0.0,
                "weighted_wins": 0.0,
                "weighted_pnl_pct": 0.0,
            },
        )
        group["rows"] += 1
        group["effective_rows"] += weight
        group["weighted_wins"] += weight if row.get("future_win") else 0.0
        group["weighted_pnl_pct"] += weight * _f(row.get("future_pnl_pct"), 0.0)
    for group in groups.values():
        denominator = max(1e-9, _f(group.get("effective_rows"), 0.0))
        group["win_rate"] = round(_f(group.get("weighted_wins"), 0.0) / denominator, 4)
        group["avg_pnl_pct"] = round(
            _f(group.get("weighted_pnl_pct"), 0.0) / denominator, 5
        )
        group["effective_rows"] = round(denominator, 4)
    return groups


def _patch_ml_phase2() -> Dict[str, Any]:
    try:
        import ml_phase2_shadow as ml2
    except Exception as exc:
        return {
            "patched": False,
            "reason": f"ml_phase2_import_failed:{type(exc).__name__}",
        }
    if id(ml2) in _PATCHED_ML2_IDS:
        return {"patched": True, "already_patched": True, "version": VERSION}

    original_update = getattr(ml2, "_update", None)
    original_adj = getattr(ml2, "_adj", None)
    if not callable(original_update) or not callable(original_adj):
        return {"patched": False, "reason": "ml_phase2_internal_functions_missing"}

    def weighted_group(rows: List[Dict[str, Any]], field: str):
        return _weighted_group(rows, field)

    def weighted_model(rows: List[Dict[str, Any]], outcome_count: int):
        labeled = [
            dict(row)
            for row in rows
            if isinstance(row, dict) and not row.get("future_outcome_pending")
        ]
        for row in labeled:
            row["score_bucket"] = ml2._score_bucket(
                _f(row.get("score_edge"), 0.0)
            )
            row.setdefault("training_weight", 1.0)
        weight_total = sum(
            max(0.0, _f(row.get("training_weight"), 1.0)) for row in labeled
        )
        weighted_wins = sum(
            max(0.0, _f(row.get("training_weight"), 1.0))
            for row in labeled
            if row.get("future_win")
        )
        baseline = weighted_wins / weight_total if weight_total > 0 else 0.50
        counterfactual = [
            row
            for row in labeled
            if row.get("label_quality") == "counterfactual_market_path"
            or row.get("counterfactual")
        ]
        strong = [row for row in labeled if row not in counterfactual]
        strong_count = len(strong)
        return {
            "version": getattr(ml2, "VERSION", VERSION),
            "training_mode": "weighted_executed_plus_counterfactual_shadow_labels",
            "live_trade_decider": False,
            "rows_total": len(rows),
            "labeled_outcome_rows": strong_count,
            "training_labeled_rows": len(labeled),
            "counterfactual_labeled_rows": len(counterfactual),
            "effective_training_rows": round(weight_total, 4),
            "trade_outcomes": outcome_count,
            "baseline_win_rate": round(baseline, 4),
            "readiness": (
                "insufficient_outcomes"
                if strong_count < getattr(ml2, "MIN_OUTCOME_ROWS", 25)
                else "developing_shadow_model"
            ),
            "readiness_reason": (
                f"Need {getattr(ml2, 'MIN_OUTCOME_ROWS', 25)}+ strong executed outcome rows "
                "before ML can be considered for any authority. Counterfactual rows improve "
                "shadow ranking but do not satisfy promotion gates."
                if strong_count < getattr(ml2, "MIN_OUTCOME_ROWS", 25)
                else "Enough strong data for shadow diagnostics only; counterfactual evidence remains discounted."
            ),
            "groups": {
                "bucket": _weighted_group(labeled, "bucket"),
                "sector": _weighted_group(labeled, "sector"),
                "decision": _weighted_group(labeled, "decision"),
                "score_bucket": _weighted_group(labeled, "score_bucket"),
                "decision_class": _weighted_group(labeled, "decision_class"),
                "ml_recommendation": _weighted_group(labeled, "ml_recommendation"),
            },
            "outcome_summary": {
                "weighted_wins": round(weighted_wins, 4),
                "weighted_losses": round(max(0.0, weight_total - weighted_wins), 4),
                "effective_rows": round(weight_total, 4),
                "strong_rows": strong_count,
                "counterfactual_rows": len(counterfactual),
                "avg_pnl_pct": round(
                    sum(
                        max(0.0, _f(row.get("training_weight"), 1.0))
                        * _f(row.get("future_pnl_pct"), 0.0)
                        for row in labeled
                    )
                    / max(1e-9, weight_total),
                    5,
                ),
            },
            "authority": {
                "counterfactual_rows_discounted": True,
                "counterfactual_rows_count_toward_promotion": False,
                "rules_remain_execution_gate": True,
                "live_trade_decider": False,
            },
        }

    def weighted_adj(groups: Dict[str, Any], field: str, key: str, baseline: float):
        group = _d(_d(groups.get(field)).get(str(key or "unknown")))
        effective_rows = _f(
            group.get("effective_rows"), _f(group.get("rows"), 0.0)
        )
        if effective_rows < 3.0:
            return 0.0
        return max(
            -0.10,
            min(0.10, _f(group.get("win_rate"), baseline) - baseline),
        )

    def patched_update(state: Dict[str, Any], mod: Any = None):
        if isinstance(state, dict):
            capture_recommendations(state, mod)
            rows = training_rows(state)
            ml_section = state.setdefault("ml_phase2", {})
            existing = [
                row for row in _l(_d(ml_section).get("dataset")) if isinstance(row, dict)
            ]
            by_id = {
                str(row.get("row_id") or _hash(row)): dict(row) for row in existing
            }
            for row in rows:
                by_id[str(row.get("row_id"))] = dict(row)
            ml_section["dataset"] = list(by_id.values())[-getattr(ml2, "MAX_ROWS", 6000):]
        result = original_update(state, mod)
        if isinstance(state, dict):
            capture_recommendations(state, mod)
            section = _ensure(state)
            model = _d(_d(state.get("ml_phase2")).get("model"))
            section["ml2_bridge"] = {
                "patched": True,
                "weighted_model_active": True,
                "strong_labeled_rows": model.get("labeled_outcome_rows"),
                "counterfactual_labeled_rows": model.get(
                    "counterfactual_labeled_rows"
                ),
                "effective_training_rows": model.get("effective_training_rows"),
                "promotion_gates_use_strong_rows_only": True,
                "updated_local": _now_text(mod),
            }
        return result

    weighted_group._ml_counterfactual_patch = VERSION  # type: ignore[attr-defined]
    weighted_model._ml_counterfactual_patch = VERSION  # type: ignore[attr-defined]
    weighted_adj._ml_counterfactual_patch = VERSION  # type: ignore[attr-defined]
    patched_update._ml_counterfactual_patch = VERSION  # type: ignore[attr-defined]
    patched_update.__wrapped__ = original_update

    ml2._group = weighted_group
    ml2._model = weighted_model
    ml2._adj = weighted_adj
    ml2._update = patched_update
    _PATCHED_ML2_IDS.add(id(ml2))
    return {
        "patched": True,
        "version": VERSION,
        "weighted_model_active": True,
        "counterfactual_rows_count_toward_promotion": False,
    }


def update_state(
    state: Dict[str, Any],
    core: Any = None,
    *,
    fetch_market_data: bool = False,
    bars_by_symbol: Dict[str, List[Dict[str, Any]]] | None = None,
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    if not ENABLED or not isinstance(state, dict):
        return state
    capture_recommendations(state, core, now_epoch=now_epoch)
    if fetch_market_data or bars_by_symbol is not None:
        refresh_market_outcomes(
            state,
            core,
            bars_by_symbol=bars_by_symbol,
            now_epoch=now_epoch,
        )
    else:
        _refresh_execution_labels(state)
        _build_training_rows(state)
    return state


def _patch_save_state(core: Any = None) -> bool:
    global _PATCHING_STATE
    core = core or _module()
    if core is None or not callable(getattr(core, "save_state", None)):
        return False
    if id(core) in _PATCHED_CORE_IDS:
        return True
    original = core.save_state

    def patched_save_state(state: Dict[str, Any]):
        global _PATCHING_STATE
        if _PATCHING_STATE:
            return original(state)
        try:
            with _LOCK:
                _PATCHING_STATE = True
                update_state(state, core, fetch_market_data=False)
        except Exception as exc:
            try:
                _ensure(state)["last_error"] = f"{type(exc).__name__}: {exc}"
            except Exception:
                pass
        finally:
            _PATCHING_STATE = False
        return original(state)

    patched_save_state._ml_counterfactual_ledger_patched = VERSION  # type: ignore[attr-defined]
    patched_save_state.__wrapped__ = original
    core.save_state = patched_save_state
    _PATCHED_CORE_IDS.add(id(core))
    return True


def _save_state(core: Any, state: Dict[str, Any]) -> None:
    try:
        core.save_state(state)
    except Exception:
        pass


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"started": False, "reason": "core_not_ready", "version": VERSION}
    if id(core) in WATCHDOG_CORE_IDS:
        return {"started": True, "already_started": True, "version": VERSION}
    WATCHDOG_CORE_IDS.add(id(core))

    def worker() -> None:
        while True:
            try:
                state = _state(core)
                if state:
                    with _LOCK:
                        update_state(state, core, fetch_market_data=True)
                    _save_state(core, state)
            except Exception as exc:
                try:
                    state = _state(core)
                    _ensure(state)["watchdog_error"] = f"{type(exc).__name__}: {exc}"
                    _save_state(core, state)
                except Exception:
                    pass
            time.sleep(max(60, MARKET_DATA_INTERVAL_SECONDS))

    thread = threading.Thread(
        target=worker,
        daemon=True,
        name="ml-counterfactual-outcome-ledger",
    )
    thread.start()
    return {
        "started": True,
        "version": VERSION,
        "thread_name": thread.name,
        "interval_seconds": max(60, MARKET_DATA_INTERVAL_SECONDS),
    }


def _summary(state: Dict[str, Any]) -> Dict[str, Any]:
    section = _ensure(state)
    events = [row for row in _l(section.get("events")) if isinstance(row, dict)]
    classes: Dict[str, int] = {}
    for event in events:
        key = str(event.get("decision_class") or "unknown")
        classes[key] = classes.get(key, 0) + 1
    return {
        "events": len(events),
        "pending": sum(1 for row in events if row.get("outcome_pending", True)),
        "labeled": sum(1 for row in events if not row.get("outcome_pending", True)),
        "executed": sum(1 for row in events if row.get("executed")),
        "executed_realized": sum(
            1
            for row in events
            if row.get("label_quality") == "executed_realized_outcome"
        ),
        "counterfactual_labeled": sum(
            1
            for row in events
            if row.get("label_quality") == "counterfactual_market_path"
        ),
        "decision_classes": classes,
        "training": section.get("training_summary"),
    }


def status_payload(state: Dict[str, Any] | None = None, core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    state = state if isinstance(state, dict) else _state(core)
    if isinstance(state, dict):
        update_state(state, core, fetch_market_data=False)
    section = _ensure(state)
    ml2_patch = _patch_ml_phase2()
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "ml_recommendation_counterfactual_ledger_status",
        "version": VERSION,
        "phase": PHASE,
        "generated_local": _now_text(core),
        "enabled": bool(ENABLED),
        "summary": _summary(state),
        "events_tail": _l(section.get("events"))[-20:],
        "ml2_bridge": section.get("ml2_bridge"),
        "ml2_patch": ml2_patch,
        "policy": {
            "ml_makes_independent_recommendations": True,
            "rules_filter_execution": True,
            "rules_block_cannot_be_overridden": True,
            "tracks_rules_allowed_and_rules_blocked_candidates": True,
            "tracks_ml_recommend_and_ml_oppose_cases": True,
            "labels_15m_60m_eod_next_session": True,
            "tracks_mfe_mae": True,
            "executed_labels_weight": 1.0,
            "counterfactual_60m_weight": COUNTERFACTUAL_WEIGHT_60M,
            "counterfactual_eod_weight": COUNTERFACTUAL_WEIGHT_EOD,
            "counterfactual_next_session_weight": COUNTERFACTUAL_WEIGHT_NEXT_SESSION,
            "counterfactual_rows_count_toward_promotion": False,
            "changes_trade_selection": False,
            "changes_sizing": False,
            "changes_risk_controls": False,
            "places_orders": False,
            "live_trade_authority": "none",
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _module()
    ml2_patch = _patch_ml_phase2()
    save_patch = _patch_save_state(core)
    watchdog = start_watchdog(core) if core is not None else {
        "started": False,
        "reason": "core_not_ready",
    }
    state = _state(core)
    if state:
        update_state(state, core, fetch_market_data=False)
    _LAST = {
        "status": "ok" if core is not None else "pending",
        "version": VERSION,
        "ml2_patch": ml2_patch,
        "save_state_patched": save_patch,
        "watchdog": watchdog,
        "authority": {
            "rules_remain_execution_gate": True,
            "ml_execution_authority": False,
            "live_trade_authority": "none",
            "places_orders": False,
        },
    }
    return dict(_LAST)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    if id(flask_app) in REGISTERED_APP_IDS:
        apply(core or _module())
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state = _state(core or _module())
        force = str(request.args.get("refresh", "0")).lower() in {
            "1", "true", "yes", "on"
        }
        update_state(state, core or _module(), fetch_market_data=force)
        if force:
            _save_state(core or _module(), state)
        return jsonify(status_payload(state, core or _module()))

    def dataset_route():
        state = _state(core or _module())
        update_state(state, core or _module(), fetch_market_data=False)
        section = _ensure(state)
        try:
            limit = max(1, min(int(request.args.get("limit", "250")), 1000))
        except Exception:
            limit = 250
        rows = _l(section.get("training_rows"))
        return jsonify(
            {
                "status": "ok",
                "type": "ml_counterfactual_training_dataset",
                "version": VERSION,
                "rows_total": len(rows),
                "rows_returned": min(limit, len(rows)),
                "dataset_tail": rows[-limit:],
                "promotion_gates_use_counterfactual_rows": False,
            }
        )

    paths = {
        "/paper/ml-counterfactual-ledger-status": (
            "paper_ml_counterfactual_ledger_status",
            status_route,
        ),
        "/paper/ml-counterfactual-training-dataset": (
            "paper_ml_counterfactual_training_dataset",
            dataset_route,
        ),
    }
    for path, (endpoint, view) in paths.items():
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, view)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _module())
    return {"status": "ok", "version": VERSION, "routes": sorted(paths)}


def start_bootstrap_watchdog(timeout_seconds: float = 240.0) -> Dict[str, Any]:
    """Wait for the Flask core, then install the ledger exactly once."""
    global _BOOTSTRAP_STARTED
    with _LOCK:
        if _BOOTSTRAP_STARTED:
            return {"started": True, "already_started": True, "version": VERSION}
        _BOOTSTRAP_STARTED = True

    def worker() -> None:
        deadline = time.monotonic() + max(5.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            core = _module()
            flask_app = getattr(core, "app", None) if core is not None else None
            if core is not None and flask_app is not None:
                try:
                    apply(core)
                    register_routes(flask_app, core)
                    return
                except Exception:
                    pass
            time.sleep(0.25)

    thread = threading.Thread(
        target=worker,
        daemon=True,
        name="ml-counterfactual-bootstrap",
    )
    thread.start()
    return {"started": True, "version": VERSION, "thread_name": thread.name}


try:
    start_bootstrap_watchdog()
except Exception:
    pass
