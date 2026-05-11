"""Intraday timing guard.

Purpose:
- Keep the account available for intraday trading.
- Stop the bot from chasing extended 5-minute momentum.
- Require pullback/reclaim + 15-minute trend confirmation before new longs.
- Keep tech-heavy exposure allowed; this module does not impose a tech cap.
- Preserve EOD allocation as the larger/full-size decision layer.

This is implemented as a startup patch so it can be layered onto the existing
app.py without a risky full rewrite on mobile.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, List, Tuple

VERSION = "intraday-timing-pullback-guard-2026-05-11"

CACHE_TTL_SECONDS = float(os.environ.get("INTRADAY_TIMING_CACHE_TTL_SECONDS", "75"))
MAX_ABOVE_5M_MA20 = float(os.environ.get("INTRADAY_TIMING_MAX_ABOVE_5M_MA20", "0.006"))
MAX_ABOVE_15M_MA20 = float(os.environ.get("INTRADAY_TIMING_MAX_ABOVE_15M_MA20", "0.014"))
MAX_FROM_DAY_OPEN = float(os.environ.get("INTRADAY_TIMING_MAX_FROM_DAY_OPEN", "0.035"))
RECLAIM_LOOKBACK_BARS = int(os.environ.get("INTRADAY_TIMING_RECLAIM_LOOKBACK_BARS", "8"))
MIN_15M_SLOPE_PCT = float(os.environ.get("INTRADAY_TIMING_MIN_15M_SLOPE_PCT", "0.0005"))
EOD_WINDOW_MINUTES = int(os.environ.get("EOD_ALLOCATION_WINDOW_MINUTES", os.environ.get("INTRADAY_TIMING_EOD_WINDOW_MINUTES", "45")))

# Runtime overrides. These are intentionally conservative for intraday starters.
OVERRIDES = {
    "MAX_NEW_ENTRIES_PER_CYCLE": ("min", 1),
    "CONTROLLED_PULLBACK_ALLOC_FACTOR": ("min", 0.25),
    "CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN": ("max", 75),
    "CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY": ("min", 1),
    "CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER": ("set", True),
    "CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT": ("set", True),
    "CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY": ("set", True),
    "PULLBACK_MAX_ABOVE_MA20": ("min", 0.006),
    "EXTENSION_MAX_FROM_MA20": ("min", 0.012),
    "EXTENSION_MAX_ABOVE_DAY_OPEN": ("min", 0.035),
    "FUTURES_GAP_UP_CHASE_PCT": ("min", 0.006),
    "POST_STOP_SCORE_BUMP": ("max", 0.008),
    "POST_STOP_EXCEPTIONAL_SCORE": ("max", 0.040),
    "POST_STOP_REQUIRE_SECTOR_LEADER": ("set", True),
}

_REGISTERED_APP_IDS: set[int] = set()
_TIMING_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_LAST_DECISIONS: List[Dict[str, Any]] = []
_APPLIED_OVERRIDES: Dict[str, Any] = {}
_WRAPPED = False


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _last(series: Any, default: float = 0.0) -> float:
    try:
        if series is None or len(series) == 0:
            return default
        return _float(series.iloc[-1], default)
    except Exception:
        try:
            return _float(series[-1], default)
        except Exception:
            return default


def _col(df: Any, name: str) -> Any:
    if df is None:
        return None
    try:
        if name in df.columns:
            return df[name]
    except Exception:
        pass
    # yfinance can sometimes return a MultiIndex even for one ticker.
    try:
        for c in df.columns:
            if isinstance(c, tuple) and str(c[0]).lower() == name.lower():
                return df[c]
            if isinstance(c, tuple) and str(c[-1]).lower() == name.lower():
                return df[c]
    except Exception:
        pass
    return None


def _sma(series: Any, n: int) -> float:
    try:
        if series is None or len(series) < n:
            return 0.0
        return _float(series.tail(n).mean(), 0.0)
    except Exception:
        return 0.0


def _download(module: Any, symbol: str, period: str, interval: str) -> Any:
    try:
        return module.download_prices(symbol, period=period, interval=interval)
    except TypeError:
        try:
            return module.download_prices(symbol, period, interval)
        except Exception:
            return None
    except Exception:
        return None


def _market_clock(module: Any) -> Dict[str, Any]:
    for name in ("market_clock", "get_market_clock", "market_clock_snapshot"):
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                obj = fn()
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    # Fallback based on app config.
    try:
        now = module.now_local()
        open_dt = now.replace(hour=getattr(module, "REGULAR_OPEN_HOUR", 8), minute=getattr(module, "REGULAR_OPEN_MINUTE", 30), second=0, microsecond=0)
        close_dt = now.replace(hour=getattr(module, "REGULAR_CLOSE_HOUR", 15), minute=getattr(module, "REGULAR_CLOSE_MINUTE", 0), second=0, microsecond=0)
        return {
            "is_open": open_dt <= now <= close_dt,
            "minutes_since_open": max(0.0, (now - open_dt).total_seconds() / 60.0),
            "minutes_to_close": max(0.0, (close_dt - now).total_seconds() / 60.0),
            "reason": "fallback_clock",
        }
    except Exception:
        return {"is_open": True, "minutes_since_open": None, "minutes_to_close": None, "reason": "clock_unavailable"}


def in_eod_window(module: Any) -> bool:
    clock = _market_clock(module)
    mtc = clock.get("minutes_to_close")
    return bool(clock.get("is_open") and mtc is not None and _float(mtc, 9999.0) <= EOD_WINDOW_MINUTES)


def _append_decision(decision: Dict[str, Any]) -> None:
    decision = dict(decision)
    decision.setdefault("generated_local", _now_text())
    _LAST_DECISIONS.append(decision)
    del _LAST_DECISIONS[:-50]


def _pullback_reclaim_profile(module: Any, symbol: str) -> Dict[str, Any]:
    cache_key = f"{symbol.upper()}:{int(time.time() // CACHE_TTL_SECONDS)}"
    cached = _TIMING_CACHE.get(cache_key)
    if cached:
        return dict(cached[1])

    df5 = _download(module, symbol, "2d", "5m")
    df15 = _download(module, symbol, "5d", "15m")
    close5 = _col(df5, "Close")
    high5 = _col(df5, "High")
    low5 = _col(df5, "Low")
    close15 = _col(df15, "Close")

    price = _last(close5)
    ma5_20 = _sma(close5, 20)
    ma5_8 = _sma(close5, 8)
    ma15_20 = _sma(close15, 20)
    ma15_8 = _sma(close15, 8)
    first_open = 0.0
    try:
        open5 = _col(df5, "Open")
        first_open = _float(open5.iloc[0], 0.0) if open5 is not None and len(open5) else 0.0
    except Exception:
        first_open = 0.0

    recent_low = 0.0
    recent_high = 0.0
    try:
        recent_low = _float(low5.tail(RECLAIM_LOOKBACK_BARS).min(), 0.0) if low5 is not None else 0.0
        recent_high = _float(high5.tail(RECLAIM_LOOKBACK_BARS).max(), 0.0) if high5 is not None else 0.0
    except Exception:
        pass

    above_5m_ma20_pct = (price / ma5_20 - 1.0) if price and ma5_20 else None
    above_15m_ma20_pct = (price / ma15_20 - 1.0) if price and ma15_20 else None
    from_day_open_pct = (price / first_open - 1.0) if price and first_open else None
    ma15_slope_pct = (ma15_8 / ma15_20 - 1.0) if ma15_8 and ma15_20 else None

    touched_or_undercut_ma20 = bool(ma5_20 and recent_low and recent_low <= ma5_20 * (1.0 + MAX_ABOVE_5M_MA20))
    reclaimed_5m_ma20 = bool(price and ma5_20 and price >= ma5_20 and (above_5m_ma20_pct is None or above_5m_ma20_pct <= MAX_ABOVE_5M_MA20))
    confirmed_15m = bool(price and ma15_8 and ma15_20 and price >= ma15_8 and ma15_8 >= ma15_20 * (1.0 + MIN_15M_SLOPE_PCT))
    not_too_extended_15m = bool(above_15m_ma20_pct is None or above_15m_ma20_pct <= MAX_ABOVE_15M_MA20)
    not_chasing_day_move = bool(from_day_open_pct is None or from_day_open_pct <= MAX_FROM_DAY_OPEN)

    allowed = bool(touched_or_undercut_ma20 and reclaimed_5m_ma20 and confirmed_15m and not_too_extended_15m and not_chasing_day_move)
    reasons: List[str] = []
    if not touched_or_undercut_ma20:
        reasons.append("no_recent_pullback_to_5m_ma20")
    if not reclaimed_5m_ma20:
        reasons.append("not_reclaimed_5m_ma20_or_still_extended")
    if not confirmed_15m:
        reasons.append("15m_trend_not_confirmed")
    if not not_too_extended_15m:
        reasons.append("too_far_above_15m_ma20")
    if not not_chasing_day_move:
        reasons.append("too_extended_from_day_open")

    profile = {
        "symbol": symbol.upper(),
        "allowed": allowed,
        "reasons": reasons or ["pullback_reclaim_and_15m_confirmed"],
        "price": round(price, 4) if price else None,
        "ma5_20": round(ma5_20, 4) if ma5_20 else None,
        "ma15_20": round(ma15_20, 4) if ma15_20 else None,
        "above_5m_ma20_pct": round(above_5m_ma20_pct * 100, 3) if above_5m_ma20_pct is not None else None,
        "above_15m_ma20_pct": round(above_15m_ma20_pct * 100, 3) if above_15m_ma20_pct is not None else None,
        "from_day_open_pct": round(from_day_open_pct * 100, 3) if from_day_open_pct is not None else None,
        "ma15_slope_pct": round(ma15_slope_pct * 100, 3) if ma15_slope_pct is not None else None,
        "recent_low": round(recent_low, 4) if recent_low else None,
        "recent_high": round(recent_high, 4) if recent_high else None,
        "rule": "wait_for_pullback_reclaim_5m_plus_15m_confirmation",
    }
    _TIMING_CACHE[cache_key] = (time.time(), profile)
    return dict(profile)


def timing_decision(module: Any, symbol: str, side: str = "long") -> Dict[str, Any]:
    side = (side or "long").lower()
    if side != "long":
        return {"allowed": True, "symbol": symbol, "side": side, "reason": "non_long_side_not_timing_blocked"}
    if in_eod_window(module):
        return {"allowed": True, "symbol": symbol, "side": side, "reason": "eod_window_allows_allocator_decision"}
    profile = _pullback_reclaim_profile(module, symbol)
    decision = dict(profile)
    decision["side"] = side
    decision["reason"] = ",".join(profile.get("reasons", []))
    return decision


def _extract_symbol_side(args: tuple, kwargs: dict) -> Tuple[str | None, str]:
    symbol = kwargs.get("symbol") or kwargs.get("ticker")
    side = kwargs.get("side", "long")
    for arg in args:
        if symbol is None and isinstance(arg, str) and 1 <= len(arg) <= 8:
            symbol = arg
        elif isinstance(arg, str) and arg.lower() in ("long", "short"):
            side = arg.lower()
    return (str(symbol).upper() if symbol else None, str(side).lower())


def _result_allows(result: Any) -> bool:
    if isinstance(result, bool):
        return bool(result)
    if isinstance(result, dict):
        for key in ("allowed", "ok", "pass", "passes", "entry_allowed"):
            if key in result:
                return bool(result.get(key))
        if "blocked" in result:
            return not bool(result.get("blocked"))
        return True
    if isinstance(result, tuple) and result:
        if isinstance(result[0], bool):
            return bool(result[0])
    return True


def _block_like(result: Any, reason: str) -> Any:
    if isinstance(result, bool):
        return False
    if isinstance(result, tuple) and result:
        values = list(result)
        if isinstance(values[0], bool):
            values[0] = False
            if len(values) >= 2:
                values[1] = reason
            else:
                values.append(reason)
            return tuple(values)
    if isinstance(result, dict):
        out = dict(result)
        out["allowed"] = False
        out["ok"] = False
        out["blocked"] = True
        prior = str(out.get("reason") or out.get("block_reason") or "").strip()
        out["reason"] = f"{prior},{reason}".strip(",") if prior else reason
        out["block_reason"] = out["reason"]
        return out
    return result


def apply_runtime_overrides(module: Any) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    for name, (mode, value) in OVERRIDES.items():
        try:
            old = getattr(module, name, None)
            new = value
            if old is not None:
                if mode == "min":
                    new = min(old, value)
                elif mode == "max":
                    new = max(old, value)
                elif mode == "set":
                    new = value
            setattr(module, name, new)
            applied[name] = {"old": old, "new": new, "mode": mode, "applied": True}
        except Exception as exc:
            applied[name] = {"new": value, "mode": mode, "applied": False, "error": str(exc)}
    # Update bucket config in-place if present. Keep tech exposure allowed, but make intraday starters smaller.
    try:
        bucket_config = getattr(module, "BUCKET_CONFIG", {})
        if isinstance(bucket_config, dict):
            for bucket in ("small_cap_momentum", "bitcoin_ai_compute", "data_center_infra", "semi_leaders", "cloud_cyber_software"):
                cfg = bucket_config.get(bucket)
                if isinstance(cfg, dict):
                    old = cfg.get("alloc_factor")
                    cfg["alloc_factor"] = min(float(old or 1.0), 0.20)
                    applied[f"BUCKET_CONFIG.{bucket}.alloc_factor"] = {"old": old, "new": cfg["alloc_factor"], "mode": "min", "applied": True}
    except Exception as exc:
        applied["BUCKET_CONFIG"] = {"applied": False, "error": str(exc)}
    _APPLIED_OVERRIDES.clear()
    _APPLIED_OVERRIDES.update(applied)
    return applied


def _wrap_entry_quality(module: Any) -> None:
    global _WRAPPED
    if _WRAPPED:
        return
    for fn_name in ("entry_quality_check", "controlled_pullback_entry_check"):
        fn = getattr(module, fn_name, None)
        if callable(fn) and not getattr(fn, "_intraday_timing_wrapped", False):
            def make_wrapper(__fn, __name):
                def wrapper(*args, **kwargs):
                    result = __fn(*args, **kwargs)
                    try:
                        if not _result_allows(result):
                            return result
                        symbol, side = _extract_symbol_side(args, kwargs)
                        if not symbol:
                            return result
                        decision = timing_decision(module, symbol, side)
                        decision["hook"] = __name
                        _append_decision(decision)
                        if not decision.get("allowed", True):
                            return _block_like(result, "intraday_timing_guard:" + str(decision.get("reason", "blocked")))
                    except Exception as exc:
                        _append_decision({"hook": __name, "allowed": True, "error": str(exc), "reason": "guard_error_allowed"})
                    return result
                wrapper._intraday_timing_wrapped = True
                return wrapper
            setattr(module, fn_name, make_wrapper(fn, fn_name))

    # Last safety net: if a path bypasses entry_quality_check, do not place a new long that fails timing.
    fn = getattr(module, "enter_position", None)
    if callable(fn) and not getattr(fn, "_intraday_timing_wrapped", False):
        def enter_wrapper(*args, **kwargs):
            try:
                symbol, side = _extract_symbol_side(args, kwargs)
                if symbol:
                    decision = timing_decision(module, symbol, side)
                    decision["hook"] = "enter_position"
                    _append_decision(decision)
                    if not decision.get("allowed", True):
                        # Return None to avoid pretending a trade was placed.
                        return None
            except Exception as exc:
                _append_decision({"hook": "enter_position", "allowed": True, "error": str(exc), "reason": "guard_error_allowed"})
            return fn(*args, **kwargs)
        enter_wrapper._intraday_timing_wrapped = True
        setattr(module, "enter_position", enter_wrapper)
    _WRAPPED = True


def apply(module: Any) -> Dict[str, Any]:
    applied = apply_runtime_overrides(module)
    _wrap_entry_quality(module)
    try:
        setattr(module, "INTRADAY_TIMING_GUARD_VERSION", VERSION)
    except Exception:
        pass
    return {
        "status": "ok",
        "type": "intraday_timing_apply",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "applied_runtime_overrides": applied,
        "strategy": "pullback_reclaim_5m_plus_15m_confirmation; tech-heavy exposure still allowed",
    }


def status_payload(module: Any | None = None) -> Dict[str, Any]:
    payload = {
        "status": "ok",
        "type": "intraday_timing_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "cache_size": len(_TIMING_CACHE),
        "applied_runtime_overrides": _APPLIED_OVERRIDES,
        "settings": {
            "max_above_5m_ma20_pct": MAX_ABOVE_5M_MA20 * 100,
            "max_above_15m_ma20_pct": MAX_ABOVE_15M_MA20 * 100,
            "max_from_day_open_pct": MAX_FROM_DAY_OPEN * 100,
            "reclaim_lookback_bars": RECLAIM_LOOKBACK_BARS,
            "min_15m_slope_pct": MIN_15M_SLOPE_PCT * 100,
            "eod_window_minutes": EOD_WINDOW_MINUTES,
        },
        "latest_decisions": _LAST_DECISIONS[-20:],
        "normal_test_link": "https://trading-bot-clean.up.railway.app/paper/self-check",
        "note": "Use only /paper/self-check for routine testing; this status is included in the one-link check.",
    }
    try:
        if module is not None:
            payload["market_clock"] = _market_clock(module)
            payload["in_eod_window"] = in_eod_window(module)
            state = module.load_state() if hasattr(module, "load_state") else {}
            positions = state.get("positions", {}) if isinstance(state, dict) else {}
            payload["open_positions"] = list(positions.keys()) if isinstance(positions, dict) else []
    except Exception as exc:
        payload["state_error"] = str(exc)
    return payload


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if module is not None:
        try:
            apply(module)
        except Exception:
            pass
    if "/paper/intraday-timing-status" not in existing:
        flask_app.add_url_rule("/paper/intraday-timing-status", "intraday_timing_status", lambda: jsonify(status_payload(module)))
    _REGISTERED_APP_IDS.add(id(flask_app))
