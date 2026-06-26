"""Core entry pipeline v2 — non-wrapper replacement with participation valve.

This module replaces app.try_entries_and_rotations with a complete implementation
instead of wrapping the existing function. It restores best-of-cycle candidate
ranking, a profit-guard soft-pause sleeve, and a tightly capped participation
valve for top-ranked candidates that are barely below score floor.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "core-entry-pipeline-2026-06-26-v2-participation-valve"
ENABLED = os.environ.get("CORE_ENTRY_PIPELINE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("CORE_ENTRY_PIPELINE_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
PATCH_ENABLED = os.environ.get("CORE_ENTRY_PIPELINE_PATCH_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

BEST_OF_CYCLE_ENABLED = os.environ.get("CORE_ENTRY_BEST_OF_CYCLE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_NOT_SELECTED_ROWS = int(os.environ.get("CORE_ENTRY_MAX_NOT_SELECTED_ROWS", "15"))

PROFIT_GUARD_SLEEVE_ENABLED = os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY = int(os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY", "1"))
PROFIT_GUARD_SLEEVE_ALLOC_FACTOR = float(os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_ALLOC_FACTOR", "0.35"))
PROFIT_GUARD_SLEEVE_MIN_SCORE = float(os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_MIN_SCORE", "0.018"))
PROFIT_GUARD_SLEEVE_ALLOWED_MODES = {s.strip().lower() for s in os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_ALLOWED_MODES", "risk_on,constructive").split(",") if s.strip()}
PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT = float(os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT", "0.15"))
PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("CORE_ENTRY_PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT", "0.35"))

PARTICIPATION_VALVE_ENABLED = os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY = int(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY", "1"))
PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE = int(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE", "1"))
PARTICIPATION_VALVE_MAX_REVIEWED_RANK = int(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_REVIEWED_RANK", "3"))
PARTICIPATION_VALVE_ALLOC_FACTOR = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_ALLOC_FACTOR", "0.30"))
PARTICIPATION_VALVE_MIN_RAW_SCORE = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MIN_RAW_SCORE", "0.0105"))
PARTICIPATION_VALVE_MIN_RANK_SCORE = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MIN_RANK_SCORE", "0.0150"))
PARTICIPATION_VALVE_MAX_SCORE_GAP = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_SCORE_GAP", "0.0020"))
PARTICIPATION_VALVE_ALLOWED_MODES = {s.strip().lower() for s in os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_ALLOWED_MODES", "risk_on,constructive").split(",") if s.strip()}
PARTICIPATION_VALVE_MAX_DAILY_LOSS_PCT = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_DAILY_LOSS_PCT", "0.00"))
PARTICIPATION_VALVE_MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("CORE_ENTRY_PARTICIPATION_VALVE_MAX_INTRADAY_DRAWDOWN_PCT", "0.10"))
PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS = {
    s.strip()
    for s in os.environ.get(
        "CORE_ENTRY_PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS",
        "entry_score_below_minimum,score_below_post_harvest_floor,relative_strength_leader_exception_block",
    ).split(",")
    if s.strip()
}

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

HARD_PROFIT_GUARD_MARKERS = {"hard lock", "giveback", "lock triggered"}
EXTENSION_BLOCK_TOKENS = ("extended", "extension", "chase", "near_high", "overstretched", "too_close_to_intraday_high")
THEME_PRIORITY = {
    "space_stocks": 0.006,
    "bitcoin_ai_compute": 0.005,
    "semi_leaders": 0.0045,
    "memory_storage": 0.0045,
    "data_center_infra": 0.004,
    "power_grid_data_center": 0.004,
    "small_cap_momentum": 0.0035,
    "mega_cap_ai": 0.003,
    "cloud_cyber_software": 0.0025,
    "precious_metals": 0.0015,
}
PREFERRED_SYMBOLS = {
    "RKLB", "RDW", "LUNR", "ASTS", "SPCX", "SATL",
    "AMD", "AVGO", "MU", "LRCX", "NVTS", "NBIS", "GEV", "STX", "WDC", "DELL", "HPE", "GLW", "SNDK", "ON",
    "CIFR", "CLSK", "RIOT", "HIVE", "HUT", "BTDR", "WULF", "CORZ", "IREN", "MARA",
}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        return getattr(core, "portfolio", {}) or {}
    except Exception:
        return {}


def _positions(core: Any) -> Dict[str, Any]:
    try:
        positions = _portfolio(core).get("positions", {}) or {}
        return positions if isinstance(positions, dict) else {}
    except Exception:
        return {}


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _entry_blockers(entry_block_reason: Any) -> set[str]:
    return {part.strip() for part in str(entry_block_reason or "").split(",") if part.strip()}


def _risk_controls(core: Any) -> Dict[str, Any]:
    try:
        fn = getattr(core, "get_risk_controls", None)
        if callable(fn):
            rc = fn()
            return rc if isinstance(rc, dict) else {}
    except Exception:
        pass
    try:
        rc = _portfolio(core).get("risk_controls", {}) or {}
        return rc if isinstance(rc, dict) else {}
    except Exception:
        return {}


def _profit_guard_state(core: Any) -> Dict[str, Any]:
    rc = _risk_controls(core)
    active = bool(rc.get("profit_guard_active", False))
    reason = str(rc.get("profit_guard_reason") or "")
    lower = reason.lower()
    if not active:
        state = "inactive"
    elif any(marker in lower for marker in HARD_PROFIT_GUARD_MARKERS):
        state = "hard_block"
    elif "day profit pause" in lower or "pause reached" in lower:
        state = "soft_pause"
    else:
        state = "active_unknown"
    return {"active": active, "state": state, "reason": reason, "risk_controls": rc}


def _bucket(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("bucket") or signal.get("symbol_bucket")
    if value:
        return str(value)
    try:
        fn = getattr(core, "symbol_bucket", None)
        if callable(fn):
            return str(fn(symbol))
    except Exception:
        pass
    try:
        return str((getattr(core, "SYMBOL_BUCKET", {}) or {}).get(symbol, "unknown"))
    except Exception:
        return "unknown"


def _sector(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("sector")
    if value:
        return str(value)
    try:
        return str((getattr(core, "SYMBOL_SECTOR", {}) or {}).get(symbol, "UNKNOWN"))
    except Exception:
        return "UNKNOWN"


def _walk_values(obj: Any, depth: int = 0) -> List[str]:
    if depth > 4:
        return []
    out: List[str] = []
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


def _text(signal: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("entry_context", "trade_class", "reason", "signal_type", "selection_reason"):
        value = signal.get(key)
        if value:
            parts.append(str(value).lower())
    for key in ("catalyst", "theme_confirmation"):
        value = signal.get(key)
        if isinstance(value, dict) and value.get("active"):
            parts.append(key)
    return " ".join(parts)


def _quality_reason(info: Any) -> str:
    if isinstance(info, dict):
        for key in ("reason", "quality_reason", "status"):
            if info.get(key):
                return str(info.get(key))
        controlled = info.get("controlled_pullback_info")
        if isinstance(controlled, dict) and controlled.get("reason"):
            return str(controlled.get("reason"))
    return str(info or "unknown")


def _has_extension_warning(signal: Dict[str, Any], info: Any) -> bool:
    text = " ".join(_walk_values(signal) + _walk_values(info))
    return any(token in text for token in EXTENSION_BLOCK_TOKENS)


def _normal_entry_floor(core: Any, market: Dict[str, Any], side: str, fallback: float = 0.0) -> float:
    try:
        fn = getattr(core, "min_entry_score_for_market", None)
        if callable(fn):
            return _safe_float(fn(market or {}, side), fallback)
    except Exception:
        pass
    return fallback


def _is_relative_strength(signal: Dict[str, Any]) -> bool:
    text = _text(signal)
    if "relative_strength" in text or "relative strength" in text or "leader" in text:
        return True
    for key in ("relative_strength", "relative_strength_score", "rs_score", "rs_rank", "momentum_rank"):
        value = signal.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, (int, float)) and _safe_float(value) > 0:
            return True
    return False


def _is_breakout(signal: Dict[str, Any]) -> bool:
    text = _text(signal)
    return "breakout" in text or "reclaim" in text or any(bool(signal.get(k)) for k in ("breakout", "is_breakout", "breakout_signal"))


def _rank_score(core: Any, signal: Dict[str, Any], market: Dict[str, Any]) -> float:
    symbol = _symbol(signal)
    bucket = _bucket(core, symbol, signal)
    sector = _sector(core, symbol, signal)
    score = _safe_float(signal.get("score"), 0.0)
    score += THEME_PRIORITY.get(bucket, 0.0)
    if symbol in PREFERRED_SYMBOLS:
        score += 0.002
    if sector in (market.get("sector_leaders") or []):
        score += 0.003
    if _is_relative_strength(signal):
        score += 0.003
    if _is_breakout(signal):
        score += 0.003
    catalyst = signal.get("catalyst")
    theme = signal.get("theme_confirmation")
    if isinstance(catalyst, dict) and catalyst.get("active"):
        score += 0.0025
    if isinstance(theme, dict) and theme.get("active"):
        score += 0.0025
    text = _text(signal)
    if "extended" in text or "chase" in text or "near_high" in text:
        score -= 0.004
    return round(float(score), 8)


def _prepare_candidates(core: Any, long_signals: Iterable[Any], short_signals: Iterable[Any], params: Dict[str, Any], market: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if params.get("allow_longs", False):
        candidates.extend([dict(s) for s in (long_signals or []) if isinstance(s, dict)])
    if params.get("allow_shorts", False):
        candidates.extend([dict(s) for s in (short_signals or []) if isinstance(s, dict)])
    for signal in candidates:
        symbol = _symbol(signal)
        signal.setdefault("symbol", symbol)
        signal.setdefault("side", "long")
        signal.setdefault("bucket", _bucket(core, symbol, signal))
        signal.setdefault("sector", _sector(core, symbol, signal))
        signal["core_entry_rank_score"] = _rank_score(core, signal, market or {})
    key = (lambda x: _safe_float(x.get("core_entry_rank_score", x.get("score", 0.0)), 0.0)) if BEST_OF_CYCLE_ENABLED else (lambda x: _safe_float(x.get("score"), 0.0))
    return sorted(candidates, key=key, reverse=True)


def _block_rows(candidates: Iterable[Dict[str, Any]], reason: str, max_rows: int = 10, extra: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for signal in list(candidates or [])[:max_rows]:
        row = {"symbol": signal.get("symbol"), "side": signal.get("side"), "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": reason}
        if extra:
            row.update(extra)
        rows.append(row)
    return rows


def _entries_today_with_context(core: Any, context_token: str) -> int:
    try:
        today = getattr(core, "today_key", lambda: "")()
        trades = getattr(core, "trades_for_date", lambda _d: [])(today)
    except Exception:
        trades = []
    count = 0
    for trade in trades or []:
        if not isinstance(trade, dict) or str(trade.get("action") or "") != "entry":
            continue
        text = " ".join(str(trade.get(k) or "") for k in ("entry_context", "trade_class", "reason")).lower()
        if context_token.lower() in text:
            count += 1
    return count


def _profit_guard_sleeve_entries_today(core: Any) -> int:
    return _entries_today_with_context(core, "profit_guard_core_sleeve")


def _participation_valve_entries_today(core: Any) -> int:
    return _entries_today_with_context(core, "core_participation_valve")


def _risk_clean_for_participation(core: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    rc = _risk_controls(core)
    mode = str((market or {}).get("market_mode") or "").lower()
    if mode not in PARTICIPATION_VALVE_ALLOWED_MODES:
        return False, {"reason": "participation_valve_market_mode_not_allowed", "market_mode": mode, "allowed_modes": sorted(PARTICIPATION_VALVE_ALLOWED_MODES)}
    if bool((market or {}).get("bear_confirmed")) or mode in {"risk_off", "crash_warning", "defensive_rotation", "bear"}:
        return False, {"reason": "participation_valve_market_regime_block", "market_mode": mode, "bear_confirmed": bool((market or {}).get("bear_confirmed"))}
    futures = (market or {}).get("futures_bias", {}) or {}
    if str(futures.get("action") or "").lower() == "block_opening_longs":
        return False, {"reason": "participation_valve_futures_block_opening_longs", "futures_bias": futures}
    if bool(rc.get("halted", False)):
        return False, {"reason": "participation_valve_risk_halted", "risk_controls": rc}
    if bool(rc.get("self_defense_active", False)):
        return False, {"reason": "participation_valve_self_defense_active", "risk_controls": rc}
    daily_loss = _safe_float(rc.get("daily_loss_pct"), 0.0)
    intraday_dd = _safe_float(rc.get("intraday_drawdown_pct"), 0.0)
    if daily_loss > PARTICIPATION_VALVE_MAX_DAILY_LOSS_PCT:
        return False, {"reason": "participation_valve_daily_loss_not_clean", "daily_loss_pct": daily_loss, "max_daily_loss_pct": PARTICIPATION_VALVE_MAX_DAILY_LOSS_PCT}
    if intraday_dd > PARTICIPATION_VALVE_MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "participation_valve_intraday_drawdown_too_high", "intraday_drawdown_pct": intraday_dd, "max_intraday_drawdown_pct": PARTICIPATION_VALVE_MAX_INTRADAY_DRAWDOWN_PCT}
    return True, {"reason": "participation_valve_risk_clean", "risk_controls": rc}


def _participation_valve_ok(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], quality_info: Any, rank_index: int, entries_this_cycle: int, valve_entries_this_cycle: int) -> Tuple[bool, Dict[str, Any]]:
    if not (PARTICIPATION_VALVE_ENABLED and _paper_context()):
        return False, {"reason": "participation_valve_disabled_or_not_paper"}
    symbol = _symbol(signal)
    side = _side(signal)
    score = _safe_float(signal.get("score"), 0.0)
    rank_score = _safe_float(signal.get("core_entry_rank_score"), score)
    quality_reason = _quality_reason(quality_info)
    required_score = _safe_float(quality_info.get("required_score") if isinstance(quality_info, dict) else None, 0.0)
    if required_score <= 0:
        required_score = _normal_entry_floor(core, market, side, 0.0)
    score_gap = max(0.0, required_score - score) if required_score > 0 else 999.0

    base = {
        "version": VERSION,
        "symbol": symbol,
        "side": side,
        "rank_index": rank_index,
        "score": round(score, 6),
        "rank_score": round(rank_score, 6),
        "required_score": round(required_score, 6),
        "score_gap": round(score_gap, 6),
        "quality_reason": quality_reason,
    }
    if side != "long":
        return False, {**base, "reason": "participation_valve_long_only"}
    if rank_index > PARTICIPATION_VALVE_MAX_REVIEWED_RANK:
        return False, {**base, "reason": "participation_valve_rank_too_low", "max_rank": PARTICIPATION_VALVE_MAX_REVIEWED_RANK}
    if valve_entries_this_cycle >= PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE:
        return False, {**base, "reason": "participation_valve_cycle_limit", "max_entries_per_cycle": PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE}
    if _participation_valve_entries_today(core) >= PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY:
        return False, {**base, "reason": "participation_valve_daily_limit", "max_entries_per_day": PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY}
    if quality_reason not in PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS:
        return False, {**base, "reason": "participation_valve_quality_reason_not_allowed", "allowed_reasons": sorted(PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS)}
    if score < PARTICIPATION_VALVE_MIN_RAW_SCORE:
        return False, {**base, "reason": "participation_valve_raw_score_too_low", "min_raw_score": PARTICIPATION_VALVE_MIN_RAW_SCORE}
    if rank_score < PARTICIPATION_VALVE_MIN_RANK_SCORE:
        return False, {**base, "reason": "participation_valve_rank_score_too_low", "min_rank_score": PARTICIPATION_VALVE_MIN_RANK_SCORE}
    if score_gap > PARTICIPATION_VALVE_MAX_SCORE_GAP:
        return False, {**base, "reason": "participation_valve_score_gap_too_wide", "max_score_gap": PARTICIPATION_VALVE_MAX_SCORE_GAP}
    if _has_extension_warning(signal, quality_info):
        return False, {**base, "reason": "participation_valve_extension_or_chase_block"}
    risk_ok, risk_info = _risk_clean_for_participation(core, market)
    if not risk_ok:
        return False, {**base, **risk_info}
    return True, {**base, "reason": "participation_valve_ok", "alloc_factor": PARTICIPATION_VALVE_ALLOC_FACTOR, "risk": risk_info}


def _profit_guard_sleeve_context_ok(core: Any, blockers: set[str], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not PROFIT_GUARD_SLEEVE_ENABLED:
        return False, {"reason": "profit_guard_core_sleeve_disabled"}
    extra_blockers = sorted(blockers - {"profit_guard_active"})
    if extra_blockers:
        return False, {"reason": "non_profit_guard_entry_blocker_present", "extra_blockers": extra_blockers, "blockers": sorted(blockers)}
    state = _profit_guard_state(core)
    if not state.get("active"):
        return False, {"reason": "profit_guard_not_active", "profit_guard": {k: v for k, v in state.items() if k != "risk_controls"}}
    if state.get("state") != "soft_pause":
        return False, {"reason": "profit_guard_state_not_soft_pause", "profit_guard": {k: v for k, v in state.items() if k != "risk_controls"}}
    mode = str((market or {}).get("market_mode") or "").lower()
    if mode not in PROFIT_GUARD_SLEEVE_ALLOWED_MODES:
        return False, {"reason": "market_mode_not_allowed_for_profit_guard_core_sleeve", "market_mode": mode, "allowed_modes": sorted(PROFIT_GUARD_SLEEVE_ALLOWED_MODES)}
    if bool((market or {}).get("bear_confirmed")) or mode in {"risk_off", "crash_warning", "defensive_rotation", "bear"}:
        return False, {"reason": "market_regime_not_allowed_for_profit_guard_core_sleeve", "market_mode": mode, "bear_confirmed": bool((market or {}).get("bear_confirmed"))}
    futures = (market or {}).get("futures_bias", {}) or {}
    if str(futures.get("action") or "").lower() == "block_opening_longs":
        return False, {"reason": "futures_block_opening_longs", "futures_bias": futures}
    rc = _risk_controls(core)
    if bool(rc.get("halted", False)):
        return False, {"reason": "risk_halted", "risk_controls": rc}
    daily_loss = _safe_float(rc.get("daily_loss_pct"), 0.0)
    intraday_dd = _safe_float(rc.get("intraday_drawdown_pct"), 0.0)
    if daily_loss > PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT:
        return False, {"reason": "daily_loss_too_high_for_profit_guard_core_sleeve", "daily_loss_pct": daily_loss}
    if intraday_dd > PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "intraday_drawdown_too_high_for_profit_guard_core_sleeve", "intraday_drawdown_pct": intraday_dd}
    used = _profit_guard_sleeve_entries_today(core)
    if used >= PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY:
        return False, {"reason": "profit_guard_core_sleeve_daily_limit", "entries_today": used, "max_entries_per_day": PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY}
    return True, {"reason": "profit_guard_core_sleeve_context_ok", "profit_guard": {k: v for k, v in state.items() if k != "risk_controls"}, "entries_today": used}


def _try_profit_guard_core_sleeve(core: Any, candidates: List[Dict[str, Any]], params: Dict[str, Any], market: Dict[str, Any], blockers: set[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    rotations: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    ok, context = _profit_guard_sleeve_context_ok(core, blockers, market)
    payload = {"version": VERSION, "status": "checked", "context": context, "reviewed_count": 0, "eligible_count": 0, "selected_candidates": []}
    if not ok:
        payload.update({"status": "blocked", "reason": context.get("reason", "profit_guard_core_sleeve_blocked")})
        return entries, rotations, _block_rows(candidates, payload["reason"]), payload
    selected: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    params_dict = dict(params or {})
    for signal in candidates[:30]:
        payload["reviewed_count"] += 1
        symbol = _symbol(signal)
        side = _side(signal)
        row = {"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score")}
        if side != "long":
            rejected.append({**row, "reason": "profit_guard_core_sleeve_long_only"})
            continue
        if symbol in _positions(core):
            rejected.append({**row, "reason": "already_held"})
            continue
        try:
            if callable(getattr(core, "is_in_cooldown", None)) and core.is_in_cooldown(symbol):
                rejected.append({**row, "reason": "cooldown"})
                continue
        except Exception:
            pass
        if _safe_float(signal.get("score"), 0.0) < PROFIT_GUARD_SLEEVE_MIN_SCORE:
            rejected.append({**row, "reason": "score_below_profit_guard_core_sleeve_floor", "required_score": PROFIT_GUARD_SLEEVE_MIN_SCORE})
            continue
        candidate = dict(signal)
        candidate["alloc_factor"] = min(_safe_float(candidate.get("alloc_factor"), 1.0), PROFIT_GUARD_SLEEVE_ALLOC_FACTOR)
        candidate["entry_context"] = "profit_guard_core_sleeve"
        candidate["trade_class"] = "profit_guard_core_sleeve"
        try:
            quality_ok, quality_info = core.entry_quality_check(candidate, params_dict, market)
        except Exception as exc:
            rejected.append({**row, "reason": "entry_quality_check_error", "error": str(exc)})
            continue
        if not quality_ok:
            rejected.append({**row, "reason": "entry_quality_block", "quality_info": quality_info})
            continue
        selected.append({"signal": candidate, "summary": {**row, "reason": "selected_profit_guard_core_sleeve", "quality_info": quality_info}})
        break
    payload["eligible_count"] = len(selected)
    payload["selected_candidates"] = [s.get("summary") for s in selected]
    payload["rejected_preview"] = rejected[:15]
    if not selected:
        payload.update({"status": "no_eligible_candidate", "reason": "profit_guard_core_sleeve_no_candidate_passed_quality"})
        return entries, rotations, rejected[:10] or _block_rows(candidates, payload["reason"]), payload
    candidate = selected[0]["signal"]
    quality_info = selected[0]["summary"].get("quality_info", {})
    entry = core.enter_position(candidate, params_dict, market_mode=(market or {}).get("market_mode", "neutral"))
    if entry and not entry.get("blocked"):
        entry["quality_info"] = quality_info
        entry["core_entry_pipeline"] = {"version": VERSION, "mode": "profit_guard_core_sleeve"}
        entries.append(entry)
        payload.update({"status": "allowed", "reason": "profit_guard_soft_pause_core_sleeve_opened", "entries_returned_count": 1})
    else:
        if isinstance(entry, dict):
            blocked.append(entry)
        payload.update({"status": "attempted_no_entry", "reason": "enter_position_blocked_profit_guard_core_sleeve", "entries_returned_count": 0, "enter_position_result": entry})
    return entries, rotations, blocked, payload


def _core_try_entries_and_rotations(core: Any, long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
    entries: List[Dict[str, Any]] = []
    rotations: List[Dict[str, Any]] = []
    blocked_entries: List[Dict[str, Any]] = []
    participation_attempts: List[Dict[str, Any]] = []
    participation_entries: List[Dict[str, Any]] = []
    params = dict(params or {})
    market = dict(market or {})
    mode = market.get("market_mode", "neutral")
    max_positions = _safe_int(params.get("max_positions"), 0)
    max_new_entries = _safe_int(getattr(core, "MAX_NEW_ENTRIES_PER_CYCLE", 2), 2)
    candidates = _prepare_candidates(core, long_signals or [], short_signals or [], params, market)
    blockers = _entry_blockers(entry_block_reason)

    if not bool(new_entries_allowed):
        if "profit_guard_active" in blockers:
            sleeve_entries, sleeve_rotations, sleeve_blocked, sleeve_payload = _try_profit_guard_core_sleeve(core, candidates, params, market, blockers)
            try:
                _portfolio(core)["core_entry_pipeline"] = {"version": VERSION, "mode": "profit_guard_core_sleeve", **sleeve_payload}
            except Exception:
                pass
            if sleeve_entries or sleeve_rotations:
                return sleeve_entries, sleeve_rotations, sleeve_blocked
            return sleeve_entries, sleeve_rotations, sleeve_blocked[:15]
        block_reason = entry_block_reason or "new_entries_not_allowed"
        try:
            _portfolio(core)["core_entry_pipeline"] = {"version": VERSION, "mode": "blocked", "reason": block_reason, "candidate_count": len(candidates)}
        except Exception:
            pass
        return entries, rotations, _block_rows(candidates, block_reason)

    entries_this_cycle = 0
    participation_this_cycle = 0
    not_selected_rows = 0
    for rank_index, signal in enumerate(candidates, start=1):
        symbol = _symbol(signal)
        side = _side(signal)
        if not symbol:
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "missing_symbol", "score": signal.get("score")})
            continue
        if symbol in _positions(core):
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "already_held", "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score")})
            continue
        try:
            if core.is_in_cooldown(symbol):
                blocked_entries.append({"symbol": symbol, "side": side, "reason": "cooldown", "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score")})
                continue
        except Exception:
            pass
        if entries_this_cycle >= max_new_entries:
            reason = "not_best_of_cycle_candidate" if BEST_OF_CYCLE_ENABLED else "max_new_entries_per_cycle"
            if not_selected_rows < MAX_NOT_SELECTED_ROWS:
                blocked_entries.append({"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": reason, "max_new_entries_per_cycle": max_new_entries})
                not_selected_rows += 1
            continue

        if len(_positions(core)) < max_positions:
            try:
                ok, quality_info = core.entry_quality_check(signal, params, market)
            except Exception as exc:
                blocked_entries.append({"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": "entry_quality_check_error", "error": str(exc)})
                continue
            if not ok:
                valve_ok, valve_info = _participation_valve_ok(core, signal, params, market, quality_info, rank_index, entries_this_cycle, participation_this_cycle)
                participation_attempts.append(valve_info)
                if valve_ok:
                    starter = dict(signal)
                    starter["alloc_factor"] = min(_safe_float(starter.get("alloc_factor"), 1.0), PARTICIPATION_VALVE_ALLOC_FACTOR)
                    starter["entry_context"] = "core_participation_valve"
                    starter["trade_class"] = "core_participation_valve"
                    starter["core_participation_valve"] = valve_info
                    entry = core.enter_position(starter, params, market_mode=mode)
                    if entry and not entry.get("blocked"):
                        entry["quality_info"] = quality_info
                        entry["core_entry_pipeline"] = {"version": VERSION, "mode": "core_participation_valve", "rank_score": starter.get("core_entry_rank_score"), "best_of_cycle": bool(BEST_OF_CYCLE_ENABLED), "participation_valve": valve_info}
                        entries.append(entry)
                        participation_entries.append(entry)
                        entries_this_cycle += 1
                        participation_this_cycle += 1
                    else:
                        blocked_entries.append(entry or {"symbol": symbol, "side": side, "reason": "participation_valve_enter_position_returned_empty", "participation_valve": valve_info})
                    continue
                blocked_entries.append({"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": "entry_quality_block", "quality_info": quality_info, "participation_valve": valve_info})
                continue
            entry = core.enter_position(signal, params, market_mode=mode)
            if entry and not entry.get("blocked"):
                entry["quality_info"] = quality_info
                entry["core_entry_pipeline"] = {"version": VERSION, "rank_score": signal.get("core_entry_rank_score"), "best_of_cycle": bool(BEST_OF_CYCLE_ENABLED)}
                entries.append(entry)
                entries_this_cycle += 1
            else:
                blocked_entries.append(entry or {"symbol": symbol, "side": side, "reason": "enter_position_returned_empty"})
            continue

        weakest = core.weakest_position_for_rotation(signal)
        if not weakest:
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "max_positions_full", "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score")})
            continue
        allowed, info = core.rotation_allowed(signal, weakest, market)
        if not allowed:
            blocked_entries.append({"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": "max_positions_full_no_rotation", "rotation_info": info})
            continue
        weakest_symbol = weakest.get("symbol")
        ok, quality_info = core.entry_quality_check(signal, params, market, exclude_symbol=weakest_symbol)
        if not ok:
            blocked_entries.append({"symbol": symbol, "side": side, "score": signal.get("score"), "rank_score": signal.get("core_entry_rank_score"), "reason": "rotation_entry_quality_block", "rotation_info": info, "quality_info": quality_info})
            continue
        pos = _positions(core).get(weakest_symbol)
        if not pos:
            continue
        px_out = core.latest_price(weakest_symbol) or float(pos.get("last_price", pos.get("entry", 0)))
        exit_result = core.exit_position(weakest_symbol, px_out, "rotation_to_stronger_signal", market_mode=mode, extra={"new_score": round(_safe_float(signal.get("score"), 0.0), 6), "weakest_score": round(_safe_float(weakest.get("score"), 0.0), 6), "weakest_pnl_pct": round(_safe_float(weakest.get("pnl_pct"), 0.0) * 100, 2), "held_seconds": weakest.get("held_seconds"), "sector_aligned": signal.get("sector") in market.get("sector_leaders", []), "core_entry_pipeline_version": VERSION})
        entry_result = core.enter_position(signal, params, market_mode=mode)
        if entry_result and not entry_result.get("blocked"):
            entry_result["quality_info"] = quality_info
            entry_result["core_entry_pipeline"] = {"version": VERSION, "rank_score": signal.get("core_entry_rank_score"), "best_of_cycle": bool(BEST_OF_CYCLE_ENABLED)}
            entries_this_cycle += 1
        rotations.append({"out": weakest_symbol, "in": symbol, "exit": exit_result, "entry": entry_result, "info": info, "quality_info": quality_info})

    try:
        _portfolio(core)["core_entry_pipeline"] = {
            "version": VERSION,
            "mode": "normal",
            "candidate_count": len(candidates),
            "entries_count": len(entries),
            "rotations_count": len(rotations),
            "blocked_count": len(blocked_entries),
            "best_of_cycle_enabled": bool(BEST_OF_CYCLE_ENABLED),
            "participation_valve_enabled": bool(PARTICIPATION_VALVE_ENABLED),
            "participation_valve_attempts": participation_attempts[:10],
            "participation_valve_entries": participation_entries,
            "participation_valve_entries_count": len(participation_entries),
            "top_candidates": [{"symbol": c.get("symbol"), "score": c.get("score"), "rank_score": c.get("core_entry_rank_score")} for c in candidates[:10]],
        }
    except Exception:
        pass
    return entries, rotations, blocked_entries


def _patch(core: Any) -> bool:
    if core is None or not (ENABLED and PATCH_ENABLED and _paper_context()):
        return False
    current = getattr(core, "try_entries_and_rotations", None)
    if callable(current) and getattr(current, "_core_entry_pipeline_version", None) == VERSION:
        return False

    def try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        return _core_try_entries_and_rotations(core, long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

    try_entries_and_rotations._core_entry_pipeline_non_wrapper_patched = True  # type: ignore[attr-defined]
    try_entries_and_rotations._core_entry_pipeline_version = VERSION  # type: ignore[attr-defined]
    core.try_entries_and_rotations = try_entries_and_rotations
    PATCHED_MODULE_IDS.add(id(core))
    return True


def _is_patched(core: Any) -> bool:
    try:
        return bool(getattr(getattr(core, "try_entries_and_rotations", None), "_core_entry_pipeline_non_wrapper_patched", False))
    except Exception:
        return False


def _policy() -> Dict[str, Any]:
    return {
        "enabled": bool(ENABLED),
        "patch_enabled": bool(PATCH_ENABLED),
        "paper_only": bool(PAPER_ONLY),
        "non_wrapper_replacement": True,
        "calls_prior_try_entries": False,
        "best_of_cycle_enabled": bool(BEST_OF_CYCLE_ENABLED),
        "max_not_selected_rows": MAX_NOT_SELECTED_ROWS,
        "participation_valve_enabled": bool(PARTICIPATION_VALVE_ENABLED),
        "participation_valve_max_entries_per_day": PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY,
        "participation_valve_max_entries_per_cycle": PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE,
        "participation_valve_max_reviewed_rank": PARTICIPATION_VALVE_MAX_REVIEWED_RANK,
        "participation_valve_alloc_factor": PARTICIPATION_VALVE_ALLOC_FACTOR,
        "participation_valve_min_raw_score": PARTICIPATION_VALVE_MIN_RAW_SCORE,
        "participation_valve_min_rank_score": PARTICIPATION_VALVE_MIN_RANK_SCORE,
        "participation_valve_max_score_gap": PARTICIPATION_VALVE_MAX_SCORE_GAP,
        "participation_valve_allowed_modes": sorted(PARTICIPATION_VALVE_ALLOWED_MODES),
        "participation_valve_allowed_quality_reasons": sorted(PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS),
        "participation_valve_blocks_extension_or_chase": True,
        "participation_valve_calls_entry_quality_check_first": True,
        "participation_valve_limited_score_floor_exception": True,
        "profit_guard_sleeve_enabled": bool(PROFIT_GUARD_SLEEVE_ENABLED),
        "profit_guard_sleeve_max_entries_per_day": PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY,
        "profit_guard_sleeve_alloc_factor": PROFIT_GUARD_SLEEVE_ALLOC_FACTOR,
        "profit_guard_sleeve_min_score": PROFIT_GUARD_SLEEVE_MIN_SCORE,
        "profit_guard_sleeve_allowed_modes": sorted(PROFIT_GUARD_SLEEVE_ALLOWED_MODES),
        "hard_profit_lock_still_blocks": True,
        "giveback_lock_still_blocks": True,
        "does_not_raise_max_positions": True,
        "does_not_bypass_cooldowns": True,
        "does_not_bypass_self_defense_or_risk_halt": True,
        "does_not_bypass_extension_guard": True,
        "does_not_lower_global_score_thresholds": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    latest = {}
    if core is not None:
        try:
            latest = _portfolio(core).get("core_entry_pipeline") or {}
        except Exception:
            latest = {}
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "core_entry_pipeline_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "patched_try_entries": bool(_is_patched(core)) if core is not None else False,
        "latest": latest if isinstance(latest, dict) else {},
        "policy": _policy(),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    patched = _patch(core) if core is not None else False
    payload = status_payload(core)
    payload["patched_this_call"] = {"try_entries_and_rotations": bool(patched)}
    return payload


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


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

    if "/paper/core-entry-pipeline-status" not in existing:
        flask_app.add_url_rule("/paper/core-entry-pipeline-status", "core_entry_pipeline_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
