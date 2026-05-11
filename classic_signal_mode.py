"""Classic signal mode hard gate.

Restores the earlier simpler walk-forward / higher-timeframe logic as the
primary trade-selection engine while keeping the newer operational safety stack.

This version is stricter than the initial classic patch:
- Every new long must pass classic daily-trend confirmation unless the EOD
  allocation window is active.
- High-beta pilot names require both classic confirmation and an exceptional
  score before a new intraday starter can be opened.
- Existing weak intraday positions are not allowed to be added to while they are
  down more than the early-loss threshold.
- Intraday scanner remains available, but only as a small pilot layer.
- Tech-heavy exposure remains allowed when the higher-timeframe signal confirms.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, List, Tuple

VERSION = "classic-signal-hard-gate-2026-05-11"

CACHE_TTL_SECONDS = float(os.environ.get("CLASSIC_SIGNAL_CACHE_TTL_SECONDS", "900"))
EOD_WINDOW_MINUTES = int(os.environ.get("EOD_ALLOCATION_WINDOW_MINUTES", os.environ.get("CLASSIC_SIGNAL_EOD_WINDOW_MINUTES", "45")))

# Higher-timeframe rules: simple, slower, and closer to the earlier cleaner
# walk-forward style. These are intentionally not hyper-optimized; they are
# durable filters designed to avoid noisy intraday over-trading.
MIN_RET_20D = float(os.environ.get("CLASSIC_SIGNAL_MIN_RET_20D", "0.00"))
MIN_RET_60D = float(os.environ.get("CLASSIC_SIGNAL_MIN_RET_60D", "-0.02"))
MAX_RET_5D_CHASE = float(os.environ.get("CLASSIC_SIGNAL_MAX_RET_5D_CHASE", "0.10"))
MAX_DRAWDOWN_60D = float(os.environ.get("CLASSIC_SIGNAL_MAX_DRAWDOWN_60D", "0.24"))
MIN_SCORE_TO_OVERRIDE = float(os.environ.get("CLASSIC_SIGNAL_EXCEPTIONAL_SCORE", "0.045"))
HIGH_BETA_MIN_SCORE = float(os.environ.get("CLASSIC_SIGNAL_HIGH_BETA_MIN_SCORE", "0.045"))
EARLY_LOSS_BLOCK_PCT = float(os.environ.get("CLASSIC_SIGNAL_EARLY_LOSS_BLOCK_PCT", "-0.015"))
EARLY_LOSS_WINDOW_SECONDS = int(os.environ.get("CLASSIC_SIGNAL_EARLY_LOSS_WINDOW_SECONDS", "7200"))

HIGH_BETA_SYMBOLS = {
    "RGTI", "QBTS", "IONQ", "SOUN", "BBAI", "AI", "APLD", "IREN", "HUT", "CIFR",
    "WULF", "CLSK", "MARA", "RIOT", "BTDR", "CORZ", "RKLB", "JOBY", "ACHR", "TEM",
    "RXRX", "SMCI", "ALAB", "ARM", "MRVL", "MU", "ACLS", "AAOI", "LITE", "COHR",
}

# Make intraday scanner a tightly controlled pilot. These do not cap tech
# exposure; they shrink intraday starter size and reduce rotation churn.
OVERRIDES = {
    "CLASSIC_SIGNAL_MODE_ENABLED": ("set", True),
    "CLASSIC_SIGNAL_HARD_GATE_ENABLED": ("set", True),
    "PRIMARY_SIGNAL_MODE": ("set", "classic_signal_plus_eod_hard_gate"),
    "INTRADAY_SCANNER_ROLE": ("set", "pilot_only_classic_confirmed"),
    "MAX_NEW_ENTRIES_PER_CYCLE": ("min", 1),
    "CONTROLLED_PULLBACK_ALLOC_FACTOR": ("min", 0.15),
    "CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY": ("min", 1),
    "CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER": ("set", True),
    "CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY": ("set", True),
    "ROTATION_MIN_HOLD_SECONDS": ("max", 7200),
    "ROTATION_MIN_SCORE_EDGE": ("max", 0.012),
    "ROTATION_SCORE_MULTIPLIER": ("max", 2.00),
    "MIN_ENTRY_SCORE_RISK_ON": ("max", 0.022),
    "MIN_ENTRY_SCORE_CONSTRUCTIVE": ("max", 0.022),
    "MIN_ENTRY_SCORE_NEUTRAL": ("max", 0.024),
    "ENTRY_SCORE_LOSS_STEP": ("max", 0.008),
    "POST_STOP_SCORE_BUMP": ("max", 0.012),
    "POST_STOP_EXCEPTIONAL_SCORE": ("max", 0.048),
    "POST_STOP_REQUIRE_SECTOR_LEADER": ("set", True),
}

# Starter/pilot allocation only. EOD/classic-confirmed baskets can still carry
# tech-heavy exposure through the core position/risk engine.
PILOT_BUCKET_ALLOC_FACTORS = {
    "small_cap_momentum": 0.08,
    "bitcoin_ai_compute": 0.10,
    "semi_leaders": 0.14,
    "data_center_infra": 0.14,
    "cloud_cyber_software": 0.14,
    "mega_cap_ai": 0.22,
    "precious_metals": 0.18,
    "energy_leaders": 0.18,
    "benchmark_etf": 0.28,
    "dividend_defensive": 0.28,
    "defense_industrial": 0.22,
}

_REGISTERED_APP_IDS: set[int] = set()
_APPLIED_OVERRIDES: Dict[str, Any] = {}
_PROFILE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_LATEST_DECISIONS: List[Dict[str, Any]] = []
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


def _pct_change(series: Any, bars: int) -> float | None:
    try:
        if series is None or len(series) <= bars:
            return None
        start = _float(series.iloc[-bars - 1], 0.0)
        end = _float(series.iloc[-1], 0.0)
        if not start:
            return None
        return end / start - 1.0
    except Exception:
        return None


def _max_drawdown(series: Any, bars: int) -> float | None:
    try:
        if series is None or len(series) < 5:
            return None
        window = series.tail(min(bars, len(series)))
        peak = None
        max_dd = 0.0
        for value in window:
            v = _float(value, 0.0)
            if not v:
                continue
            peak = v if peak is None else max(peak, v)
            if peak:
                max_dd = min(max_dd, v / peak - 1.0)
        return abs(max_dd)
    except Exception:
        return None


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
        return {"is_open": True, "minutes_to_close": None, "reason": "clock_unavailable"}


def in_eod_window(module: Any) -> bool:
    clock = _market_clock(module)
    mtc = clock.get("minutes_to_close")
    return bool(clock.get("is_open") and mtc is not None and _float(mtc, 9999.0) <= EOD_WINDOW_MINUTES)


def _append_decision(decision: Dict[str, Any]) -> None:
    row = dict(decision)
    row.setdefault("generated_local", _now_text())
    _LATEST_DECISIONS.append(row)
    del _LATEST_DECISIONS[:-100]


def _extract_symbol_side_score(args: tuple, kwargs: dict) -> Tuple[str | None, str, float | None]:
    symbol = kwargs.get("symbol") or kwargs.get("ticker")
    side = kwargs.get("side", "long")
    score = kwargs.get("score")
    for arg in args:
        if symbol is None and isinstance(arg, str) and 1 <= len(arg) <= 8:
            symbol = arg
        elif isinstance(arg, str) and arg.lower() in ("long", "short"):
            side = arg.lower()
        elif score is None and isinstance(arg, (int, float)):
            score = arg
    return (str(symbol).upper() if symbol else None, str(side).lower(), _float(score, None) if score is not None else None)


def _position_guard(module: Any, symbol: str) -> Dict[str, Any]:
    try:
        state = module.load_state() if hasattr(module, "load_state") else {}
        positions = state.get("positions", {}) if isinstance(state, dict) else {}
        pos = positions.get(symbol) if isinstance(positions, dict) else None
        if not isinstance(pos, dict):
            return {"blocked": False, "reason": "no_existing_position"}
        pnl_pct = _float(pos.get("pnl_pct"), None)
        if pnl_pct is None:
            entry = _float(pos.get("entry") or pos.get("entry_price"), 0.0)
            last_price = _float(pos.get("last_price") or pos.get("price"), 0.0)
            pnl_pct = (last_price / entry - 1.0) if entry and last_price else 0.0
        entry_time = _float(pos.get("entry_time"), 0.0)
        held_seconds = time.time() - entry_time if entry_time else None
        early = held_seconds is not None and held_seconds <= EARLY_LOSS_WINDOW_SECONDS
        if early and pnl_pct <= EARLY_LOSS_BLOCK_PCT:
            return {
                "blocked": True,
                "reason": "existing_position_early_loss_no_adds",
                "pnl_pct": round(pnl_pct * 100, 3),
                "held_seconds": round(held_seconds, 1),
            }
        return {"blocked": False, "reason": "existing_position_ok", "pnl_pct": round(pnl_pct * 100, 3), "held_seconds": round(held_seconds, 1) if held_seconds is not None else None}
    except Exception as exc:
        return {"blocked": False, "reason": "position_guard_error_allowed", "error": str(exc)}


def classic_profile(module: Any, symbol: str) -> Dict[str, Any]:
    symbol = str(symbol).upper()
    cache_key = f"{symbol}:{int(time.time() // CACHE_TTL_SECONDS)}"
    cached = _PROFILE_CACHE.get(cache_key)
    if cached:
        return dict(cached[1])

    df = _download(module, symbol, "6mo", "1d")
    close = _col(df, "Close")
    price = _last(close)
    ma20 = _sma(close, 20)
    ma50 = _sma(close, 50)
    ma100 = _sma(close, 100)
    ret5 = _pct_change(close, 5)
    ret20 = _pct_change(close, 20)
    ret60 = _pct_change(close, 60)
    dd60 = _max_drawdown(close, 60)

    data_ok = bool(price and ma20 and ma50)
    trend_ok = bool(data_ok and price >= ma20 and ma20 >= ma50)
    longer_trend_ok = bool((not ma100) or price >= ma100)
    momentum_ok = bool(ret20 is None or ret20 >= MIN_RET_20D)
    medium_ok = bool(ret60 is None or ret60 >= MIN_RET_60D)
    not_chasing = bool(ret5 is None or ret5 <= MAX_RET_5D_CHASE)
    drawdown_ok = bool(dd60 is None or dd60 <= MAX_DRAWDOWN_60D)

    reasons: List[str] = []
    if not data_ok:
        reasons.append("classic_data_unavailable")
    if data_ok and not trend_ok:
        reasons.append("daily_trend_not_confirmed")
    if data_ok and not longer_trend_ok:
        reasons.append("below_longer_trend")
    if not momentum_ok:
        reasons.append("20d_momentum_negative")
    if not medium_ok:
        reasons.append("60d_momentum_weak")
    if not not_chasing:
        reasons.append("5d_move_too_extended")
    if not drawdown_ok:
        reasons.append("60d_drawdown_too_high")

    allowed = bool(data_ok and trend_ok and longer_trend_ok and momentum_ok and medium_ok and not_chasing and drawdown_ok)
    profile = {
        "symbol": symbol,
        "allowed": allowed,
        "classic_confirmed": allowed,
        "reasons": reasons or ["classic_daily_trend_confirmed"],
        "price": round(price, 4) if price else None,
        "ma20": round(ma20, 4) if ma20 else None,
        "ma50": round(ma50, 4) if ma50 else None,
        "ma100": round(ma100, 4) if ma100 else None,
        "ret5_pct": round(ret5 * 100, 2) if ret5 is not None else None,
        "ret20_pct": round(ret20 * 100, 2) if ret20 is not None else None,
        "ret60_pct": round(ret60 * 100, 2) if ret60 is not None else None,
        "drawdown60_pct": round(dd60 * 100, 2) if dd60 is not None else None,
        "rule": "classic_hard_gate_daily_trend_not_chase",
    }
    _PROFILE_CACHE[cache_key] = (time.time(), profile)
    return dict(profile)


def classic_decision(module: Any, symbol: str, side: str = "long", score: float | None = None) -> Dict[str, Any]:
    symbol = str(symbol).upper()
    side = (side or "long").lower()
    if side != "long":
        return {"allowed": True, "symbol": symbol, "side": side, "reason": "shorts_not_classic_blocked"}
    if in_eod_window(module):
        return {"allowed": True, "symbol": symbol, "side": side, "reason": "eod_allocator_window_allows_full_decision"}

    profile = classic_profile(module, symbol)
    reasons = list(profile.get("reasons", []))
    allowed = bool(profile.get("allowed"))

    position_guard = _position_guard(module, symbol)
    if position_guard.get("blocked"):
        allowed = False
        reasons.append(str(position_guard.get("reason")))

    high_beta = symbol in HIGH_BETA_SYMBOLS
    score_value = score if score is not None else 0.0
    if high_beta and score_value < HIGH_BETA_MIN_SCORE:
        allowed = False
        reasons.append("high_beta_requires_exceptional_score")

    # Exceptional score can only help if the underlying daily trend is already
    # confirmed. It cannot bypass a failed trend, drawdown, or chase block.
    exceptional_score = score is not None and score >= MIN_SCORE_TO_OVERRIDE
    exceptional_confirmed = bool(exceptional_score and profile.get("classic_confirmed") and not position_guard.get("blocked"))
    if exceptional_confirmed and not high_beta:
        allowed = True
    elif exceptional_confirmed and high_beta:
        allowed = True

    decision = dict(profile)
    decision["allowed"] = allowed
    decision["side"] = side
    decision["score"] = score
    decision["hard_gate_enabled"] = True
    decision["high_beta_symbol"] = high_beta
    decision["high_beta_min_score"] = HIGH_BETA_MIN_SCORE
    decision["exceptional_score_override"] = bool(exceptional_confirmed)
    decision["position_guard"] = position_guard
    decision["reason"] = "classic_hard_gate_confirmed" if allowed else ",".join(dict.fromkeys(reasons or ["classic_hard_gate_blocked"]))
    return decision


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

    try:
        bucket_config = getattr(module, "BUCKET_CONFIG", {})
        if isinstance(bucket_config, dict):
            for bucket, target in PILOT_BUCKET_ALLOC_FACTORS.items():
                cfg = bucket_config.get(bucket)
                if isinstance(cfg, dict):
                    old = cfg.get("alloc_factor")
                    cfg["alloc_factor"] = min(float(old if old is not None else 1.0), target)
                    applied[f"BUCKET_CONFIG.{bucket}.alloc_factor"] = {"old": old, "new": cfg["alloc_factor"], "mode": "min", "applied": True}
    except Exception as exc:
        applied["BUCKET_CONFIG"] = {"applied": False, "error": str(exc)}

    _APPLIED_OVERRIDES.clear()
    _APPLIED_OVERRIDES.update(applied)
    return applied


def _wrap_entry_points(module: Any) -> None:
    global _WRAPPED
    if _WRAPPED:
        return

    for fn_name in ("entry_quality_check", "controlled_pullback_entry_check"):
        fn = getattr(module, fn_name, None)
        if callable(fn) and not getattr(fn, "_classic_signal_wrapped", False):
            def make_wrapper(__fn, __name):
                def wrapper(*args, **kwargs):
                    result = __fn(*args, **kwargs)
                    try:
                        if not _result_allows(result):
                            return result
                        symbol, side, score = _extract_symbol_side_score(args, kwargs)
                        if not symbol:
                            return result
                        decision = classic_decision(module, symbol, side, score)
                        decision["hook"] = __name
                        _append_decision(decision)
                        if not decision.get("allowed", True):
                            return _block_like(result, "classic_hard_gate:" + str(decision.get("reason", "blocked")))
                    except Exception as exc:
                        _append_decision({"hook": __name, "allowed": True, "error": str(exc), "reason": "classic_hard_gate_error_allowed"})
                    return result
                wrapper._classic_signal_wrapped = True
                return wrapper
            setattr(module, fn_name, make_wrapper(fn, fn_name))

    fn = getattr(module, "enter_position", None)
    if callable(fn) and not getattr(fn, "_classic_signal_wrapped", False):
        def enter_wrapper(*args, **kwargs):
            try:
                symbol, side, score = _extract_symbol_side_score(args, kwargs)
                if symbol:
                    decision = classic_decision(module, symbol, side, score)
                    decision["hook"] = "enter_position"
                    _append_decision(decision)
                    if not decision.get("allowed", True):
                        return None
            except Exception as exc:
                _append_decision({"hook": "enter_position", "allowed": True, "error": str(exc), "reason": "classic_hard_gate_error_allowed"})
            return fn(*args, **kwargs)
        enter_wrapper._classic_signal_wrapped = True
        setattr(module, "enter_position", enter_wrapper)

    _WRAPPED = True


def apply(module: Any) -> Dict[str, Any]:
    applied = apply_runtime_overrides(module)
    _wrap_entry_points(module)
    try:
        setattr(module, "CLASSIC_SIGNAL_MODE_VERSION", VERSION)
    except Exception:
        pass
    return {
        "status": "ok",
        "type": "classic_signal_apply",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "hard_gate_enabled": True,
        "high_beta_min_score": HIGH_BETA_MIN_SCORE,
        "applied_runtime_overrides": applied,
        "strategy": "classic higher-timeframe signal is the hard entry gate; intraday scanner pilot only; tech-heavy allowed when trend confirms",
    }


def status_payload(module: Any | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "ok",
        "type": "classic_signal_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "mode": "classic_signal_plus_eod_hard_gate",
        "intraday_role": "pilot_only_classic_confirmed",
        "hard_gate_enabled": True,
        "tech_heavy_allowed": True,
        "applied_runtime_overrides": _APPLIED_OVERRIDES,
        "settings": {
            "min_ret_20d_pct": MIN_RET_20D * 100,
            "min_ret_60d_pct": MIN_RET_60D * 100,
            "max_ret_5d_chase_pct": MAX_RET_5D_CHASE * 100,
            "max_drawdown_60d_pct": MAX_DRAWDOWN_60D * 100,
            "exceptional_score_override": MIN_SCORE_TO_OVERRIDE,
            "high_beta_min_score": HIGH_BETA_MIN_SCORE,
            "early_loss_block_pct": EARLY_LOSS_BLOCK_PCT * 100,
            "early_loss_window_seconds": EARLY_LOSS_WINDOW_SECONDS,
            "eod_window_minutes": EOD_WINDOW_MINUTES,
        },
        "latest_decisions": _LATEST_DECISIONS[-20:],
        "blocked_decisions_recent": [d for d in _LATEST_DECISIONS[-50:] if not d.get("allowed", True)][-10:],
        "normal_test_link": "https://trading-bot-clean.up.railway.app/paper/self-check",
        "note": "Use /paper/self-check for routine testing. Classic mode should appear there as pass.",
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
    if "/paper/classic-signal-status" not in existing:
        flask_app.add_url_rule("/paper/classic-signal-status", "classic_signal_status", lambda: jsonify(status_payload(module)))
    _REGISTERED_APP_IDS.add(id(flask_app))
