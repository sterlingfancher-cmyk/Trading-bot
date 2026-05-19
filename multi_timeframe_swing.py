from __future__ import annotations

import os
import time
from typing import Any, Dict

import numpy as np
from flask import jsonify, request

VERSION = "multi-timeframe-swing-hold-2026-05-19-v1"
ENABLED = os.environ.get("MULTI_TIMEFRAME_SWING_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
CACHE_TTL_SECONDS = int(os.environ.get("MULTI_TIMEFRAME_SWING_CACHE_TTL_SECONDS", "1800"))
DAILY_LOOKBACK_PERIOD = os.environ.get("MULTI_TIMEFRAME_DAILY_LOOKBACK", "9mo")
HOURLY_LOOKBACK_PERIOD = os.environ.get("MULTI_TIMEFRAME_HOURLY_LOOKBACK", "30d")
LEADER_SCORE_BONUS = float(os.environ.get("SWING_LEADER_SCORE_BONUS", "0.0040"))
SWING_SCORE_BONUS = float(os.environ.get("SWING_CANDIDATE_SCORE_BONUS", "0.0025"))
AVOID_CHASE_SCORE_PENALTY = float(os.environ.get("SWING_AVOID_CHASE_SCORE_PENALTY", "0.0030"))
DOWNTICK_SCORE_DISCOUNT = float(os.environ.get("SWING_DOWN_MARKET_SCORE_DISCOUNT", "0.0040"))
MIN_EXCEPTION_SCORE = float(os.environ.get("SWING_MIN_EXCEPTION_SCORE", "0.0110"))
MAX_INITIAL_RISK_PCT = float(os.environ.get("SWING_MAX_INITIAL_RISK_PCT", "0.0200"))
MAX_HOLD_DAYS = float(os.environ.get("SWING_MAX_HOLD_DAYS", "10"))
LEADER_ALLOC_FACTOR = float(os.environ.get("SWING_LEADER_ALLOC_FACTOR", "0.85"))
CANDIDATE_ALLOC_FACTOR = float(os.environ.get("SWING_CANDIDATE_ALLOC_FACTOR", "0.70"))
AVOID_CHASE_ALLOC_FACTOR = float(os.environ.get("SWING_AVOID_CHASE_ALLOC_FACTOR", "0.40"))

_PROFILES: Dict[str, Dict[str, Any]] = {}
_ORIGINALS: Dict[str, Any] = {}
_INTRADAY_EXIT_REASONS = {
    "profit_lock_long_level_3", "profit_lock_long_breakeven",
    "profit_lock_long_no_red", "trailing_stop_long",
}


def _sf(v, default=0.0):
    try:
        return default if v is None else float(v)
    except Exception:
        return default


def _clean(arr):
    try:
        a = np.asarray(arr).astype(float).flatten()
        return a[~np.isnan(a)]
    except Exception:
        return np.array([])


def _pct(prices, bars):
    prices = _clean(prices)
    if len(prices) <= bars or float(prices[-bars]) == 0:
        return 0.0
    return float((prices[-1] / prices[-bars]) - 1.0)


def _sma(prices, bars):
    prices = _clean(prices)
    if len(prices) < bars:
        return None
    return float(np.mean(prices[-bars:]))


def _series(core, df, col="Close"):
    try:
        return _clean(core.price_series(df, col))
    except Exception:
        return np.array([])


def _bars(core, symbol, period, interval):
    try:
        return _series(core, core.download_prices(symbol, period=period, interval=interval), "Close")
    except Exception:
        return np.array([])


def _bench(core, symbol):
    sector = getattr(core, "SYMBOL_SECTOR", {}).get(symbol, "")
    return sector if sector in {"XLK", "XLY", "XLI", "XLF", "XLV", "XLE", "XLU", "XLP"} else "QQQ"


def multi_timeframe_profile(core, symbol, market=None, force=False):
    market = market or {}
    symbol = str(symbol or "").upper()
    now = time.time()
    cached = _PROFILES.get(symbol)
    if cached and not force and now - float(cached.get("ts", 0)) < CACHE_TTL_SECONDS:
        return dict(cached.get("profile", {}))

    daily = _bars(core, symbol, DAILY_LOOKBACK_PERIOD, "1d")
    hourly = _bars(core, symbol, HOURLY_LOOKBACK_PERIOD, "1h")
    bench_symbol = _bench(core, symbol)
    bench = _bars(core, bench_symbol, DAILY_LOOKBACK_PERIOD, "1d")
    qqq = bench if bench_symbol == "QQQ" else _bars(core, "QQQ", DAILY_LOOKBACK_PERIOD, "1d")

    px = float(daily[-1]) if len(daily) else 0.0
    ma20, ma50, ma100 = _sma(daily, 20), _sma(daily, 50), _sma(daily, 100)
    h20, h50 = _sma(hourly, 20), _sma(hourly, 50)
    r5, r20, r60 = _pct(daily, 5), _pct(daily, 20), _pct(daily, 60)
    b20, b60, q20 = _pct(bench, 20), _pct(bench, 60), _pct(qqq, 20)
    rs20, rs60, rsq20 = r20 - b20, r60 - b60, r20 - q20

    above20 = bool(ma20 and px > ma20)
    above50 = bool(ma50 and px > ma50)
    ma_stack = bool(ma20 and ma50 and ma20 >= ma50)
    long_stack = bool(ma20 and ma50 and ma100 and px > ma20 >= ma50 >= ma100)
    hourly_ok = bool(len(hourly) >= 50 and h20 and h50 and hourly[-1] > h20 >= h50 * 0.995)

    score = 0.0
    for condition, points in (
        (above20, .18), (above50, .14), (ma_stack, .18), (long_stack, .15),
        (r20 > 0, .12), (r60 > 0, .10), (rs20 > 0, .14), (rs60 > 0, .11),
        (hourly_ok, .10),
    ):
        if condition:
            score += points

    ext20 = ((px / ma20) - 1.0) if ma20 and ma20 > 0 else 0.0
    overextended = bool(r5 > 0.18 or ext20 > 0.16)
    if long_stack and r20 > 0 and rs20 > 0:
        trend = "strong_uptrend"
    elif above20 and ma_stack and r20 > -0.02:
        trend = "constructive_uptrend"
    elif ma20 and px < ma20 and r20 < 0:
        trend = "weak_or_breaking"
    else:
        trend = "mixed"

    sector = getattr(core, "SYMBOL_SECTOR", {}).get(symbol, "UNKNOWN")
    bucket = getattr(core, "SYMBOL_BUCKET", {}).get(symbol, "default")
    sector_leader = sector in (market.get("sector_leaders", []) or [])
    bear = bool(market.get("bear_confirmed", False))
    broad_soft = bool(market.get("broad_market_soft", False))

    classification = "intraday_trade"
    if overextended and score >= .65:
        classification = "avoid_chase"
    if score >= .72 and trend in {"strong_uptrend", "constructive_uptrend"} and not overextended:
        classification = "swing_candidate"
    if score >= .88 and trend == "strong_uptrend" and (sector_leader or rsq20 > .025):
        classification = "leader_hold"
    if bear or (broad_soft and classification in {"leader_hold", "swing_candidate"} and rs20 <= 0 and not sector_leader):
        classification = "intraday_trade"

    if classification == "leader_hold":
        bonus, alloc = LEADER_SCORE_BONUS, LEADER_ALLOC_FACTOR
    elif classification == "swing_candidate":
        bonus, alloc = SWING_SCORE_BONUS, CANDIDATE_ALLOC_FACTOR
    elif classification == "avoid_chase":
        bonus, alloc = -AVOID_CHASE_SCORE_PENALTY, AVOID_CHASE_ALLOC_FACTOR
    else:
        bonus, alloc = 0.0, 1.0

    profile = {
        "symbol": symbol, "version": VERSION, "enabled": bool(ENABLED),
        "classification": classification, "daily_trend": trend,
        "trend_score": round(float(score), 4), "score_bonus": round(float(bonus), 6),
        "alloc_factor": round(float(alloc), 4), "bucket": bucket, "sector": sector,
        "benchmark": bench_symbol, "last_price": round(px, 4),
        "ret_5d_pct": round(r5 * 100, 2), "ret_20d_pct": round(r20 * 100, 2),
        "ret_60d_pct": round(r60 * 100, 2), "benchmark_20d_pct": round(b20 * 100, 2),
        "benchmark_60d_pct": round(b60 * 100, 2),
        "relative_strength_20d_pct": round(rs20 * 100, 2),
        "relative_strength_60d_pct": round(rs60 * 100, 2),
        "rs_vs_qqq_20d_pct": round(rsq20 * 100, 2),
        "above_20dma": above20, "above_50dma": above50,
        "ma_stack_20_over_50": ma_stack, "long_stack_20_50_100": long_stack,
        "hourly_confirmed": hourly_ok, "overextended": overextended,
        "extended_from_20dma_pct": round(ext20 * 100, 2), "sector_leader": bool(sector_leader),
        "broad_market_soft": broad_soft, "bear_confirmed": bear, "generated_ts": int(now),
    }
    _PROFILES[symbol] = {"ts": now, "profile": dict(profile)}
    return profile


def _eligible(profile):
    return profile.get("classification") in {"leader_hold", "swing_candidate"} or (
        profile.get("daily_trend") in {"strong_uptrend", "constructive_uptrend"}
        and _sf(profile.get("trend_score")) >= .62
        and _sf(profile.get("relative_strength_20d_pct")) >= -.5
    )


def _held_days(pos):
    return max(0.0, (time.time() - _sf(pos.get("entry_time"), time.time())) / 86400.0)


def _wrap_scan(core):
    original = _ORIGINALS.get("scan_signals")
    def wrapped(market):
        longs, shorts, rejected = original(market)
        if not ENABLED:
            return longs, shorts, rejected
        for sig in longs:
            try:
                prof = multi_timeframe_profile(core, sig.get("symbol"), market)
                cls = prof.get("classification", "intraday_trade")
                sig["multi_timeframe"] = prof
                sig["trade_class"] = cls
                sig["swing_hold_candidate"] = cls in {"leader_hold", "swing_candidate"}
                sig["score"] = round(max(0.0, _sf(sig.get("score")) + _sf(prof.get("score_bonus"))), 6)
                if cls in {"leader_hold", "swing_candidate"}:
                    sig.setdefault("entry_context", "multi_timeframe_swing_hold")
                if cls == "avoid_chase":
                    sig.setdefault("entry_context", "multi_timeframe_avoid_chase")
                sig["alloc_factor"] = round(min(_sf(sig.get("alloc_factor"), 1.0), _sf(prof.get("alloc_factor"), 1.0)), 4)
            except Exception as exc:
                sig["multi_timeframe_error"] = str(exc)
        return sorted(longs, key=lambda x: _sf(x.get("score")), reverse=True), shorts, rejected
    core.scan_signals = wrapped


def _wrap_entry_quality(core):
    original = _ORIGINALS.get("entry_quality_check")
    def wrapped(signal, params, market, exclude_symbol=None):
        ok, info = original(signal, params, market, exclude_symbol=exclude_symbol)
        if ok or not ENABLED or signal.get("side", "long") != "long":
            return ok, info
        if market.get("bear_confirmed") or market.get("market_mode") in {"risk_off", "crash_warning", "defensive_rotation"}:
            return ok, info
        prof = signal.get("multi_timeframe") or multi_timeframe_profile(core, signal.get("symbol"), market)
        if prof.get("classification") not in {"leader_hold", "swing_candidate"} or not _eligible(prof):
            return ok, info
        required = _sf(info.get("required_score"), _sf(core.min_entry_score_for_market(market, "long"))) if isinstance(info, dict) else _sf(core.min_entry_score_for_market(market, "long"))
        required = max(MIN_EXCEPTION_SCORE, required - DOWNTICK_SCORE_DISCOUNT)
        score = _sf(signal.get("score"))
        if score < required:
            return ok, info
        signal["entry_context"] = "multi_timeframe_leader_exception"
        signal["trade_class"] = prof.get("classification")
        signal["swing_hold_candidate"] = True
        signal["multi_timeframe"] = prof
        signal["alloc_factor"] = min(_sf(signal.get("alloc_factor", 1.0), 1.0), _sf(prof.get("alloc_factor", CANDIDATE_ALLOC_FACTOR), CANDIDATE_ALLOC_FACTOR))
        return True, {
            "reason": "multi_timeframe_leader_exception", "symbol": signal.get("symbol"),
            "score": round(score, 6), "required_score": round(required, 6),
            "classification": prof.get("classification"), "daily_trend": prof.get("daily_trend"),
            "trend_score": prof.get("trend_score"),
            "relative_strength_20d_pct": prof.get("relative_strength_20d_pct"),
            "broad_market_soft": bool(market.get("broad_market_soft", False)),
            "original_block": info,
        }
    core.entry_quality_check = wrapped


def _wrap_enter(core):
    original = _ORIGINALS.get("enter_position")
    def wrapped(signal, params, market_mode=None):
        result = original(signal, params, market_mode=market_mode)
        if not ENABLED or not result or result.get("blocked"):
            return result
        symbol = signal.get("symbol")
        pos = core.portfolio.get("positions", {}).get(symbol)
        prof = signal.get("multi_timeframe")
        if pos is not None and prof:
            cls = prof.get("classification", "intraday_trade")
            pos["trade_class"] = cls
            pos["swing_hold_candidate"] = cls in {"leader_hold", "swing_candidate"}
            pos["multi_timeframe"] = prof
            pos["max_initial_risk_pct"] = round(MAX_INITIAL_RISK_PCT * 100, 2)
            pos["max_hold_days"] = MAX_HOLD_DAYS
            result.update({"trade_class": cls, "swing_hold_candidate": pos["swing_hold_candidate"], "multi_timeframe": prof})
            try:
                last = core.portfolio.get("trades", [])[-1]
                if last.get("action") == "entry" and last.get("symbol") == symbol:
                    last.update({"trade_class": cls, "swing_hold_candidate": pos["swing_hold_candidate"], "multi_timeframe": prof})
            except Exception:
                pass
        return result
    core.enter_position = wrapped


def _wrap_exit(core):
    original = _ORIGINALS.get("exit_position")
    def wrapped(symbol, px, reason, market_mode=None, extra=None):
        pos = core.portfolio.get("positions", {}).get(symbol)
        if ENABLED and pos and pos.get("side", "long") == "long" and pos.get("trade_class") in {"leader_hold", "swing_candidate"}:
            prof = multi_timeframe_profile(core, symbol, core.portfolio.get("last_market") or {})
            pnl = core.position_pnl_pct(pos, px)
            days = _held_days(pos)
            protect = False
            guard_reason = None
            if reason in _INTRADAY_EXIT_REASONS and days <= MAX_HOLD_DAYS and _eligible(prof):
                protect, guard_reason = True, "swing_hold_intraday_exit_guard"
            elif reason == "stop_loss" and pnl > -MAX_INITIAL_RISK_PCT and days <= MAX_HOLD_DAYS and _eligible(prof):
                protect, guard_reason = True, "swing_hold_wider_initial_risk_guard"
            if protect:
                pos["last_price"] = float(px)
                pos["swing_exit_guard_last"] = {
                    "blocked_reason": reason, "guard_reason": guard_reason,
                    "price": round(float(px), 4), "pnl_pct": round(float(pnl) * 100, 2),
                    "held_days": round(days, 2), "profile_classification": prof.get("classification"),
                    "daily_trend": prof.get("daily_trend"), "trend_score": prof.get("trend_score"),
                    "time": int(time.time()),
                }
                return None
        return original(symbol, px, reason, market_mode=market_mode, extra=extra)
    core.exit_position = wrapped


def _wrap_rotation(core):
    original = _ORIGINALS.get("rotation_allowed")
    def wrapped(new_signal, weakest, market):
        symbol = weakest.get("symbol") if isinstance(weakest, dict) else None
        pos = core.portfolio.get("positions", {}).get(symbol)
        if ENABLED and pos and pos.get("side", "long") == "long" and pos.get("trade_class") in {"leader_hold", "swing_candidate"}:
            prof = multi_timeframe_profile(core, symbol, market)
            px = _sf(pos.get("last_price", pos.get("entry", 0.0)))
            pnl = core.position_pnl_pct(pos, px)
            days = _held_days(pos)
            if days <= MAX_HOLD_DAYS and pnl > -MAX_INITIAL_RISK_PCT and _eligible(prof):
                return False, {
                    "reason": "swing_hold_rotation_guard", "weakest_symbol": symbol,
                    "trade_class": pos.get("trade_class"), "held_days": round(days, 2),
                    "pnl_pct": round(float(pnl) * 100, 2), "daily_trend": prof.get("daily_trend"),
                    "trend_score": prof.get("trend_score"), "new_symbol": new_signal.get("symbol") if isinstance(new_signal, dict) else None,
                    "new_score": round(_sf(new_signal.get("score") if isinstance(new_signal, dict) else 0.0), 6),
                }
        return original(new_signal, weakest, market)
    core.rotation_allowed = wrapped


def status_payload(core, lightweight=False):
    positions = []
    for symbol, pos in (core.portfolio.get("positions", {}) or {}).items():
        px = _sf(pos.get("last_price", pos.get("entry", 0)))
        item = {
            "symbol": symbol, "side": pos.get("side", "long"),
            "trade_class": pos.get("trade_class", "intraday_trade"),
            "swing_hold_candidate": bool(pos.get("swing_hold_candidate", False)),
            "entry_context": pos.get("entry_context"), "last_price": round(px, 4),
            "pnl_pct": round(core.position_pnl_pct(pos, px) * 100, 2),
            "swing_exit_guard_last": pos.get("swing_exit_guard_last"),
        }
        if not lightweight:
            item["multi_timeframe"] = multi_timeframe_profile(core, symbol, core.portfolio.get("last_market") or {})
        positions.append(item)
    audit = core.portfolio.get("scanner_audit") or {}
    return {
        "status": "ok", "type": "multi_timeframe_swing_status", "version": VERSION,
        "enabled": bool(ENABLED), "trade_authority": "entry_scoring_and_exit_guard_overlay",
        "cache_ttl_seconds": CACHE_TTL_SECONDS, "cached_profiles_count": len(_PROFILES),
        "leader_score_bonus": LEADER_SCORE_BONUS, "swing_score_bonus": SWING_SCORE_BONUS,
        "down_market_score_discount": DOWNTICK_SCORE_DISCOUNT,
        "max_initial_risk_pct": round(MAX_INITIAL_RISK_PCT * 100, 2),
        "max_hold_days": MAX_HOLD_DAYS, "protected_exit_reasons": sorted(_INTRADAY_EXIT_REASONS),
        "positions": positions, "recent_long_signal_symbols": (audit.get("long_signals", []) or [])[:15],
        "recent_blocked_symbols": [b.get("symbol") for b in (audit.get("blocked_entries", []) or [])[:10] if isinstance(b, dict)],
        "classification_rules": {
            "intraday_trade": "normal tactical setup; intraday exits apply",
            "swing_candidate": "daily trend plus relative strength supports a multi-day hold",
            "leader_hold": "strong daily trend, sector/benchmark leadership, and hourly confirmation",
            "avoid_chase": "strong name but extended; reduce size/score and wait for pullback",
        },
        "safety": {
            "does_not_bypass_halts": True, "does_not_bypass_self_defense": True,
            "does_not_bypass_market_regime_protection": True,
            "stop_loss_may_widen_only_until_pct": round(MAX_INITIAL_RISK_PCT * 100, 2),
        },
    }


def _wrap_controls(core):
    original = _ORIGINALS.get("entry_controls_snapshot")
    def wrapped(*args, **kwargs):
        payload = original(*args, **kwargs)
        try:
            payload["multi_timeframe_swing"] = status_payload(core, lightweight=True)
        except Exception:
            payload["multi_timeframe_swing"] = {"status": "error"}
        return payload
    core.entry_controls_snapshot = wrapped


def apply(core):
    if getattr(core, "_multi_timeframe_swing_installed", False):
        return
    for name in ["scan_signals", "entry_quality_check", "enter_position", "exit_position", "rotation_allowed", "entry_controls_snapshot"]:
        _ORIGINALS[name] = getattr(core, name, None)
    core.multi_timeframe_profile = lambda symbol, market=None, force=False: multi_timeframe_profile(core, symbol, market, force)
    core.multi_timeframe_swing_status_payload = lambda lightweight=False: status_payload(core, lightweight)
    core.MULTI_TIMEFRAME_SWING_VERSION = VERSION
    _wrap_scan(core)
    _wrap_entry_quality(core)
    _wrap_enter(core)
    _wrap_exit(core)
    _wrap_rotation(core)
    _wrap_controls(core)
    core._multi_timeframe_swing_installed = True


def register_routes(app, core):
    def _response():
        force = str(request.args.get("refresh", "0")).lower() in {"1", "true", "yes", "on"}
        symbol = request.args.get("symbol")
        payload = status_payload(core, lightweight=not force)
        if symbol:
            s = symbol.upper()
            payload["requested_symbol"] = s
            payload["requested_profile"] = multi_timeframe_profile(core, s, core.portfolio.get("last_market") or {}, force=force)
        return jsonify(payload)
    for rule, endpoint in (("/paper/multi-timeframe-swing-status", "multi_timeframe_swing_status"), ("/paper/swing-hold-status", "swing_hold_status")):
        try:
            app.add_url_rule(rule, endpoint, _response)
        except Exception:
            pass
