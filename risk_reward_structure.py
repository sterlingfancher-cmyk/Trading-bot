"""VWAP/EMA/Fibonacci reward-risk gate and structure-based stop overlay."""
from __future__ import annotations

import datetime as dt
import functools
import json
import math
import os
import time
from typing import Any, Dict, List

import numpy as np

VERSION = "risk-reward-structure-vwap-ema-fib-2026-05-16"
ENABLED = os.getenv("RISK_REWARD_STRUCTURE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_RR = float(os.getenv("RISK_REWARD_MIN_RR", "1.55"))
IDEAL_RR = float(os.getenv("RISK_REWARD_IDEAL_RR", "2.0"))
MAX_RISK_PER_TRADE_PCT = float(os.getenv("RISK_REWARD_MAX_RISK_PER_TRADE_PCT", "0.004"))
STOP_MIN_PCT = float(os.getenv("RISK_REWARD_STOP_MIN_PCT", "0.008"))
STOP_MAX_PCT = float(os.getenv("RISK_REWARD_STOP_MAX_PCT", "0.045"))
ATR_PERIOD = int(os.getenv("RISK_REWARD_ATR_PERIOD", "14"))
SWING_LOOKBACK = int(os.getenv("RISK_REWARD_SWING_LOOKBACK", "18"))
ATR_BUFFER = float(os.getenv("RISK_REWARD_ATR_STOP_BUFFER", "0.35"))
STRICT_TREND = os.getenv("RISK_REWARD_STRICT_TREND", "true").lower() not in {"0", "false", "no", "off"}
EXCEPTIONAL_SCORE = float(os.getenv("RISK_REWARD_EXCEPTIONAL_SCORE", "0.040"))
CACHE_TTL = int(os.getenv("RISK_REWARD_CACHE_TTL_SECONDS", "120"))

_APPLIED: Dict[str, Any] = {}
_CACHE: Dict[str, Dict[str, Any]] = {}
_DECISIONS: List[Dict[str, Any]] = []
_REGISTERED: set[int] = set()


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        y = float(x)
        return default if math.isnan(y) or math.isinf(y) else y
    except Exception:
        return default


def _arr(x: Any) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float)
        return a[np.isfinite(a)]
    except Exception:
        return np.array([], dtype=float)


def _ema(values: np.ndarray, period: int) -> float | None:
    v = _arr(values)
    if len(v) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = float(v[0])
    for x in v[1:]:
        out = float(x) * alpha + out * (1.0 - alpha)
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float | None:
    h, l, c = _arr(high), _arr(low), _arr(close)
    n = min(len(h), len(l), len(c))
    if n < ATR_PERIOD + 2:
        return None
    h, l, c = h[-n:], l[-n:], c[-n:]
    tr = []
    prev = float(c[0])
    for i in range(1, n):
        tr.append(max(float(h[i] - l[i]), abs(float(h[i]) - prev), abs(float(l[i]) - prev)))
        prev = float(c[i])
    return float(np.mean(tr[-ATR_PERIOD:])) if len(tr) >= ATR_PERIOD else None


def _vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> float | None:
    h, l, c, v = _arr(high), _arr(low), _arr(close), _arr(volume)
    n = min(len(h), len(l), len(c), len(v), 78)
    if n < 5 or float(np.sum(v[-n:])) <= 0:
        return None
    typical = (h[-n:] + l[-n:] + c[-n:]) / 3.0
    return float(np.sum(typical * v[-n:]) / np.sum(v[-n:]))


