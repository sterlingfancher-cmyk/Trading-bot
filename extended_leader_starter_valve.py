"""Extended leader starter valve for the core entry pipeline.

This is intentionally a helper-function patch, not a try_entries wrapper. It lets
an underdeployed paper account take one tiny starter in a top-ranked leader that
is blocked only for an upper-extension/chase reason, while preserving cooldowns,
self-defense, risk halts, market-regime blocks, and daily-loss controls.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "extended-leader-starter-valve-2026-06-29-v1"
ENABLED = os.environ.get("EXTENDED_LEADER_STARTER_VALVE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_REVIEWED_RANK = int(os.environ.get("EXTENDED_LEADER_STARTER_MAX_REVIEWED_RANK", "5"))
MAX_ENTRIES_PER_DAY = int(os.environ.get("EXTENDED_LEADER_STARTER_MAX_ENTRIES_PER_DAY", "1"))
MIN_CASH_PCT = float(os.environ.get("EXTENDED_LEADER_STARTER_MIN_CASH_PCT", "80.0"))
MIN_RAW_SCORE = float(os.environ.get("EXTENDED_LEADER_STARTER_MIN_RAW_SCORE", "0.0135"))
MIN_RANK_SCORE = float(os.environ.get("EXTENDED_LEADER_STARTER_MIN_RANK_SCORE", "0.0190"))
ALLOC_FACTOR = float(os.environ.get("EXTENDED_LEADER_STARTER_ALLOC_FACTOR", "0.22"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("EXTENDED_LEADER_STARTER_MAX_DAILY_LOSS_PCT", "0.00"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("EXTENDED_LEADER_STARTER_MAX_INTRADAY_DRAWDOWN_PCT", "0.10"))
ALLOWED_MODES = {s.strip().lower() for s in os.environ.get("EXTENDED_LEADER_STARTER_ALLOWED_MODES", "risk_on,constructive").split(",") if s.strip()}
ALLOWED_REASONS = {
    s.strip()
    for s in os.environ.get(
        "EXTENDED_LEADER_STARTER_ALLOWED_REASONS",
        "extended_above_5m_ma20,extension_chase,relative_strength_leader_exception_block",
    ).split(",")
    if s.strip()
}

REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_LAST_STATUS: Dict[str, Any] = {}
_ORIGINAL_FN = None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        return getattr(core, "portfolio", {}) or {}
    except Exception:
        return {}


def _cash_pct(core: Any) -> float:
    pf = _portfolio(core)
    cash = _safe_float(pf.get("cash"), 0.0)
    equity = _safe_float(pf.get("equity"), 0.0)
    if equity <= 0.0:
        equity = cash
    if equity <= 0.0:
        return 0.0
    return round((cash / equity) * 100.0, 4)


def _walk_values(obj: Any, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    out: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"reason", "entry_context", "trade_class", "signal_type", "selection_reason", "quality_reason", "status"} and value:
                out.append(str(value).lower())
            out.extend(_walk_values(value, depth + 1))
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            out.extend(_walk_values(value, depth + 1))
    elif isinstance(obj, str):
        out.append(obj.lower())
    return out


def _quality_reason(info: Any) -> str:
    if isinstance(info, dict):
        for key in ("reason", "quality_reason", "status"):
            if info.get(key):
                return str(info.get(key))
        controlled = info.get("controlled_pullback_info")
        if isinstance(controlled, dict) and controlled.get("reason"):
            return str(controlled.get("reason"))
    return str(info or "unknown")


def _is_upper_extension(signal: Dict[str, Any], quality_info: Any) -> bool:
    text = " ".join(_walk_values(signal) + _walk_values(quality_info))
    if any(token in text for token in ("extended_below", "extended below", "below_5m", "below 5m")):
        return False
    return any(token in text for token in ("extended_above", "extended above", "above_5m", "above 5m", "near_high", "overstretched", "chase"))


def _risk_ok(core: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    try:
        rc = core.get_risk_controls() if callable(getattr(core, "get_risk_controls", None)) else (_portfolio(core).get("risk_controls") or {})
    except Exception:
        rc = _portfolio(core).get("risk_controls") or {}
    if not isinstance(rc, dict):
        rc = {}
    mode = str((market or {}).get("market_mode") or "").lower()
    if mode not in ALLOWED_MODES:
        return False, {"reason": "extended_starter_market_mode_not_allowed", "market_mode": mode, "allowed_modes": sorted(ALLOWED_MODES)}
    if bool((market or {}).get("bear_confirmed")) or mode in {"risk_off", "crash_warning", "defensive_rotation", "bear"}:
        return False, {"reason": "extended_starter_market_regime_block", "market_mode": mode, "bear_confirmed": bool((market or {}).get("bear_confirmed"))}
    futures = (market or {}).get("futures_bias", {}) or {}
    if str(futures.get("action") or "").lower() == "block_opening_longs":
        return False, {"reason": "extended_starter_futures_block_opening_longs", "futures_bias": futures}
    if bool(rc.get("halted", False)):
        return False, {"reason": "extended_starter_risk_halted", "risk_controls": rc}
    if bool(rc.get("self_defense_active", False)):
        return False, {"reason": "extended_starter_self_defense_active", "risk_controls": rc}
    daily_loss = _safe_float(rc.get("daily_loss_pct"), 0.0)
    intraday_dd = _safe_float(rc.get("intraday_drawdown_pct"), 0.0)
    if daily_loss > MAX_DAILY_LOSS_PCT:
        return False, {"reason": "extended_starter_daily_loss_not_clean", "daily_loss_pct": daily_loss, "max_daily_loss_pct": MAX_DAILY_LOSS_PCT}
    if intraday_dd > MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "extended_starter_intraday_drawdown_too_high", "intraday_drawdown_pct": intraday_dd, "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT}
    return True, {"reason": "extended_starter_risk_clean", "risk_controls": rc}


def _starter_entries_today(core: Any) -> int:
    try:
        return int(getattr(__import__("core_entry_pipeline"), "_entries_today_with_context")(core, "core_participation_valve"))
    except Exception:
        return 0


def _patched_participation_valve_ok(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], quality_info: Any, rank_index: int, entries_this_cycle: int, valve_entries_this_cycle: int):
    global _LAST_STATUS
    cep = __import__("core_entry_pipeline")
    original = _ORIGINAL_FN
    if callable(original):
        ok, info = original(core, signal, params, market, quality_info, rank_index, entries_this_cycle, valve_entries_this_cycle)
        if ok:
            _LAST_STATUS = {"status": "passthrough_allowed", "reason": "base_participation_valve_allowed", "latest": info}
            return ok, info
    else:
        info = {"reason": "base_participation_valve_missing"}

    symbol = str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()
    side = str(signal.get("side") or "long").lower().strip() or "long"
    score = _safe_float(signal.get("score"), 0.0)
    rank_score = _safe_float(signal.get("core_entry_rank_score"), score)
    quality_reason = _quality_reason(quality_info)
    cash_pct = _cash_pct(core)
    base = {
        "version": VERSION,
        "symbol": symbol,
        "side": side,
        "rank_index": rank_index,
        "score": round(score, 6),
        "rank_score": round(rank_score, 6),
        "quality_reason": quality_reason,
        "cash_pct": cash_pct,
        "base_participation_result": info,
    }

    def blocked(reason: str, **extra: Any):
        payload = {**base, "reason": reason, **extra}
        _LAST_STATUS = {"status": "blocked", "latest": payload}
        return False, payload

    if not ENABLED:
        return blocked("extended_starter_disabled")
    if side != "long":
        return blocked("extended_starter_long_only")
    if rank_index > MAX_REVIEWED_RANK:
        return blocked("extended_starter_rank_too_low", max_rank=MAX_REVIEWED_RANK)
    if valve_entries_this_cycle >= 1:
        return blocked("extended_starter_cycle_limit", max_entries_per_cycle=1)
    if _starter_entries_today(core) >= MAX_ENTRIES_PER_DAY:
        return blocked("extended_starter_daily_limit", max_entries_per_day=MAX_ENTRIES_PER_DAY)
    if cash_pct < MIN_CASH_PCT:
        return blocked("extended_starter_cash_not_high_enough", min_cash_pct=MIN_CASH_PCT)
    if score < MIN_RAW_SCORE:
        return blocked("extended_starter_raw_score_too_low", min_raw_score=MIN_RAW_SCORE)
    if rank_score < MIN_RANK_SCORE:
        return blocked("extended_starter_rank_score_too_low", min_rank_score=MIN_RANK_SCORE)
    if quality_reason not in ALLOWED_REASONS and not _is_upper_extension(signal, quality_info):
        return blocked("extended_starter_not_upper_extension_leader", allowed_reasons=sorted(ALLOWED_REASONS))
    if not _is_upper_extension(signal, quality_info):
        return blocked("extended_starter_requires_upper_extension_signal")
    risk_ok, risk_info = _risk_ok(core, market or {})
    if not risk_ok:
        return blocked(risk_info.get("reason", "extended_starter_risk_block"), **risk_info)

    try:
        cep.PARTICIPATION_VALVE_ALLOC_FACTOR = min(float(getattr(cep, "PARTICIPATION_VALVE_ALLOC_FACTOR", 1.0)), ALLOC_FACTOR)
    except Exception:
        pass
    payload = {**base, "reason": "extended_leader_starter_ok", "alloc_factor": ALLOC_FACTOR, "risk": risk_info}
    _LAST_STATUS = {"status": "allowed", "latest": payload}
    return True, payload


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED, _ORIGINAL_FN
    if not ENABLED:
        return status_payload(core)
    try:
        import core_entry_pipeline as cep
        current = getattr(cep, "_participation_valve_ok", None)
        if getattr(current, "_extended_leader_starter_version", None) == VERSION:
            _PATCHED = True
        else:
            _ORIGINAL_FN = current
            _patched_participation_valve_ok._extended_leader_starter_version = VERSION  # type: ignore[attr-defined]
            cep._participation_valve_ok = _patched_participation_valve_ok
            _PATCHED = True
    except Exception as exc:
        _LAST_STATUS["apply_error"] = f"{type(exc).__name__}: {exc}"
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def policy() -> Dict[str, Any]:
    return {
        "enabled": bool(ENABLED),
        "helper_patch_only": True,
        "does_not_wrap_try_entries": True,
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
        "max_reviewed_rank": MAX_REVIEWED_RANK,
        "alloc_factor": ALLOC_FACTOR,
        "min_cash_pct": MIN_CASH_PCT,
        "min_raw_score": MIN_RAW_SCORE,
        "min_rank_score": MIN_RANK_SCORE,
        "allowed_modes": sorted(ALLOWED_MODES),
        "allowed_reasons": sorted(ALLOWED_REASONS),
        "does_not_bypass_cooldowns": True,
        "does_not_bypass_self_defense": True,
        "does_not_bypass_risk_halts": True,
        "does_not_change_live_authority": True,
        "does_not_change_ml_authority": True,
        "paper_only_controlled_starter": True,
        "authority_changed": False,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "type": "extended_leader_starter_valve_status",
        "version": VERSION,
        "generated_local": _now(core or _mod()),
        "enabled": bool(ENABLED),
        "patched": bool(_PATCHED),
        "latest": dict(_LAST_STATUS),
        "policy": policy(),
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(apply(core or _mod()))

    if "/paper/extended-leader-starter-valve-status" not in existing:
        flask_app.add_url_rule("/paper/extended-leader-starter-valve-status", "extended_leader_starter_valve_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
