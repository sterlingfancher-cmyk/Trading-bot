"""Opening range FVG guard for the Railway trading bot.

This module is intentionally side-effect light. It can be imported by an
import-time patch hook and attached to the existing single-file app without a
large app.py rewrite.

Default behavior is PILOT mode: compute decisions, annotate signals, and log
scanner audit details, but do not block entries unless OR_FVG_GUARD_PILOT=false.
"""

import os
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def env_bool(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).lower() not in ["0", "false", "no", "off"]


OR_FVG_GUARD_ENABLED = env_bool("OR_FVG_GUARD_ENABLED", "true")
OR_FVG_GUARD_PILOT = env_bool("OR_FVG_GUARD_PILOT", "true")
OR_FVG_GUARD_EARLY_MINUTES = int(os.environ.get("OR_FVG_GUARD_EARLY_MINUTES", "45"))
OR_FVG_OPENING_RANGE_MINUTES = int(os.environ.get("OR_FVG_OPENING_RANGE_MINUTES", "15"))
OR_FVG_MIN_GAP_PCT = float(os.environ.get("OR_FVG_MIN_GAP_PCT", "0.0010"))
OR_FVG_EMA_FAST = int(os.environ.get("OR_FVG_EMA_FAST", "8"))
OR_FVG_EMA_SLOW = int(os.environ.get("OR_FVG_EMA_SLOW", "20"))
OR_FVG_LOG_LIMIT = int(os.environ.get("OR_FVG_LOG_LIMIT", "120"))


def _clean(values: Any) -> np.ndarray:
    arr = np.asarray(values).astype(float).flatten()
    return arr[~np.isnan(arr)]


def _series_from_df(df: pd.DataFrame, column: str) -> np.ndarray:
    if df is None or getattr(df, "empty", True):
        return np.array([])
    try:
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            matches = [c for c in df.columns if c[0] == column or c[-1] == column]
            if matches:
                return _clean(df[matches[0]].values)
    except Exception:
        pass
    if column not in df:
        return np.array([])
    return _clean(df[column].values)


def _ema(values: np.ndarray, span: int) -> Optional[float]:
    values = _clean(values)
    if len(values) < max(2, span):
        return None
    alpha = 2.0 / (span + 1.0)
    ema = float(values[0])
    for val in values[1:]:
        ema = (alpha * float(val)) + ((1.0 - alpha) * ema)
    return float(ema)


def _vwap(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray) -> Optional[float]:
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n <= 0:
        return None
    h = highs[-n:]
    l = lows[-n:]
    c = closes[-n:]
    v = volumes[-n:]
    volume_sum = float(np.sum(v))
    if volume_sum <= 0:
        return None
    typical = (h + l + c) / 3.0
    return float(np.sum(typical * v) / volume_sum)


def _session_start_index(df: pd.DataFrame, market_tz: Any, open_hour: int, open_minute: int) -> int:
    if df is None or getattr(df, "empty", True) or not hasattr(df, "index"):
        return 0
    try:
        idx = df.index
        if getattr(idx, "tz", None) is None:
            local_idx = idx.tz_localize("UTC").tz_convert(market_tz)
        else:
            local_idx = idx.tz_convert(market_tz)
        last_day = local_idx[-1].date()
        open_dt = datetime.datetime.combine(last_day, datetime.time(open_hour, open_minute))
        open_dt = market_tz.localize(open_dt) if getattr(open_dt, "tzinfo", None) is None else open_dt
        positions = np.where(local_idx >= open_dt)[0]
        if len(positions) > 0:
            return int(positions[0])
    except Exception:
        pass
    return max(0, len(df) - 78)


