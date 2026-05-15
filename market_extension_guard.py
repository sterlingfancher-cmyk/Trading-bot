from __future__ import annotations

import datetime as dt
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List

VERSION = "market-extension-fib-candle-guard-2026-05-15"
ENABLED = os.environ.get("MARKET_EXTENSION_GUARD_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
INDEX_SYMBOLS = [s.strip().upper() for s in os.environ.get("MARKET_EXTENSION_INDEX_SYMBOLS", "SPY,QQQ").split(",") if s.strip()]
DAILY_PERIOD = os.environ.get("MARKET_EXTENSION_DAILY_PERIOD", "1y")
CACHE_TTL = int(os.environ.get("MARKET_EXTENSION_GUARD_CACHE_TTL", "300"))
MA20_CAUTION = float(os.environ.get("MARKET_EXTENSION_MA20_CAUTION_PCT", "0.040"))
MA20_SEVERE = float(os.environ.get("MARKET_EXTENSION_MA20_SEVERE_PCT", "0.055"))
NEAR_HIGH = float(os.environ.get("MARKET_EXTENSION_NEAR_HIGH_PCT", "0.020"))
FIB_LOOKBACK = int(os.environ.get("MARKET_EXTENSION_FIB_LOOKBACK_BARS", "126"))
BEAR_WICK_MIN = float(os.environ.get("MARKET_EXTENSION_BEARISH_WICK_MIN", "0.42"))
BULL_CLOSE_MIN = float(os.environ.get("MARKET_EXTENSION_BULLISH_CLOSE_LOCATION", "0.65"))
EXCEPTIONAL_SCORE = float(os.environ.get("MARKET_EXTENSION_EXCEPTIONAL_SCORE", "0.045"))

_REGISTERED: set[int] = set()
_PATCHED: set[int] = set()
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_LOCK = threading.RLock()


def _module() -> Any:
    for name in ("app", "__main__", "wsgi"):
        mod = sys.modules.get(name)
        if mod is not None:
            core = getattr(mod, "core", mod)
            if hasattr(core, "download_prices") and hasattr(core, "portfolio"):
                return core
    return None


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(values: Any) -> List[float]:
    out: List[float] = []
    try:
        for v in list(values):
            fv = _f(v, math.nan)
            if not math.isnan(fv):
                out.append(fv)
    except Exception:
        pass
    return out


def _sma(values: List[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / float(period)


def _pct(a: float, b: float) -> float:
    return 0.0 if not b else (a / b) - 1.0


def _series(mod: Any, df: Any, col: str) -> List[float]:
    try:
        if hasattr(mod, "price_series"):
            return _clean(mod.price_series(df, col))
    except Exception:
        pass
    try:
        return _clean(df[col].values)
    except Exception:
        return []


def _daily(mod: Any, symbol: str):
    try:
        df = mod.download_prices(symbol, period=DAILY_PERIOD, interval="1d")
    except Exception:
        df = None
    return [_series(mod, df, c) for c in ("Open", "High", "Low", "Close", "Volume")]


def _fib(lows: List[float], highs: List[float], closes: List[float]) -> Dict[str, Any]:
    n = min(len(closes), max(20, FIB_LOOKBACK))
    if len(lows) < n or len(highs) < n or len(closes) < n:
        return {"available": False, "reason": "insufficient_data"}
    lo, hi, c = min(lows[-n:]), max(highs[-n:]), closes[-1]
    span = hi - lo
    if lo <= 0 or hi <= 0 or span <= 0:
        return {"available": False, "reason": "bad_range"}
    levels = {"fib_23_6": hi - span * 0.236, "fib_38_2": hi - span * 0.382, "fib_50_0": hi - span * 0.5, "fib_61_8": hi - span * 0.618}
    below = [(k, v) for k, v in levels.items() if v <= c]
    nearest = max(below, key=lambda kv: kv[1]) if below else min(levels.items(), key=lambda kv: abs(kv[1] - c))
    return {"available": True, "lookback_bars": n, "swing_low": round(lo, 4), "swing_high": round(hi, 4), "levels": {k: round(v, 4) for k, v in levels.items()}, "nearest_support": {"name": nearest[0], "price": round(nearest[1], 4), "distance_pct": round(_pct(c, nearest[1]) * 100, 2)}}


def _candle(opens, highs, lows, closes, volumes) -> Dict[str, Any]:
    if min(len(opens), len(highs), len(lows), len(closes)) < 2:
        return {"available": False}
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    rng = max(h - l, abs(c) * 0.0001, 0.0001)
    body = abs(c - o)
    upper = max(0.0, h - max(o, c))
    lower = max(0.0, min(o, c) - l)
    loc = (c - l) / rng
    vr = None
    if len(volumes) >= 21:
        avg = sum(volumes[-21:-1]) / 20.0
        vr = volumes[-1] / avg if avg > 0 else None
    bearish = upper / rng >= BEAR_WICK_MIN and loc <= 0.58 and c <= o * 1.002
    bullish = c > o and loc >= BULL_CLOSE_MIN and body / rng >= 0.25
    return {"available": True, "open": round(o, 4), "high": round(h, 4), "low": round(l, 4), "close": round(c, 4), "daily_change_pct": round(_pct(c, closes[-2]) * 100, 2), "upper_wick_pct_of_range": round(upper / rng * 100, 2), "lower_wick_pct_of_range": round(lower / rng * 100, 2), "close_location_pct": round(loc * 100, 2), "volume_ratio_20d": round(vr, 2) if vr is not None else None, "bearish_rejection": bool(bearish), "bullish_confirmation": bool(bullish), "bullish_breakout_confirmation": bool(bullish and (vr is None or vr >= 0.90))}


def _index(mod: Any, symbol: str) -> Dict[str, Any]:
    opens, highs, lows, closes, volumes = _daily(mod, symbol)
    if len(closes) < 35:
        return {"symbol": symbol, "status": "insufficient_data"}
    c = closes[-1]
    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50) or _sma(closes, min(35, len(closes)))
    n = min(len(highs), FIB_LOOKBACK)
    recent_high = max(highs[-n:])
    recent_low = min(lows[-n:])
    pct_above_ma20 = _pct(c, ma20) if ma20 else 0.0
    pct_below_high = _pct(recent_high, c) if c else 0.0
    candle = _candle(opens, highs, lows, closes, volumes)
    near_high = c >= recent_high * (1.0 - NEAR_HIGH)
    extended = pct_above_ma20 >= MA20_CAUTION
    severe = pct_above_ma20 >= MA20_SEVERE
    rejection = bool(candle.get("bearish_rejection") and highs[-1] >= recent_high * 0.994)
    bullish = bool(candle.get("bullish_breakout_confirmation") and near_high)
    if rejection and (extended or near_high):
        state, action = "extended_bearish_rejection", "raise_floor_reduce_size"
    elif severe and not bullish:
        state, action = "severely_extended", "raise_floor_reduce_size"
    elif extended and near_high and not bullish:
        state, action = "extended_near_high", "reduce_aggression"
    elif bullish:
        state, action = "bullish_confirmation", "normal_confirmed"
    else:
        state, action = "normal", "normal"
    return {"symbol": symbol, "status": "ok", "close": round(c, 4), "ma20": round(ma20, 4) if ma20 else None, "ma50": round(ma50, 4) if ma50 else None, "recent_high": round(recent_high, 4), "recent_low": round(recent_low, 4), "pct_above_ma20": round(pct_above_ma20 * 100, 2), "pct_below_recent_high": round(pct_below_high * 100, 2), "near_recent_high": bool(near_high), "extended_above_ma20": bool(extended), "severe_extension": bool(severe), "bearish_rejection_at_high": bool(rejection), "bullish_confirmation_near_high": bool(bullish), "candle": candle, "fibonacci": _fib(lows, highs, closes), "state": state, "action": action}


def compute_guard(mod: Any = None, force: bool = False) -> Dict[str, Any]:
    mod = mod or _module()
    now = time.time()
    with _LOCK:
        if not force and _CACHE.get("payload") and now - _f(_CACHE.get("ts")) < CACHE_TTL:
            return dict(_CACHE["payload"])
        if not ENABLED:
            payload = {"status": "ok", "type": "market_extension_guard", "version": VERSION, "enabled": False, "action": "disabled"}
            _CACHE.update({"ts": now, "payload": payload})
            return dict(payload)
        if mod is None:
            return {"status": "error", "type": "market_extension_guard", "version": VERSION, "error": "core_module_not_available"}
        indexes = [_index(mod, s) for s in INDEX_SYMBOLS]
        valid = [x for x in indexes if x.get("status") == "ok"]
        extended = [x for x in valid if x.get("extended_above_ma20") or x.get("severe_extension") or x.get("near_recent_high")]
        rejects = [x for x in valid if x.get("bearish_rejection_at_high")]
        bullish = [x for x in valid if x.get("bullish_confirmation_near_high")]
        action, bump, factor, block = "normal", 0.0, 1.0, False
        if rejects and extended and not bullish:
            action, bump, factor, block = "block_low_quality_chase_longs", 0.006, 0.65, True
        elif len(extended) >= 2 and not bullish:
            action, bump, factor = "raise_score_floor_reduce_size", 0.004, 0.75
        elif len(extended) >= 1 and not bullish:
            action, bump, factor = "reduce_aggression", 0.002, 0.85
        elif bullish:
            action = "bullish_confirmation_ok"
        payload = {"status": "ok", "type": "market_extension_guard", "version": VERSION, "enabled": ENABLED, "generated_local": _now(mod), "symbols": INDEX_SYMBOLS, "action": action, "block_chase_longs": bool(block), "score_bump": round(bump, 6), "long_alloc_factor": round(factor, 4), "extended_symbols": [x.get("symbol") for x in extended], "bearish_rejection_symbols": [x.get("symbol") for x in rejects], "bullish_confirmation_symbols": [x.get("symbol") for x in bullish], "indexes": indexes, "recommended_actions": _actions(action), "notes": ["Fibonacci levels are support/resistance references, not standalone entry triggers.", "Bearish rejection raises caution only when SPY/QQQ are extended or near highs.", "Bullish candle confirmation prevents over-penalizing valid breakouts."]}
        _CACHE.update({"ts": now, "payload": payload})
        return dict(payload)


def _actions(action: str) -> List[str]:
    if action == "block_low_quality_chase_longs":
        return ["Avoid low/medium-score chase longs until SPY/QQQ pull back or confirm with bullish candles.", "Prefer controlled pullback/reclaim entries.", "Use Fibonacci zones as pullback references, not blind buy points."]
    if action == "raise_score_floor_reduce_size":
        return ["Raise the long-entry quality floor and reduce size while both indexes are stretched.", "Require strong candle/volume confirmation for new-high breakouts."]
    if action == "reduce_aggression":
        return ["Reduce size on new longs and avoid entries far above short-term support."]
    if action == "bullish_confirmation_ok":
        return ["Bullish confirmation is present; keep normal controls and avoid oversized late breakouts."]
    return ["No extension-specific action required."]


def _patch_core(mod: Any = None) -> bool:
    mod = mod or _module()
    if mod is None or id(mod) in _PATCHED:
        return False
    orig_market = getattr(mod, "market_status", None)
    if callable(orig_market):
        def market_status(force=False):
            market = orig_market(force=force)
            if isinstance(market, dict):
                guard = compute_guard(mod, force=False)
                market["market_extension_guard"] = guard
                market["candle_guard"] = {"action": guard.get("action"), "bearish_rejection_symbols": guard.get("bearish_rejection_symbols", []), "bullish_confirmation_symbols": guard.get("bullish_confirmation_symbols", [])}
            return market
        mod.market_status = market_status
    orig_min = getattr(mod, "min_entry_score_for_market", None)
    if callable(orig_min):
        def min_entry_score_for_market(market, side="long"):
            v = _f(orig_min(market, side))
            if str(side).lower() == "long" and isinstance(market, dict):
                v += _f((market.get("market_extension_guard") or compute_guard(mod)).get("score_bump"))
            return round(v, 6)
        mod.min_entry_score_for_market = min_entry_score_for_market
    orig_aggr = getattr(mod, "apply_aggression_adjustments", None)
    if callable(orig_aggr):
        def apply_aggression_adjustments(params, market):
            adjusted = orig_aggr(params, market)
            try:
                guard = (market or {}).get("market_extension_guard") or compute_guard(mod)
                factor = _f(guard.get("long_alloc_factor"), 1.0)
                if factor < 0.999 and isinstance(adjusted, dict):
                    adjusted["long_alloc_pct"] = round(_f(adjusted.get("long_alloc_pct")) * factor, 4)
                    adjusted["aggression_reduced"] = True
                    prev = str(adjusted.get("aggression_reduction_reason") or "")
                    adjusted["aggression_reduction_reason"] = ",".join([x for x in [prev, "market_extension_" + str(guard.get("action"))] if x])
                    adjusted["aggression_reduction_factor"] = round(_f(adjusted.get("aggression_reduction_factor"), 1.0) * factor, 4)
                    adjusted["market_extension_guard"] = {"action": guard.get("action"), "long_alloc_factor": factor, "score_bump": guard.get("score_bump")}
            except Exception:
                pass
            return adjusted
        mod.apply_aggression_adjustments = apply_aggression_adjustments
    orig_quality = getattr(mod, "entry_quality_check", None)
    if callable(orig_quality):
        def entry_quality_check(signal, params, market, exclude_symbol=None):
            try:
                guard = (market or {}).get("market_extension_guard") or compute_guard(mod)
                side = str((signal or {}).get("side", "long")).lower()
                score = _f((signal or {}).get("score"))
                if side == "long" and guard.get("block_chase_longs") and score < EXCEPTIONAL_SCORE:
                    return False, {"reason": "market_extension_chase_guard", "symbol": (signal or {}).get("symbol"), "score": round(score, 6), "required_exceptional_score": round(EXCEPTIONAL_SCORE, 6), "guard_action": guard.get("action"), "extended_symbols": guard.get("extended_symbols", []), "bearish_rejection_symbols": guard.get("bearish_rejection_symbols", [])}
            except Exception:
                pass
            return orig_quality(signal, params, market, exclude_symbol=exclude_symbol)
        mod.entry_quality_check = entry_quality_check
    orig_feedback = getattr(mod, "feedback_loop_status", None)
    if callable(orig_feedback):
        def feedback_loop_status(*args, **kwargs):
            payload = orig_feedback(*args, **kwargs)
            try:
                market = kwargs.get("market") if "market" in kwargs else (args[0] if args else None)
                guard = (market or {}).get("market_extension_guard") if isinstance(market, dict) else None
                guard = guard or compute_guard(mod)
                if isinstance(payload, dict):
                    payload["market_extension_guard"] = {"action": guard.get("action"), "score_bump": guard.get("score_bump"), "long_alloc_factor": guard.get("long_alloc_factor"), "block_chase_longs": guard.get("block_chase_longs"), "extended_symbols": guard.get("extended_symbols", []), "bearish_rejection_symbols": guard.get("bearish_rejection_symbols", []), "bullish_confirmation_symbols": guard.get("bullish_confirmation_symbols", [])}
                    if guard.get("action") not in {None, "normal", "bullish_confirmation_ok"}:
                        actions = payload.setdefault("actions", [])
                        label = "market_extension_" + str(guard.get("action"))
                        if isinstance(actions, list) and label not in actions:
                            actions.append(label)
                    if _f(guard.get("score_bump")) > 0 and payload.get("dynamic_min_long_score") is not None:
                        payload["dynamic_min_long_score"] = round(_f(payload.get("dynamic_min_long_score")) + _f(guard.get("score_bump")), 6)
            except Exception:
                pass
            return payload
        mod.feedback_loop_status = feedback_loop_status
    _PATCHED.add(id(mod))
    return True


def register_routes(flask_app: Any = None, module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    _patch_core(module)
    if flask_app is None and module is not None:
        flask_app = getattr(module, "app", None)
    if flask_app is None:
        return {"status": "skipped", "version": VERSION, "reason": "flask_app_not_available"}
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify, request
    def market_extension_status():
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
        return jsonify(compute_guard(module, force=force))
    def fibonacci_status():
        guard = compute_guard(module, force=False)
        return jsonify({"status": guard.get("status", "ok"), "type": "fibonacci_status", "version": VERSION, "generated_local": _now(module), "fibonacci": {x.get("symbol"): x.get("fibonacci") for x in guard.get("indexes", []) if isinstance(x, dict)}, "note": "Fibonacci levels are references, not standalone trade triggers."})
    existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    if "/paper/market-extension-status" not in existing:
        flask_app.add_url_rule("/paper/market-extension-status", "paper_market_extension_status", market_extension_status)
    if "/paper/fibonacci-status" not in existing:
        flask_app.add_url_rule("/paper/fibonacci-status", "paper_fibonacci_status", fibonacci_status)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/market-extension-status", "/paper/fibonacci-status"]}


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    patched = _patch_core(module)
    routes = register_routes(getattr(module, "app", None), module) if module is not None else {"status": "skipped"}
    return {"status": "ok", "version": VERSION, "enabled": ENABLED, "patched_core": patched or (id(module) in _PATCHED if module is not None else False), "route_status": routes}
