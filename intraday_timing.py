"""Intraday adaptive timing guard.

Purpose:
- Keep the account available for intraday trading.
- Stop the bot from chasing extended 5-minute momentum.
- Keep the 5-minute MA20 as a chase-prevention / pullback-reclaim guard.
- Add adaptive confirmation using VWAP reclaim, 9 EMA momentum hold, 15-minute trend,
  and ATR-based extension checks.
- Preserve EOD allocation as the larger/full-size decision layer.

This is implemented as a startup patch so it can be layered onto the existing
app.py without a risky full rewrite on mobile.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, List, Tuple

VERSION = "intraday-adaptive-timing-2026-05-13"

CACHE_TTL_SECONDS = float(os.environ.get("INTRADAY_TIMING_CACHE_TTL_SECONDS", "75"))

# Legacy 5-minute MA20 chase guard. This remains the primary no-chase reference.
MAX_ABOVE_5M_MA20 = float(os.environ.get("INTRADAY_TIMING_MAX_ABOVE_5M_MA20", "0.006"))
MAX_ABOVE_15M_MA20 = float(os.environ.get("INTRADAY_TIMING_MAX_ABOVE_15M_MA20", "0.014"))
MAX_FROM_DAY_OPEN = float(os.environ.get("INTRADAY_TIMING_MAX_FROM_DAY_OPEN", "0.035"))
RECLAIM_LOOKBACK_BARS = int(os.environ.get("INTRADAY_TIMING_RECLAIM_LOOKBACK_BARS", "8"))
MIN_15M_SLOPE_PCT = float(os.environ.get("INTRADAY_TIMING_MIN_15M_SLOPE_PCT", "0.0005"))
EOD_WINDOW_MINUTES = int(os.environ.get("EOD_ALLOCATION_WINDOW_MINUTES", os.environ.get("INTRADAY_TIMING_EOD_WINDOW_MINUTES", "45")))

# Adaptive timing additions. These allow the bot to compare entry timing paths instead of
# using 5m MA20 as the only trigger. The rules still block obvious chase entries.
VWAP_RECLAIM_MAX_ABOVE = float(os.environ.get("INTRADAY_TIMING_VWAP_RECLAIM_MAX_ABOVE", "0.008"))
EMA9_HOLD_MAX_BELOW = float(os.environ.get("INTRADAY_TIMING_EMA9_HOLD_MAX_BELOW", "0.0025"))
EMA9_HOLD_MAX_ABOVE_5M_MA20 = float(os.environ.get("INTRADAY_TIMING_EMA9_HOLD_MAX_ABOVE_5M_MA20", "0.010"))
ATR_PERIOD = int(os.environ.get("INTRADAY_TIMING_ATR_PERIOD", "14"))
MAX_ATR_EXTENSION = float(os.environ.get("INTRADAY_TIMING_MAX_ATR_EXTENSION", "1.25"))
CATALYST_MAX_ATR_EXTENSION = float(os.environ.get("INTRADAY_TIMING_CATALYST_MAX_ATR_EXTENSION", "1.65"))
MIN_METHODS_FOR_FULL_CONFIRMATION = int(os.environ.get("INTRADAY_TIMING_MIN_METHODS_FOR_FULL_CONFIRMATION", "1"))

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


def _session_df(df: Any) -> Any:
    """Return only the latest regular/intraday session when the index supports dates."""
    if df is None:
        return df
    try:
        if len(df) == 0:
            return df
        idx = df.index
        last_date = idx[-1].date()
        mask = [getattr(x, "date", lambda: None)() == last_date for x in idx]
        session = df.loc[mask]
        return session if len(session) else df
    except Exception:
        return df


def _sma(series: Any, n: int) -> float:
    try:
        if series is None or len(series) < n:
            return 0.0
        return _float(series.tail(n).mean(), 0.0)
    except Exception:
        return 0.0


def _ema(series: Any, n: int) -> float:
    try:
        if series is None or len(series) < n:
            return 0.0
        return _float(series.ewm(span=n, adjust=False).mean().iloc[-1], 0.0)
    except Exception:
        return 0.0


def _vwap(df: Any) -> float:
    try:
        if df is None or len(df) == 0:
            return 0.0
        high = _col(df, "High")
        low = _col(df, "Low")
        close = _col(df, "Close")
        volume = _col(df, "Volume")
        if high is None or low is None or close is None or volume is None:
            return 0.0
        typical = (high + low + close) / 3.0
        denom = volume.cumsum().iloc[-1]
        if _float(denom, 0.0) <= 0:
            return 0.0
        return _float((typical * volume).cumsum().iloc[-1] / denom, 0.0)
    except Exception:
        return 0.0


def _atr(df: Any, n: int = ATR_PERIOD) -> float:
    try:
        if df is None or len(df) < n + 1:
            return 0.0
        high = _col(df, "High")
        low = _col(df, "Low")
        close = _col(df, "Close")
        if high is None or low is None or close is None:
            return 0.0
        prev_close = close.shift(1)
        tr = (high - low).abs()
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = tr.combine(tr2, max).combine(tr3, max)
        return _float(true_range.tail(n).mean(), 0.0)
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


def _safe_pct(numerator: float, denominator: float) -> float | None:
    if not numerator or not denominator:
        return None
    try:
        return numerator / denominator - 1.0
    except Exception:
        return None


def _pct_text(x: float | None) -> float | None:
    return round(x * 100, 3) if x is not None else None


def _pullback_reclaim_profile(module: Any, symbol: str) -> Dict[str, Any]:
    cache_key = f"{symbol.upper()}:{int(time.time() // CACHE_TTL_SECONDS)}"
    cached = _TIMING_CACHE.get(cache_key)
    if cached:
        return dict(cached[1])

    raw5 = _download(module, symbol, "2d", "5m")
    raw15 = _download(module, symbol, "5d", "15m")
    df5 = _session_df(raw5)
    df15 = raw15

    close5 = _col(df5, "Close")
    high5 = _col(df5, "High")
    low5 = _col(df5, "Low")
    close15 = _col(df15, "Close")

    price = _last(close5)
    ma5_20 = _sma(close5, 20)
    ma5_8 = _sma(close5, 8)
    ema5_9 = _ema(close5, 9)
    session_vwap = _vwap(df5)
    atr5 = _atr(df5, ATR_PERIOD)

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

    above_5m_ma20_pct = _safe_pct(price, ma5_20)
    above_15m_ma20_pct = _safe_pct(price, ma15_20)
    above_vwap_pct = _safe_pct(price, session_vwap)
    above_ema9_pct = _safe_pct(price, ema5_9)
    from_day_open_pct = _safe_pct(price, first_open)
    ma15_slope_pct = _safe_pct(ma15_8, ma15_20)
    atr_extension = ((price - ma5_20) / atr5) if price and ma5_20 and atr5 else None

    # Confirmation layer: the larger trend must agree. 5m MA20 is no longer the
    # only acceptable trigger, but the 15m trend keeps the starter from fighting tape.
    confirmed_15m = bool(price and ma15_8 and ma15_20 and price >= ma15_8 and ma15_8 >= ma15_20 * (1.0 + MIN_15M_SLOPE_PCT))
    not_too_extended_15m = bool(above_15m_ma20_pct is None or above_15m_ma20_pct <= MAX_ABOVE_15M_MA20)
    not_chasing_day_move = bool(from_day_open_pct is None or from_day_open_pct <= MAX_FROM_DAY_OPEN)

    # ATR extension control. Catalyst names can get slightly more room, but no rule
    # gets unlimited chase authority.
    atr_ok_standard = bool(atr_extension is None or atr_extension <= MAX_ATR_EXTENSION)
    atr_ok_catalyst_room = bool(atr_extension is None or atr_extension <= CATALYST_MAX_ATR_EXTENSION)

    # Method 1: classic 5m MA20 pullback/reclaim.
    touched_ma20 = bool(ma5_20 and recent_low and recent_low <= ma5_20 * (1.0 + MAX_ABOVE_5M_MA20))
    reclaimed_ma20 = bool(price and ma5_20 and price >= ma5_20 and (above_5m_ma20_pct is None or above_5m_ma20_pct <= MAX_ABOVE_5M_MA20))
    ma20_reclaim = bool(touched_ma20 and reclaimed_ma20 and atr_ok_standard)

    # Method 2: VWAP pullback/reclaim. Useful when price respects VWAP better than MA20.
    touched_vwap = bool(session_vwap and recent_low and recent_low <= session_vwap * (1.0 + VWAP_RECLAIM_MAX_ABOVE))
    reclaimed_vwap = bool(price and session_vwap and price >= session_vwap and (above_vwap_pct is None or above_vwap_pct <= VWAP_RECLAIM_MAX_ABOVE))
    vwap_reclaim = bool(touched_vwap and reclaimed_vwap and atr_ok_standard)

    # Method 3: 9 EMA momentum hold. This is the risk-on starter valve for strong trends.
    # It still requires 15m trend confirmation and ATR control, so it should not become
    # a blind breakout chase.
    recent_held_ema9 = bool(ema5_9 and recent_low and recent_low >= ema5_9 * (1.0 - EMA9_HOLD_MAX_BELOW))
    price_holds_ema9 = bool(price and ema5_9 and price >= ema5_9)
    not_far_above_ma20_for_ema = bool(above_5m_ma20_pct is None or above_5m_ma20_pct <= EMA9_HOLD_MAX_ABOVE_5M_MA20)
    ema9_momentum_hold = bool(recent_held_ema9 and price_holds_ema9 and not_far_above_ma20_for_ema and atr_ok_catalyst_room)

    methods = {
        "5m_ma20_pullback_reclaim": ma20_reclaim,
        "vwap_reclaim": vwap_reclaim,
        "ema9_momentum_hold": ema9_momentum_hold,
    }
    confirmed_methods = [name for name, ok in methods.items() if ok]
    enough_methods = len(confirmed_methods) >= max(1, MIN_METHODS_FOR_FULL_CONFIRMATION)

    allowed = bool(confirmed_15m and not_too_extended_15m and not_chasing_day_move and enough_methods)

    reasons: List[str] = []
    if not confirmed_15m:
        reasons.append("15m_trend_not_confirmed")
    if not not_too_extended_15m:
        reasons.append("too_far_above_15m_ma20")
    if not not_chasing_day_move:
        reasons.append("too_extended_from_day_open")
    if not enough_methods:
        reasons.append("waiting_for_pullback_reclaim_or_ema9_hold")
    if not ma20_reclaim and above_5m_ma20_pct is not None and above_5m_ma20_pct > MAX_ABOVE_5M_MA20:
        reasons.append("above_5m_ma20_without_reclaim")
    if not vwap_reclaim and above_vwap_pct is not None and above_vwap_pct > VWAP_RECLAIM_MAX_ABOVE:
        reasons.append("above_vwap_without_reclaim")
    if atr_extension is not None and atr_extension > CATALYST_MAX_ATR_EXTENSION:
        reasons.append("atr_extension_too_high")

    profile = {
        "symbol": symbol.upper(),
        "allowed": allowed,
        "reasons": reasons or ["adaptive_timing_confirmed"],
        "selected_methods": confirmed_methods,
        "method_checks": methods,
        "price": round(price, 4) if price else None,
        "ma5_20": round(ma5_20, 4) if ma5_20 else None,
        "ma5_8": round(ma5_8, 4) if ma5_8 else None,
        "ema5_9": round(ema5_9, 4) if ema5_9 else None,
        "vwap": round(session_vwap, 4) if session_vwap else None,
        "atr5": round(atr5, 4) if atr5 else None,
        "ma15_20": round(ma15_20, 4) if ma15_20 else None,
        "ma15_8": round(ma15_8, 4) if ma15_8 else None,
        "above_5m_ma20_pct": _pct_text(above_5m_ma20_pct),
        "above_15m_ma20_pct": _pct_text(above_15m_ma20_pct),
        "above_vwap_pct": _pct_text(above_vwap_pct),
        "above_ema9_pct": _pct_text(above_ema9_pct),
        "from_day_open_pct": _pct_text(from_day_open_pct),
        "ma15_slope_pct": _pct_text(ma15_slope_pct),
        "atr_extension": round(atr_extension, 3) if atr_extension is not None else None,
        "recent_low": round(recent_low, 4) if recent_low else None,
        "recent_high": round(recent_high, 4) if recent_high else None,
        "rule": "adaptive_5m_ma20_vwap_ema9_15m_atr",
        "interpretation": "5m MA20 remains the chase guard; VWAP/EMA9 can confirm safer risk-on starters when 15m trend and ATR extension agree.",
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
        out["adaptive_timing"] = out.get("adaptive_timing") or {}
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
                            blocked = _block_like(result, "intraday_adaptive_timing_guard:" + str(decision.get("reason", "blocked")))
                            if isinstance(blocked, dict):
                                blocked["adaptive_timing"] = decision
                            return blocked
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
        "strategy": "adaptive_5m_ma20_vwap_ema9_15m_atr; 5m MA20 remains chase guard, not standalone signal",
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
            "primary_role": "5m MA20 is used as a chase-prevention / pullback-reclaim guard, not as a standalone buy signal.",
            "adaptive_methods": [
                "5m_ma20_pullback_reclaim",
                "vwap_reclaim",
                "ema9_momentum_hold",
                "15m_trend_confirmation",
                "atr_extension_guard",
            ],
            "max_above_5m_ma20_pct": MAX_ABOVE_5M_MA20 * 100,
            "max_above_15m_ma20_pct": MAX_ABOVE_15M_MA20 * 100,
            "max_from_day_open_pct": MAX_FROM_DAY_OPEN * 100,
            "vwap_reclaim_max_above_pct": VWAP_RECLAIM_MAX_ABOVE * 100,
            "ema9_hold_max_below_pct": EMA9_HOLD_MAX_BELOW * 100,
            "ema9_hold_max_above_5m_ma20_pct": EMA9_HOLD_MAX_ABOVE_5M_MA20 * 100,
            "atr_period": ATR_PERIOD,
            "max_atr_extension": MAX_ATR_EXTENSION,
            "catalyst_max_atr_extension": CATALYST_MAX_ATR_EXTENSION,
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