def _aggregate_15m(opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray) -> Dict[str, np.ndarray]:
    n = min(len(opens), len(highs), len(lows), len(closes), len(volumes))
    if n < 3:
        return {"open": np.array([]), "high": np.array([]), "low": np.array([]), "close": np.array([]), "volume": np.array([])}
    usable = (n // 3) * 3
    o = opens[-usable:].reshape(-1, 3)[:, 0]
    h = highs[-usable:].reshape(-1, 3).max(axis=1)
    l = lows[-usable:].reshape(-1, 3).min(axis=1)
    c = closes[-usable:].reshape(-1, 3)[:, -1]
    v = volumes[-usable:].reshape(-1, 3).sum(axis=1)
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _latest_fvg(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, direction: str) -> Optional[Dict[str, Any]]:
    n = min(len(highs), len(lows), len(closes))
    if n < 4:
        return None
    highs = highs[-n:]
    lows = lows[-n:]
    closes = closes[-n:]
    latest = None
    for i in range(2, n):
        if direction == "long" and lows[i] > highs[i - 2]:
            lower = float(highs[i - 2])
            upper = float(lows[i])
            width_pct = (upper / lower - 1.0) if lower > 0 else 0.0
            if width_pct >= OR_FVG_MIN_GAP_PCT:
                latest = {"direction": "bullish", "index": i, "lower": lower, "upper": upper, "mid": (lower + upper) / 2.0, "width_pct": width_pct}
        elif direction == "short" and highs[i] < lows[i - 2]:
            lower = float(highs[i])
            upper = float(lows[i - 2])
            width_pct = (upper / lower - 1.0) if lower > 0 else 0.0
            if width_pct >= OR_FVG_MIN_GAP_PCT:
                latest = {"direction": "bearish", "index": i, "lower": lower, "upper": upper, "mid": (lower + upper) / 2.0, "width_pct": width_pct}
    return latest


def evaluate_opening_range_fvg_guard(
    symbol: str,
    side: str,
    df: pd.DataFrame,
    *,
    market_tz: Any,
    open_hour: int,
    open_minute: int,
) -> Dict[str, Any]:
    """Return a structured permit/block/log decision for a proposed early entry."""
    side = side or "long"
    payload: Dict[str, Any] = {
        "enabled": bool(OR_FVG_GUARD_ENABLED),
        "pilot": bool(OR_FVG_GUARD_PILOT),
        "symbol": symbol,
        "side": side,
        "permit": True,
        "would_block": False,
        "active_window": False,
        "reason": "disabled" if not OR_FVG_GUARD_ENABLED else "not_evaluated",
    }
    if not OR_FVG_GUARD_ENABLED:
        return payload
    if df is None or getattr(df, "empty", True):
        payload.update({"permit": bool(OR_FVG_GUARD_PILOT), "would_block": True, "reason": "no_intraday_dataframe"})
        return payload

    opens_all = _series_from_df(df, "Open")
    highs_all = _series_from_df(df, "High")
    lows_all = _series_from_df(df, "Low")
    closes_all = _series_from_df(df, "Close")
    volumes_all = _series_from_df(df, "Volume")
    if min(len(opens_all), len(highs_all), len(lows_all), len(closes_all), len(volumes_all)) < 6:
        payload.update({"permit": bool(OR_FVG_GUARD_PILOT), "would_block": True, "reason": "insufficient_intraday_bars"})
        return payload

    start = _session_start_index(df, market_tz, open_hour, open_minute)
    opens = opens_all[start:]
    highs = highs_all[start:]
    lows = lows_all[start:]
    closes = closes_all[start:]
    volumes = volumes_all[start:]
    bars_since_open = len(closes)
    minutes_since_open = bars_since_open * 5
    active_window = minutes_since_open <= OR_FVG_GUARD_EARLY_MINUTES
    payload["active_window"] = bool(active_window)
    payload["minutes_since_open"] = int(minutes_since_open)
    payload["early_window_minutes"] = OR_FVG_GUARD_EARLY_MINUTES
    if not active_window:
        payload.update({"permit": True, "would_block": False, "reason": "outside_early_entry_window"})
        return payload

    or_bars = max(1, int(round(OR_FVG_OPENING_RANGE_MINUTES / 5.0)))
    or_bars = min(or_bars, len(highs), len(lows))
    opening_range_high = float(np.max(highs[:or_bars]))
    opening_range_low = float(np.min(lows[:or_bars]))
    px = float(closes[-1])
    vwap = _vwap(highs, lows, closes, volumes)
    ema_fast = _ema(closes, OR_FVG_EMA_FAST)
    ema_slow = _ema(closes, OR_FVG_EMA_SLOW)
    fvg_5m = _latest_fvg(highs, lows, closes, side)
    bars_15 = _aggregate_15m(opens, highs, lows, closes, volumes)
    fvg_15m = _latest_fvg(bars_15["high"], bars_15["low"], bars_15["close"], side)
    active_fvg = fvg_5m or fvg_15m

    if side == "short":
        reclaim_or_hold = bool(active_fvg and px <= float(active_fvg["upper"]) and px < opening_range_low)
        vwap_ok = bool(vwap is not None and px < vwap)
        ema_ok = bool(ema_fast is not None and ema_slow is not None and px < ema_fast <= ema_slow)
    else:
        reclaim_or_hold = bool(active_fvg and px >= float(active_fvg["lower"]) and px > opening_range_high)
        vwap_ok = bool(vwap is not None and px > vwap)
        ema_ok = bool(ema_fast is not None and ema_slow is not None and px > ema_fast >= ema_slow)

    confirmed = bool(active_fvg and reclaim_or_hold and vwap_ok and ema_ok)
    would_block = not confirmed
    permit = True if OR_FVG_GUARD_PILOT else confirmed
    reason = "fvg_reclaim_hold_confirmed" if confirmed else "early_entry_requires_fvg_reclaim_vwap_ema_confirmation"

    payload.update({
        "permit": bool(permit),
        "would_block": bool(would_block),
        "confirmed": bool(confirmed),
        "reason": reason,
        "price": round(px, 4),
        "opening_range_minutes": OR_FVG_OPENING_RANGE_MINUTES,
        "opening_range_high": round(opening_range_high, 4),
        "opening_range_low": round(opening_range_low, 4),
        "vwap": round(float(vwap), 4) if vwap is not None else None,
        "ema_fast": round(float(ema_fast), 4) if ema_fast is not None else None,
        "ema_slow": round(float(ema_slow), 4) if ema_slow is not None else None,
        "vwap_ok": bool(vwap_ok),
        "ema_ok": bool(ema_ok),
        "reclaim_or_hold_ok": bool(reclaim_or_hold),
        "fvg_5m": fvg_5m,
        "fvg_15m": fvg_15m,
    })
    return payload


def log_guard_decision(portfolio: Dict[str, Any], decision: Dict[str, Any], source: str = "scanner") -> None:
    audit = portfolio.setdefault("scanner_audit", {})
    audit.setdefault("opening_range_fvg_guard", [])
    record = dict(decision)
    record["ts"] = int(time.time())
    record["source"] = source
    audit["opening_range_fvg_guard"].append(record)
    audit["opening_range_fvg_guard"] = audit["opening_range_fvg_guard"][-OR_FVG_LOG_LIMIT:]
    if decision.get("would_block"):
        audit.setdefault("blocked_entries", [])
        audit["blocked_entries"].append({
            "symbol": decision.get("symbol"),
            "side": decision.get("side"),
            "reason": decision.get("reason"),
            "pilot": decision.get("pilot"),
            "guard": "opening_range_fvg_guard",
            "price": decision.get("price"),
            "ts": int(time.time()),
        })
        audit["blocked_entries"] = audit["blocked_entries"][-OR_FVG_LOG_LIMIT:]


def position_tier_for_market(market: Dict[str, Any]) -> Dict[str, Any]:
    """Map broad-market confirmation to requested max-position tiers."""
    mode = (market or {}).get("market_mode", "neutral")
    risk_score = float((market or {}).get("risk_score", 0.0) or 0.0)
    breadth = (market or {}).get("breadth", {}) or {}
    futures = (market or {}).get("futures_bias", {}) or {}
    bear_confirmed = bool((market or {}).get("bear_confirmed", False))
    defensive_rotation = bool((market or {}).get("defensive_rotation", False))
    broad_market_soft = bool((market or {}).get("broad_market_soft", False))

    exceptional = (
        mode == "risk_on"
        and risk_score >= 82
        and breadth.get("state") == "supportive"
        and futures.get("bias") == "bullish"
        and not broad_market_soft
    )
    strong = (
        mode == "risk_on"
        and risk_score >= 70
        and not bear_confirmed
        and not defensive_rotation
    )
    caution = mode in ["neutral", "risk_off", "crash_warning", "defensive_rotation"] or bear_confirmed or defensive_rotation

    if exceptional:
        return {"max_positions": 8, "tier": "exceptional_broad_market_confirmation", "reason": "risk_on_plus_supportive_breadth_and_bullish_futures"}
    if strong:
        return {"max_positions": 6, "tier": "strong_risk_on", "reason": "risk_on_confirmed"}
    if caution:
        if mode in ["risk_off", "crash_warning"] or bear_confirmed:
            max_positions = 0 if mode == "crash_warning" else 3
        else:
            max_positions = 3
        return {"max_positions": int(max_positions), "tier": "caution_self_defense", "reason": "reduced_exposure_context"}
    return {"max_positions": 4, "tier": "default", "reason": "standard_default"}
