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
stronger evidence than counterfactual market-path labels. Counterfactual labels
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
_REGISTERED_APP_IDS: set[int] = set()
_WATCHDOG_CORE_IDS: set[int] = set()
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
        # allow entries without epoch or entries that occurred shortly after the
        # recommendation event (120s back tolerance)
        if epoch is None or epoch >= event_epoch - 120:
            matching_entries.append((epoch or event_epoch, row))
    matching_entries.sort(key=lambda item: item[0])
    entry = matching_entries[0][1] if matching_entries else None

    matching_exits = []

    # NOTE: Production-shaped regression observed a duplicated TEM close mapping
    # where the same recorded exit was being matched to an ML/event row even when
    # the exit clearly pre-dated the matched entry. To avoid assigning an exit
    # that happened before the selected entry (thereby producing duplicate
    # apparent closes/ownership), require that candidate exits occur at or after
    # the chosen entry epoch when an entry with a known epoch exists. If no
    # entry epoch is known, fall back to the original event_epoch anchor.

    entry_epoch = None
    if entry is not None:
        entry_epoch = _trade_epoch(entry) or event_epoch

    for row in _exit_rows(state):
        if _symbol(row) != symbol or _side(row) != side:
            continue
        epoch = _trade_epoch(row)
        # Preserve permissive behavior for unknown-timestamp exits (epoch is None)
        # but avoid matching exits that clearly pre-date the discovered entry.
        if epoch is None:
            matching_exits.append((epoch or (entry_epoch or event_epoch), row))
            continue
        # If we have a concrete entry epoch, require exit >= entry_epoch
        if entry_epoch is not None:
            if epoch >= entry_epoch:
                matching_exits.append((epoch, row))
        else:
            # No matched entry with epoch; fall back to requiring exit >= event_epoch
            if epoch >= event_epoch:
                matching_exits.append((epoch, row))

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
