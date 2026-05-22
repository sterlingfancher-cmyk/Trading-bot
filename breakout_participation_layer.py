"""Breakout participation layer for high relative-strength gap/breakout days.

Loaded by sitecustomize. State-safe; it only patches scanner/universe at runtime.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

VERSION = "breakout-participation-layer-2026-05-22-runtime-stability-v2"

PATCHED_MODULE_IDS: set[int] = set()
REGISTERED_APP_IDS: set[int] = set()

BREAKOUT_PARTICIPATION_ENABLED = os.environ.get("BREAKOUT_PARTICIPATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
BREAKOUT_MIN_MOVE_PCT = float(os.environ.get("BREAKOUT_MIN_MOVE_PCT", "0.055"))
BREAKOUT_VOLUME_SURGE_RATIO = float(os.environ.get("BREAKOUT_VOLUME_SURGE_RATIO", "1.35"))
BREAKOUT_OPENING_RANGE_BARS = int(os.environ.get("BREAKOUT_OPENING_RANGE_BARS", "6"))
BREAKOUT_CONFIRMATION_LOOKBACK_BARS = int(os.environ.get("BREAKOUT_CONFIRMATION_LOOKBACK_BARS", "8"))
BREAKOUT_MAX_REGULAR_ALLOC_FACTOR = float(os.environ.get("BREAKOUT_MAX_REGULAR_ALLOC_FACTOR", "0.45"))
BREAKOUT_EXTENDED_ALLOC_FACTOR = float(os.environ.get("BREAKOUT_EXTENDED_ALLOC_FACTOR", "0.30"))
BREAKOUT_PARABOLIC_ALLOC_FACTOR = float(os.environ.get("BREAKOUT_PARABOLIC_ALLOC_FACTOR", "0.20"))
BREAKOUT_MAX_STARTERS_PER_CYCLE = int(os.environ.get("BREAKOUT_MAX_STARTERS_PER_CYCLE", "3"))
BREAKOUT_MIN_MINUTES_AFTER_OPEN = int(os.environ.get("BREAKOUT_MIN_MINUTES_AFTER_OPEN", "20"))
BREAKOUT_NO_NEW_STARTERS_LAST_MINUTES = int(os.environ.get("BREAKOUT_NO_NEW_STARTERS_LAST_MINUTES", "45"))
BREAKOUT_SCORE_FLOOR = float(os.environ.get("BREAKOUT_SCORE_FLOOR", "0.036"))
BREAKOUT_SCORE_CAP = float(os.environ.get("BREAKOUT_SCORE_CAP", "0.080"))
BREAKOUT_NEAR_HIGH_FACTOR = float(os.environ.get("BREAKOUT_NEAR_HIGH_FACTOR", "0.985"))
BREAKOUT_MAX_RANGE_COMPRESSION_PCT = float(os.environ.get("BREAKOUT_MAX_RANGE_COMPRESSION_PCT", "0.055"))

AI_CLOUD_BREAKOUTS = [
    "NBIS", "APLD", "LITE", "COHR", "AAOI", "SNDK", "WDC", "STX", "LRCX",
    "TER", "NVTS", "ALAB", "MRVL", "CRDO", "SMCI", "ANET", "DELL", "HPE",
]
POWER_INFRA_BREAKOUTS = [
    "BE", "VRT", "ETN", "PWR", "GEV", "VST", "CEG", "NRG", "MOD", "POWL",
    "IESC", "BWXT", "MTZ", "HWM",
]
CRYPTO_COMPUTE_BREAKOUTS = [
    "APLD", "IREN", "HUT", "CIFR", "CLSK", "MARA", "RIOT", "BTDR", "CORZ",
    "WULF", "HIVE", "WGMI", "IBIT", "ETHE",
]
SMALL_CAP_BREAKOUTS = [
    "RKLB", "PL", "QBTS", "IONQ", "RGTI", "SOUN", "ACHR", "JOBY", "TEM",
    "BBAI", "AI", "BTQ",
]
ADDITIONAL_BREAKOUT_UNIVERSE = list(dict.fromkeys(
    AI_CLOUD_BREAKOUTS + POWER_INFRA_BREAKOUTS + CRYPTO_COMPUTE_BREAKOUTS + SMALL_CAP_BREAKOUTS
))

ADDITIONAL_SECTORS = {
    "BE": "XLI", "NBIS": "XLK", "APLD": "XLK", "LITE": "XLK", "SNDK": "XLK",
    "LRCX": "XLK", "NVTS": "XLK", "HIVE": "XLK", "WGMI": "XLK", "IBIT": "CRYPTO",
    "ETHE": "CRYPTO", "BWXT": "XLI", "MTZ": "XLI", "HWM": "XLI", "PL": "XLK",
    "BTQ": "XLK", "CRDO": "XLK", "RKLB": "XLI",
}
ADDITIONAL_BUCKETS = {
    "BE": "power_grid_data_center",
    "BWXT": "power_grid_data_center",
    "MTZ": "power_grid_data_center",
    "HWM": "power_grid_data_center",
    "NBIS": "ai_cloud_breakout",
    "APLD": "bitcoin_ai_compute",
    "LITE": "data_center_infra",
    "SNDK": "data_center_infra",
    "LRCX": "semi_leaders",
    "NVTS": "ai_cloud_breakout",
    "HIVE": "bitcoin_ai_compute",
    "WGMI": "bitcoin_ai_compute",
    "IBIT": "crypto_proxy",
    "ETHE": "crypto_proxy",
    "PL": "small_cap_momentum",
    "BTQ": "small_cap_momentum",
    "CRDO": "ai_cloud_breakout",
}


def _mod():
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "scan_signals"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "scan_signals"):
            return m
    return None


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _series(arr: Any) -> np.ndarray:
    try:
        out = np.asarray(arr, dtype=float)
        out = out[np.isfinite(out)]
        return out
    except Exception:
        return np.array([])


def _sma(arr: np.ndarray, n: int) -> float | None:
    arr = _series(arr)
    if len(arr) < n:
        return None
    return float(np.mean(arr[-n:]))


def _pct(arr: np.ndarray, n: int) -> float:
    arr = _series(arr)
    if len(arr) <= n or float(arr[-n]) == 0:
        return 0.0
    return float(arr[-1] / arr[-n] - 1.0)


def _now_text(m=None) -> str:
    try:
        return m.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _session_bar_count(m=None) -> int:
    try:
        now = m.now_local()
        open_dt = m.regular_open_datetime(now)
        minutes = max(0.0, (now - open_dt).total_seconds() / 60.0)
        return max(1, min(78, int(minutes // 5) + 1))
    except Exception:
        return 78


def _minutes_since_open_and_to_close(m=None) -> Tuple[float, float]:
    try:
        now = m.now_local()
        open_dt = m.regular_open_datetime(now)
        close_dt = now.replace(
            hour=getattr(m, "REGULAR_CLOSE_HOUR", 15),
            minute=getattr(m, "REGULAR_CLOSE_MINUTE", 0),
            second=0,
            microsecond=0,
        )
        return max(0.0, (now - open_dt).total_seconds() / 60.0), max(0.0, (close_dt - now).total_seconds() / 60.0)
    except Exception:
        return 999.0, 999.0


def _volume_surge(vols: np.ndarray, lookback: int = 6) -> float:
    vols = _series(vols)
    if len(vols) < lookback + 8:
        return 0.0
    recent = float(np.sum(vols[-lookback:]))
    base = vols[-(lookback * 10):-lookback] if len(vols) >= lookback * 11 else vols[:-lookback]
    if len(base) < lookback:
        return 0.0
    base_avg_window = float(np.mean(base)) * lookback
    return recent / base_avg_window if base_avg_window > 0 else 0.0


def _add_unique(seq: List[str], values: List[str]) -> List[str]:
    seen = set(seq)
    for v in values:
        if v not in seen:
            seq.append(v)
            seen.add(v)
    return seq


def _apply_runtime_stability_hotfix(m=None, flask_app=None) -> Dict[str, Any]:
    try:
        import runtime_stability_hotfix
        module = m or _mod()
        payload = {}
        if hasattr(runtime_stability_hotfix, "apply_runtime_overrides"):
            payload = runtime_stability_hotfix.apply_runtime_overrides(module)
        if flask_app is not None and hasattr(runtime_stability_hotfix, "register_routes"):
            runtime_stability_hotfix.register_routes(flask_app, module)
        return payload if isinstance(payload, dict) else {"status": "ok", "reason": "runtime_stability_loaded"}
    except Exception as exc:
        return {"status": "error", "reason": "runtime_stability_hotfix_failed", "error": str(exc), "version": VERSION}


def _patch_universe(m) -> None:
    if m is None:
        return
    try:
        m.UNIVERSE = _add_unique(list(getattr(m, "UNIVERSE", []) or []), ADDITIONAL_BREAKOUT_UNIVERSE)
    except Exception:
        pass

    try:
        sector_map = getattr(m, "SYMBOL_SECTOR", {})
        for sym, sector in ADDITIONAL_SECTORS.items():
            sector_map.setdefault(sym, sector)
        m.SYMBOL_SECTOR = sector_map
    except Exception:
        pass

    try:
        bucket_map = getattr(m, "SYMBOL_BUCKET", {})
        for sym in ADDITIONAL_BREAKOUT_UNIVERSE:
            if sym in ADDITIONAL_BUCKETS:
                bucket_map[sym] = ADDITIONAL_BUCKETS[sym]
            elif sym in POWER_INFRA_BREAKOUTS:
                bucket_map.setdefault(sym, "power_grid_data_center")
            elif sym in AI_CLOUD_BREAKOUTS:
                bucket_map.setdefault(sym, "ai_cloud_breakout")
            elif sym in CRYPTO_COMPUTE_BREAKOUTS:
                bucket_map.setdefault(sym, "bitcoin_ai_compute")
            elif sym in SMALL_CAP_BREAKOUTS:
                bucket_map.setdefault(sym, "small_cap_momentum")
        m.SYMBOL_BUCKET = bucket_map
    except Exception:
        pass

    try:
        cfg = getattr(m, "BUCKET_CONFIG", {})
        cfg.setdefault("ai_cloud_breakout", {"alloc_factor": 0.55, "max_exposure_pct": 0.30, "max_positions": 2})
        cfg.setdefault("power_grid_data_center", {"alloc_factor": 0.60, "max_exposure_pct": 0.35, "max_positions": 2})
        cfg.setdefault("crypto_proxy", {"alloc_factor": 0.45, "max_exposure_pct": 0.18, "max_positions": 2})
        m.BUCKET_CONFIG = cfg
    except Exception:
        pass


def _breakout_context(m, symbol: str, arrays: Dict[str, Any], market: Dict[str, Any], benchmark_prices=None) -> Dict[str, Any]:
    if not BREAKOUT_PARTICIPATION_ENABLED:
        return {"active": False, "reason": "breakout_participation_disabled", "version": VERSION}

    closes = _series(arrays.get("close"))
    opens = _series(arrays.get("open"))
    highs = _series(arrays.get("high"))
    lows = _series(arrays.get("low"))
    vols = _series(arrays.get("volume"))
    if len(closes) < 24 or len(opens) < 5 or len(highs) < 5 or len(lows) < 5:
        return {"active": False, "reason": "not_enough_intraday_data", "version": VERSION}

    minutes_since_open, minutes_to_close = _minutes_since_open_and_to_close(m)
    if minutes_since_open < BREAKOUT_MIN_MINUTES_AFTER_OPEN:
        return {"active": False, "reason": "waiting_for_opening_range", "minutes_since_open": round(minutes_since_open, 1), "version": VERSION}
    if minutes_to_close <= BREAKOUT_NO_NEW_STARTERS_LAST_MINUTES:
        return {"active": False, "reason": "too_close_to_close", "minutes_to_close": round(minutes_to_close, 1), "version": VERSION}

    bars = min(len(closes), _session_bar_count(m))
    if bars < max(BREAKOUT_OPENING_RANGE_BARS + 2, 8):
        return {"active": False, "reason": "not_enough_session_bars", "session_bars": bars, "version": VERSION}

    c = closes[-bars:]
    o = opens[-bars:]
    h = highs[-bars:]
    l = lows[-bars:]
    v = vols[-bars:] if len(vols) >= bars else vols

    px = float(c[-1])
    session_open = float(o[0])
    if px <= 0 or session_open <= 0:
        return {"active": False, "reason": "bad_price", "version": VERSION}

    session_move = px / session_open - 1.0
    if session_move < BREAKOUT_MIN_MOVE_PCT:
        return {"active": False, "reason": "intraday_move_below_breakout_threshold", "intraday_move_pct": round(session_move * 100, 2), "version": VERSION}

    or_bars = max(3, min(BREAKOUT_OPENING_RANGE_BARS, bars - 2))
    opening_range_high = float(np.max(h[:or_bars]))
    session_high = float(np.max(h))
    session_low = float(np.min(l))
    recent_bars = max(3, min(BREAKOUT_CONFIRMATION_LOOKBACK_BARS, bars))
    recent_high = float(np.max(h[-recent_bars:]))
    recent_low = float(np.min(l[-recent_bars:]))
    recent_range_pct = (recent_high - recent_low) / max(px, 0.01)
    vol_surge = _volume_surge(v)

    ma8 = _sma(c, min(8, max(3, len(c) // 2)))
    ma20 = _sma(c, min(20, max(5, len(c) // 2)))
    above_fast_stack = bool(ma8 and px >= ma8)
    above_slow_stack = bool(ma20 and px >= ma20)
    broke_opening_range = bool(opening_range_high > 0 and px >= opening_range_high * 1.003)
    holding_near_high = bool(session_high > 0 and px >= session_high * BREAKOUT_NEAR_HIGH_FACTOR)
    range_not_too_wide = bool(recent_range_pct <= BREAKOUT_MAX_RANGE_COMPRESSION_PCT or holding_near_high)
    volume_confirmed = bool(vol_surge >= BREAKOUT_VOLUME_SURGE_RATIO)

    structure_confirmed = (broke_opening_range or holding_near_high) and above_fast_stack and above_slow_stack and range_not_too_wide
    strong_exception = session_move >= (BREAKOUT_MIN_MOVE_PCT * 1.7) and holding_near_high and above_fast_stack
    if not (structure_confirmed and (volume_confirmed or strong_exception)):
        return {
            "active": False,
            "reason": "breakout_structure_not_confirmed",
            "intraday_move_pct": round(session_move * 100, 2),
            "volume_surge_ratio": round(vol_surge, 2),
            "broke_opening_range": broke_opening_range,
            "holding_near_high": holding_near_high,
            "above_fast_stack": above_fast_stack,
            "above_slow_stack": above_slow_stack,
            "recent_range_pct": round(recent_range_pct * 100, 2),
            "version": VERSION,
        }

    sector = getattr(m, "SYMBOL_SECTOR", {}).get(symbol, ADDITIONAL_SECTORS.get(symbol, "UNKNOWN"))
    bucket = getattr(m, "SYMBOL_BUCKET", {}).get(symbol, ADDITIONAL_BUCKETS.get(symbol, "default"))
    sector_bonus = 0.004 if sector in (market.get("sector_leaders", []) or []) else 0.0

    rs_bonus = 0.0
    try:
        b = _series(benchmark_prices)
        if len(b) > 12 and len(c) > 12:
            b_tail = b[-min(len(b), len(c)):]
            n = min(12, len(b_tail) - 1, len(c) - 1)
            if n > 0 and _pct(c, n) - _pct(b_tail, n) > 0.01:
                rs_bonus = 0.004
    except Exception:
        pass

    volume_bonus = min(0.010, max(0.0, (vol_surge - 1.0) * 0.004))
    move_bonus = min(0.024, session_move * 0.16)
    structure_bonus = 0.008 if broke_opening_range else 0.004
    high_hold_bonus = 0.004 if holding_near_high else 0.0
    bucket_bonus = 0.003 if bucket in {"ai_cloud_breakout", "power_grid_data_center", "bitcoin_ai_compute", "data_center_infra", "semi_leaders"} else 0.0

    base_score = 0.018 + move_bonus + volume_bonus + structure_bonus + high_hold_bonus + sector_bonus + rs_bonus + bucket_bonus
    try:
        regular_score = _f(m.signal_score(symbol, closes, market, "long", benchmark_prices=benchmark_prices), 0.0)
        base_score = max(base_score, regular_score + 0.010)
    except Exception:
        pass
    score = max(BREAKOUT_SCORE_FLOOR, min(BREAKOUT_SCORE_CAP, base_score))

    if session_move >= 0.16:
        alloc_factor = BREAKOUT_PARABOLIC_ALLOC_FACTOR
        risk_tier = "parabolic_starter"
    elif session_move >= 0.11:
        alloc_factor = BREAKOUT_EXTENDED_ALLOC_FACTOR
        risk_tier = "extended_breakout_starter"
    else:
        alloc_factor = BREAKOUT_MAX_REGULAR_ALLOC_FACTOR
        risk_tier = "confirmed_breakout_starter"

    return {
        "active": True,
        "version": VERSION,
        "reason": "volume_confirmed_breakout_participation",
        "risk_tier": risk_tier,
        "score": round(score, 6),
        "alloc_factor": round(float(alloc_factor), 4),
        "intraday_move_pct": round(session_move * 100, 2),
        "volume_surge_ratio": round(vol_surge, 2),
        "session_bars": int(bars),
        "opening_range_high": round(opening_range_high, 4),
        "session_high": round(session_high, 4),
        "session_low": round(session_low, 4),
        "recent_range_pct": round(recent_range_pct * 100, 2),
        "broke_opening_range": broke_opening_range,
        "holding_near_high": holding_near_high,
        "above_fast_stack": above_fast_stack,
        "above_slow_stack": above_slow_stack,
        "volume_confirmed": volume_confirmed,
        "strong_exception": strong_exception,
        "sector": sector,
        "bucket": bucket,
        "sector_bonus": round(sector_bonus, 6),
        "relative_strength_bonus": round(rs_bonus, 6),
    }


def _patch_scan_signals(m) -> bool:
    if m is None or getattr(m.scan_signals, "_breakout_layer_patched", False):
        return False

    original_scan = m.scan_signals

    def patched_scan_signals(market):
        _patch_universe(m)
        long_signals, short_signals, rejected = original_scan(market)
        if not BREAKOUT_PARTICIPATION_ENABLED:
            return long_signals, short_signals, rejected

        existing = {str(s.get("symbol", "")).upper() for s in (long_signals or []) if isinstance(s, dict)}
        added_count = 0

        benchmark_prices = np.array([])
        try:
            qqq_df = m.fetch_intraday("QQQ")
            benchmark_prices = m.price_series(qqq_df, "Close")
        except Exception:
            benchmark_prices = np.array([])

        for symbol in list(getattr(m, "UNIVERSE", []) or []):
            symbol = str(symbol).upper()
            if added_count >= BREAKOUT_MAX_STARTERS_PER_CYCLE:
                break
            if symbol in existing:
                continue
            try:
                if m.is_in_cooldown(symbol) or symbol in (m.portfolio.get("positions", {}) or {}):
                    continue
            except Exception:
                pass

            try:
                df = m.fetch_intraday(symbol)
                if df is None or getattr(df, "empty", True):
                    continue
                arrays = m.intraday_arrays(df)
                closes = _series(arrays.get("close"))
                if len(closes) < 24:
                    continue
                ctx = _breakout_context(m, symbol, arrays, market, benchmark_prices=benchmark_prices)
                if not ctx.get("active"):
                    continue

                score = _f(ctx.get("score"), BREAKOUT_SCORE_FLOOR)
                sector = ctx.get("sector") or getattr(m, "SYMBOL_SECTOR", {}).get(symbol, "UNKNOWN")
                bucket = ctx.get("bucket") or getattr(m, "SYMBOL_BUCKET", {}).get(symbol, "default")
                px = float(closes[-1])
                signal = {
                    "symbol": symbol,
                    "side": "long",
                    "score": round(score, 6),
                    "price": px,
                    "sector": sector,
                    "bucket": bucket,
                    "entry_context": "breakout_participation_starter",
                    "trade_class": "breakout_starter",
                    "alloc_factor": ctx.get("alloc_factor", BREAKOUT_EXTENDED_ALLOC_FACTOR),
                    "breakout_participation": ctx,
                    "catalyst": {
                        "active": True,
                        "reason": "breakout_participation_layer",
                        "intraday_move_pct": ctx.get("intraday_move_pct"),
                        "volume_surge_ratio": ctx.get("volume_surge_ratio"),
                        "bucket": bucket,
                        "score_bonus": round(score - BREAKOUT_SCORE_FLOOR, 6),
                    },
                }
                long_signals.append(signal)
                existing.add(symbol)
                added_count += 1
            except Exception as exc:
                try:
                    rejected.append({"symbol": symbol, "reason": "breakout_layer_error", "error": str(exc), "version": VERSION})
                except Exception:
                    pass

        try:
            long_signals = m.apply_theme_confirmation(long_signals)
        except Exception:
            pass
        long_signals = sorted(long_signals or [], key=lambda x: _f(x.get("score"), 0.0), reverse=True)
        short_signals = sorted(short_signals or [], key=lambda x: _f(x.get("score"), 0.0), reverse=True)
        return long_signals, short_signals, rejected

    patched_scan_signals._breakout_layer_patched = True
    patched_scan_signals._breakout_original = original_scan
    m.scan_signals = patched_scan_signals
    return True


def settings_payload() -> Dict[str, Any]:
    return {
        "min_move_pct": round(BREAKOUT_MIN_MOVE_PCT * 100, 2),
        "volume_surge_ratio": BREAKOUT_VOLUME_SURGE_RATIO,
        "opening_range_bars": BREAKOUT_OPENING_RANGE_BARS,
        "min_minutes_after_open": BREAKOUT_MIN_MINUTES_AFTER_OPEN,
        "no_new_starters_last_minutes": BREAKOUT_NO_NEW_STARTERS_LAST_MINUTES,
        "max_starters_per_cycle": BREAKOUT_MAX_STARTERS_PER_CYCLE,
        "score_floor": BREAKOUT_SCORE_FLOOR,
        "score_cap": BREAKOUT_SCORE_CAP,
        "regular_alloc_factor": BREAKOUT_MAX_REGULAR_ALLOC_FACTOR,
        "extended_alloc_factor": BREAKOUT_EXTENDED_ALLOC_FACTOR,
        "parabolic_alloc_factor": BREAKOUT_PARABOLIC_ALLOC_FACTOR,
    }


def apply_runtime_overrides(m=None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    _patch_universe(m)
    patched_scan = _patch_scan_signals(m)
    runtime_stability = _apply_runtime_stability_hotfix(m)
    PATCHED_MODULE_IDS.add(id(m))
    return {
        "status": "ok",
        "version": VERSION,
        "enabled": BREAKOUT_PARTICIPATION_ENABLED,
        "patched_scan_signals": bool(patched_scan or getattr(m.scan_signals, "_breakout_layer_patched", False)),
        "universe_count": len(getattr(m, "UNIVERSE", []) or []),
        "added_symbols": ADDITIONAL_BREAKOUT_UNIVERSE,
        "settings": settings_payload(),
        "runtime_stability_hotfix": runtime_stability,
        "generated_local": _now_text(m),
    }


def current_breakout_leaders(m=None, limit: int = 20) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    apply_runtime_overrides(m)
    market = {}
    try:
        market = m.portfolio.get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    leaders = []
    benchmark_prices = np.array([])
    try:
        qqq_df = m.fetch_intraday("QQQ")
        benchmark_prices = m.price_series(qqq_df, "Close")
    except Exception:
        pass
    for symbol in list(getattr(m, "UNIVERSE", []) or []):
        try:
            df = m.fetch_intraday(symbol)
            if df is None or getattr(df, "empty", True):
                continue
            arrays = m.intraday_arrays(df)
            ctx = _breakout_context(m, symbol, arrays, market, benchmark_prices=benchmark_prices)
            if ctx.get("active"):
                leaders.append({
                    "symbol": symbol,
                    "score": ctx.get("score"),
                    "risk_tier": ctx.get("risk_tier"),
                    "alloc_factor": ctx.get("alloc_factor"),
                    "intraday_move_pct": ctx.get("intraday_move_pct"),
                    "volume_surge_ratio": ctx.get("volume_surge_ratio"),
                    "sector": ctx.get("sector"),
                    "bucket": ctx.get("bucket"),
                    "reason": ctx.get("reason"),
                })
        except Exception:
            continue
    leaders = sorted(leaders, key=lambda x: _f(x.get("score"), 0.0), reverse=True)[:max(1, min(int(limit), 50))]
    return {
        "status": "ok",
        "type": "breakout_participation_leaders",
        "version": VERSION,
        "generated_local": _now_text(m),
        "leaders_count": len(leaders),
        "leaders": leaders,
        "settings": settings_payload(),
    }


def register_routes(flask_app) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify, request

    def breakout_participation_status():
        m = _mod()
        payload = apply_runtime_overrides(m)
        return jsonify({
            "status": "ok" if payload.get("status") == "ok" else payload.get("status", "pending"),
            "type": "breakout_participation_status",
            **payload,
        })

    def breakout_participation_leaders():
        try:
            limit = int(request.args.get("limit", "20"))
        except Exception:
            limit = 20
        return jsonify(current_breakout_leaders(_mod(), limit=limit))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/breakout-participation-status" not in existing:
        flask_app.add_url_rule("/paper/breakout-participation-status", "breakout_participation_status", breakout_participation_status)
    if "/paper/breakout-leaders" not in existing:
        flask_app.add_url_rule("/paper/breakout-leaders", "breakout_participation_leaders", breakout_participation_leaders)

    _apply_runtime_stability_hotfix(_mod(), flask_app=flask_app)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(_mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