def _candle(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> Dict[str, Any]:
    o, h, l, c = _arr(open_), _arr(high), _arr(low), _arr(close)
    n = min(len(o), len(h), len(l), len(c))
    if n < 3:
        return {"pattern": "insufficient_data", "bearish_rejection": False, "bullish_rejection": False}
    op, hi, lo, cl = float(o[-1]), float(h[-1]), float(l[-1]), float(c[-1])
    prev_o, prev_c = float(o[-2]), float(c[-2])
    rng = max(hi - lo, 1e-9)
    body = abs(cl - op)
    upper = hi - max(op, cl)
    lower = min(op, cl) - lo
    bear = (cl < op and upper >= max(body * 1.5, rng * 0.30)) or (cl < op and prev_c > prev_o and op >= prev_c and cl <= prev_o)
    bull = (cl > op and lower >= max(body * 1.5, rng * 0.30)) or (cl > op and prev_c < prev_o and op <= prev_c and cl >= prev_o)
    return {
        "pattern": "bearish_rejection" if bear else "bullish_rejection" if bull else "neutral",
        "bearish_rejection": bool(bear),
        "bullish_rejection": bool(bull),
        "upper_wick_pct": round(upper / rng * 100.0, 2),
        "lower_wick_pct": round(lower / rng * 100.0, 2),
    }


def _arrays(core: Any, symbol: str) -> Dict[str, np.ndarray]:
    symbol = str(symbol).upper()
    hit = _CACHE.get(symbol)
    if hit and time.time() - float(hit.get("ts", 0)) <= CACHE_TTL:
        return hit.get("arrays", {})
    out: Dict[str, np.ndarray] = {}
    try:
        df = core.fetch_intraday(symbol) if callable(getattr(core, "fetch_intraday", None)) else None
        raw = core.intraday_arrays(df) if df is not None and callable(getattr(core, "intraday_arrays", None)) else {}
        out = {k: _arr(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    except Exception as exc:
        out = {"error": np.array([])}
        _CACHE[symbol] = {"ts": time.time(), "arrays": out, "error": str(exc)}
        return out
    _CACHE[symbol] = {"ts": time.time(), "arrays": out}
    return out


def build_plan(core: Any, signal: Dict[str, Any], market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    symbol = str(signal.get("symbol") or "").upper()
    side = str(signal.get("side", "long")).lower()
    entry = _f(signal.get("price", signal.get("entry", signal.get("last_price"))))
    if not symbol or entry <= 0:
        return {"ok": False, "reason": "missing_symbol_or_entry", "version": VERSION}
    a = _arrays(core, symbol)
    close, open_, high, low, vol = (_arr(a.get(k)) for k in ("close", "open", "high", "low", "volume"))
    n = min(len(close), len(high), len(low))
    if n < max(25, ATR_PERIOD + 5):
        fallback = max(STOP_MIN_PCT, min(STOP_MAX_PCT, 0.028))
        stop = entry * (1 - fallback) if side == "long" else entry * (1 + fallback)
        target = entry + IDEAL_RR * (entry - stop) if side == "long" else entry - IDEAL_RR * (stop - entry)
        return {"ok": False, "fallback": True, "reason": "not_enough_intraday_data", "symbol": symbol, "side": side, "entry": round(entry, 4), "planned_stop": round(stop, 4), "planned_target": round(target, 4), "stop_risk_pct": round(fallback * 100, 2), "risk_reward": IDEAL_RR, "version": VERSION}
    session = min(n, 78)
    session_high, session_low = float(np.max(high[-session:])), float(np.min(low[-session:]))
    rng = max(session_high - session_low, entry * STOP_MIN_PCT)
    atr = _atr(high, low, close) or max(entry * STOP_MIN_PCT, rng / max(session, 1))
    vwap, ema9, ema20 = _vwap(high, low, close, vol), _ema(close, 9), _ema(close, 20)
    swing_low = float(np.min(low[-min(SWING_LOOKBACK, n):])); swing_high = float(np.max(high[-min(SWING_LOOKBACK, n):]))
    fib382 = session_high - 0.382 * rng; fib50 = session_high - 0.5 * rng; fib618 = session_high - 0.618 * rng
    fib_ext_long = session_high + 0.272 * rng; fib_ext_short = session_low - 0.272 * rng
    if side == "short":
        resistance = [x for x in (swing_high, vwap, ema9, ema20, fib382, fib50, fib618) if x and x > entry]
        base = min(resistance) if resistance else entry * (1 + min(STOP_MAX_PCT, max(STOP_MIN_PCT, atr / entry * 1.5)))
        stop = min(max(base + atr * ATR_BUFFER, entry * (1 + STOP_MIN_PCT)), entry * (1 + STOP_MAX_PCT))
        risk = max(stop - entry, entry * STOP_MIN_PCT)
        target = min(session_low, fib_ext_short, entry - max(atr * 2.0, risk * MIN_RR))
        trend_ok = bool((vwap is None or entry <= vwap * 1.002) and (ema9 is None or ema20 is None or ema9 <= ema20 * 1.003 or entry <= ema20))
        reward = max(entry - target, 0.0)
    else:
        support = [x for x in (swing_low, vwap, ema9, ema20, fib382, fib50, fib618) if x and x < entry]
        base = max(support) if support else entry * (1 - min(STOP_MAX_PCT, max(STOP_MIN_PCT, atr / entry * 1.5)))
        stop = max(min(base - atr * ATR_BUFFER, entry * (1 - STOP_MIN_PCT)), entry * (1 - STOP_MAX_PCT))
        risk = max(entry - stop, entry * STOP_MIN_PCT)
        target = max(session_high, fib_ext_long, entry + max(atr * 2.0, risk * MIN_RR))
        trend_ok = bool((vwap is None or entry >= vwap * 0.998) and (ema9 is None or ema20 is None or ema9 >= ema20 * 0.997 or entry >= ema20))
        reward = max(target - entry, 0.0)
    rr = reward / risk if risk > 0 else 0.0
    return {
        "ok": True, "reason": "structure_plan_ready", "symbol": symbol, "side": side,
        "entry": round(entry, 4), "planned_stop": round(stop, 4), "planned_target": round(target, 4),
        "risk_per_share": round(risk, 4), "stop_risk_pct": round(risk / entry * 100.0, 2),
        "risk_reward": round(rr, 2), "min_required_reward_risk": MIN_RR, "ideal_reward_risk": IDEAL_RR,
        "atr": round(atr, 4), "vwap": round(vwap, 4) if vwap else None, "ema9": round(ema9, 4) if ema9 else None,
        "ema20": round(ema20, 4) if ema20 else None, "session_high": round(session_high, 4), "session_low": round(session_low, 4),
        "swing_low": round(swing_low, 4), "swing_high": round(swing_high, 4),
        "fibonacci": {"fib_382": round(fib382, 4), "fib_500": round(fib50, 4), "fib_618": round(fib618, 4), "fib_ext_long_1272": round(fib_ext_long, 4), "fib_ext_short_1272": round(fib_ext_short, 4)},
        "trend_confirmation": {"vwap_ema_confirmed": trend_ok, "price_vs_vwap_pct": round((entry / vwap - 1) * 100, 2) if vwap else None, "ema9_vs_ema20_pct": round((ema9 / ema20 - 1) * 100, 2) if ema9 and ema20 else None},
        "candle": _candle(open_, high, low, close), "version": VERSION,
    }


def _remember(row: Dict[str, Any]) -> None:
    row = dict(row); row.setdefault("generated_local", _now())
    _DECISIONS.append(row); del _DECISIONS[:-150]


def _wrap_entry_quality(core: Any, original: Any):
    @functools.wraps(original)
    def wrapped(signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], exclude_symbol: Any = None):
        result = original(signal, params, market, exclude_symbol=exclude_symbol)
        if not ENABLED or not (isinstance(result, tuple) and result and result[0]) or not isinstance(signal, dict):
            return result
        info = result[1] if len(result) > 1 and isinstance(result[1], dict) else {}
        try:
            side = str(signal.get("side", "long")).lower(); score = _f(signal.get("score"))
            plan = build_plan(core, signal, market); signal["risk_plan"] = plan
            exceptional = score >= EXCEPTIONAL_SCORE
            if plan.get("ok") and _f(plan.get("risk_reward")) < MIN_RR:
                _remember({"allowed": False, "reason": "risk_reward_below_minimum", "symbol": signal.get("symbol"), "risk_plan": plan})
                return False, {**info, "reason": "risk_reward_below_minimum", "structure_risk_reward": plan}
            trend_ok = bool((plan.get("trend_confirmation") or {}).get("vwap_ema_confirmed", True))
            if plan.get("ok") and STRICT_TREND and not trend_ok and not exceptional:
                _remember({"allowed": False, "reason": "vwap_ema_trend_not_confirmed", "symbol": signal.get("symbol"), "risk_plan": plan})
                return False, {**info, "reason": "vwap_ema_trend_not_confirmed", "structure_risk_reward": plan}
            candle = plan.get("candle") or {}
            if side == "long" and candle.get("bearish_rejection") and not exceptional:
                _remember({"allowed": False, "reason": "bearish_candle_rejection_near_entry", "symbol": signal.get("symbol"), "risk_plan": plan})
                return False, {**info, "reason": "bearish_candle_rejection_near_entry", "structure_risk_reward": plan}
            if side == "short" and candle.get("bullish_rejection") and not exceptional:
                _remember({"allowed": False, "reason": "bullish_candle_rejection_near_entry", "symbol": signal.get("symbol"), "risk_plan": plan})
                return False, {**info, "reason": "bullish_candle_rejection_near_entry", "structure_risk_reward": plan}
            try:
                equity = max(_f(core.portfolio.get("equity", core.portfolio.get("cash", 0.0))), 0.01)
                est = core.estimated_trade_allocation(signal, params) if callable(getattr(core, "estimated_trade_allocation", None)) else 0.0
                risk_pct = max(_f(plan.get("stop_risk_pct")) / 100.0, STOP_MIN_PCT)
                projected = _f(est) * risk_pct; max_dollars = equity * MAX_RISK_PER_TRADE_PCT
                if projected > max_dollars > 0:
                    factor = max(0.35, min(1.0, max_dollars / projected))
                    signal["alloc_factor"] = round(min(_f(signal.get("alloc_factor", 1.0), 1.0), factor), 4)
                    plan["risk_sizing"] = {"max_risk_per_trade_pct": round(MAX_RISK_PER_TRADE_PCT * 100, 2), "projected_risk_dollars_before": round(projected, 2), "max_risk_dollars": round(max_dollars, 2), "alloc_factor_after_risk_sizing": signal["alloc_factor"]}
            except Exception:
                pass
            _remember({"allowed": True, "reason": "structure_risk_reward_ok", "symbol": signal.get("symbol"), "risk_plan": plan})
            return True, {**info, "structure_risk_reward": plan}
        except Exception as exc:
            _remember({"allowed": True, "reason": "structure_layer_error_allow_core", "error": str(exc), "symbol": signal.get("symbol")})
            return result
    return wrapped


def _wrap_enter(core: Any, original: Any):
    @functools.wraps(original)
    def wrapped(signal: Dict[str, Any], params: Dict[str, Any], market_mode: Any = None):
        result = original(signal, params, market_mode=market_mode)
        try:
            if isinstance(result, dict) and not result.get("blocked") and isinstance(signal, dict):
                sym = str(signal.get("symbol", "")).upper(); plan = signal.get("risk_plan")
                pos = core.portfolio.get("positions", {}).get(sym)
                if isinstance(pos, dict) and isinstance(plan, dict):
                    pos.update({"risk_plan": plan, "planned_stop": plan.get("planned_stop"), "planned_target": plan.get("planned_target"), "risk_reward": plan.get("risk_reward"), "stop_model": "structure_vwap_ema_fib_atr"})
                    result["risk_plan"] = plan
        except Exception:
            pass
        return result
    return wrapped


def _structure_exits(core: Any, mode: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    latest, exit_fn = getattr(core, "latest_price", None), getattr(core, "exit_position", None)
    if not callable(latest) or not callable(exit_fn):
        return out
    for sym, pos in list((core.portfolio.get("positions", {}) or {}).items()):
        if not isinstance(pos, dict):
            continue
        plan = pos.get("risk_plan") if isinstance(pos.get("risk_plan"), dict) else {}
        stop = _f(pos.get("planned_stop") or plan.get("planned_stop"))
        if stop <= 0:
            continue
        try:
            px = latest(sym) or pos.get("last_price"); px = _f(px)
            side = str(pos.get("side", "long")).lower()
            hit = px > 0 and ((side == "long" and px <= stop) or (side == "short" and px >= stop))
            if hit:
                reason = "structure_stop_long" if side == "long" else "structure_stop_short"
                row = exit_fn(sym, px, reason, market_mode=mode, extra={"stop_model": "structure_vwap_ema_fib_atr", "planned_stop": round(stop, 4), "planned_target": plan.get("planned_target"), "risk_reward": plan.get("risk_reward")})
                if row: out.append(row)
        except Exception as exc:
            _remember({"reason": "structure_exit_check_error", "symbol": sym, "error": str(exc)})
    return out


def _wrap_manage_exits(core: Any, original: Any):
    @functools.wraps(original)
    def wrapped(params: Dict[str, Any], market: Dict[str, Any]):
        mode = str((market or {}).get("market_mode", "neutral"))
        pre = _structure_exits(core, mode)
        patched = dict(params or {})
        try:
            if any(isinstance(p, dict) and (p.get("risk_plan") or p.get("planned_stop")) for p in (core.portfolio.get("positions", {}) or {}).values()):
                patched["stop_loss"] = -max(abs(_f(patched.get("stop_loss"), -STOP_MAX_PCT)), STOP_MAX_PCT)
                patched["structure_stop_override_active"] = True
        except Exception:
            pass
        return pre + list(original(patched, market) or [])
    return wrapped


def apply(core: Any) -> Dict[str, Any]:
    applied: Dict[str, Any] = {"version": VERSION, "enabled": ENABLED}
    try:
        if callable(getattr(core, "entry_quality_check", None)) and not getattr(core.entry_quality_check, "_risk_reward_wrapped", False):
            core.entry_quality_check = _wrap_entry_quality(core, core.entry_quality_check); core.entry_quality_check._risk_reward_wrapped = True
            applied["entry_quality_check"] = "wrapped"
        if callable(getattr(core, "enter_position", None)) and not getattr(core.enter_position, "_risk_reward_wrapped", False):
            core.enter_position = _wrap_enter(core, core.enter_position); core.enter_position._risk_reward_wrapped = True
            applied["enter_position"] = "wrapped"
        if callable(getattr(core, "manage_exits", None)) and not getattr(core.manage_exits, "_risk_reward_wrapped", False):
            core.manage_exits = _wrap_manage_exits(core, core.manage_exits); core.manage_exits._risk_reward_wrapped = True
            applied["manage_exits"] = "wrapped"
        core.RISK_REWARD_STRUCTURE_VERSION = VERSION
        core.build_risk_reward_structure_plan = lambda signal, market=None: build_plan(core, signal, market)
    except Exception as exc:
        applied["error"] = str(exc)
    _APPLIED.clear(); _APPLIED.update(applied)
    return {"status": "ok" if "error" not in applied else "error", **applied}


def status(core: Any) -> Dict[str, Any]:
    positions = []
    try:
        for sym, pos in (core.portfolio.get("positions", {}) or {}).items():
            if isinstance(pos, dict):
                positions.append({"symbol": sym, "side": pos.get("side"), "entry": pos.get("entry"), "last_price": pos.get("last_price"), "planned_stop": pos.get("planned_stop"), "planned_target": pos.get("planned_target"), "risk_reward": pos.get("risk_reward"), "stop_model": pos.get("stop_model")})
    except Exception:
        pass
    return {"status": "ok", "type": "risk_reward_structure_status", "version": VERSION, "generated_local": _now(), "enabled": ENABLED, "applied": dict(_APPLIED), "settings": {"min_reward_risk": MIN_RR, "ideal_reward_risk": IDEAL_RR, "max_risk_per_trade_pct": round(MAX_RISK_PER_TRADE_PCT * 100, 2), "stop_min_pct": round(STOP_MIN_PCT * 100, 2), "stop_max_pct": round(STOP_MAX_PCT * 100, 2), "strict_vwap_ema_trend": STRICT_TREND}, "open_position_risk_plans": positions, "latest_decisions": _DECISIONS[-25:]}


def register_routes(app: Any, core: Any) -> None:
    if app is None or id(app) in _REGISTERED:
        return
    _REGISTERED.add(id(app))

    @app.route("/paper/risk-reward-status")
    def risk_reward_status_route():
        return app.response_class(response=json.dumps(status(core), indent=2, sort_keys=True), status=200, mimetype="application/json")
