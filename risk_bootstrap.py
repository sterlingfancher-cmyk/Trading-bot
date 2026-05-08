"""Direct risk-control bootstrap routes for the trading bot.

This module is intentionally self-contained because it is already confirmed to
load on Railway. It applies the conservative risk controls and also exposes the
live-volatility status route directly, so /paper/live-volatility-status no
longer depends on any secondary bootstrap path.
"""
from __future__ import annotations

import datetime as dt
import functools
import inspect
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, List

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

VERSION = "risk-bootstrap-live-vol-2026-05-08"
LIVE_VOL_VERSION = "live-volatility-stops-2026-05-08"
REGISTERED_APP_IDS = set()
APPLIED: Dict[str, Dict[str, Any]] = {}
LIVE_APPLIED: Dict[str, Any] = {}
_PATCHED_FUNCTION_IDS = set()

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
MARKET_TZ_NAME = os.environ.get("MARKET_TZ", "America/Chicago")
REGULAR_OPEN_HOUR = int(os.environ.get("REGULAR_OPEN_HOUR", "8"))
REGULAR_OPEN_MINUTE = int(os.environ.get("REGULAR_OPEN_MINUTE", "30"))
REGULAR_CLOSE_HOUR = int(os.environ.get("REGULAR_CLOSE_HOUR", "15"))
REGULAR_CLOSE_MINUTE = int(os.environ.get("REGULAR_CLOSE_MINUTE", "0"))

HYBRID_MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("HYBRID_MAX_NEW_ENTRIES_PER_CYCLE", "1"))
HYBRID_EXTENSION_MAX_FROM_MA20 = float(os.environ.get("HYBRID_EXTENSION_MAX_FROM_MA20", "0.025"))
HYBRID_PULLBACK_MAX_ABOVE_MA20 = float(os.environ.get("HYBRID_PULLBACK_MAX_ABOVE_MA20", "0.008"))
HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR = float(os.environ.get("HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR", "0.35"))
HYBRID_POST_STOP_SCORE_BUMP = float(os.environ.get("HYBRID_POST_STOP_SCORE_BUMP", "0.006"))
HYBRID_POST_STOP_EXCEPTIONAL_SCORE = float(os.environ.get("HYBRID_POST_STOP_EXCEPTIONAL_SCORE", "0.035"))
HYBRID_EOD_WINDOW_MINUTES = int(os.environ.get("HYBRID_EOD_FULL_ALLOCATION_WINDOW_MINUTES", "45"))
HYBRID_VOL_STOP_MIN_PCT = float(os.environ.get("HYBRID_VOL_STOP_MIN_PCT", "0.012"))
HYBRID_VOL_STOP_MAX_PCT = float(os.environ.get("HYBRID_VOL_STOP_MAX_PCT", "0.028"))
HYBRID_VOL_STOP_MULTIPLIER = float(os.environ.get("HYBRID_VOL_STOP_MULTIPLIER", "1.35"))
HYBRID_HIGH_VOL_ALLOC_REDUCTION = float(os.environ.get("HYBRID_HIGH_VOL_ALLOC_REDUCTION", "0.65"))
HYBRID_LIVE_VOL_STOP_DEFAULT_PCT = float(os.environ.get("HYBRID_LIVE_VOL_STOP_DEFAULT_PCT", str(HYBRID_VOL_STOP_MAX_PCT)))

BUCKET_ALLOC_REDUCTIONS = {
    "small_cap_momentum": float(os.environ.get("HYBRID_SMALL_CAP_LIVE_ALLOC_REDUCTION", str(HYBRID_HIGH_VOL_ALLOC_REDUCTION))),
    "bitcoin_ai_compute": float(os.environ.get("HYBRID_BITCOIN_COMPUTE_LIVE_ALLOC_REDUCTION", str(HYBRID_HIGH_VOL_ALLOC_REDUCTION))),
    "precious_metals": float(os.environ.get("HYBRID_METALS_LIVE_ALLOC_REDUCTION", str(HYBRID_HIGH_VOL_ALLOC_REDUCTION))),
    "semi_leaders": float(os.environ.get("HYBRID_SEMI_LIVE_ALLOC_REDUCTION", "0.75")),
    "cloud_cyber_software": float(os.environ.get("HYBRID_SOFTWARE_LIVE_ALLOC_REDUCTION", "0.75")),
    "data_center_infra": float(os.environ.get("HYBRID_DATA_CENTER_LIVE_ALLOC_REDUCTION", "0.75")),
}


def _now() -> dt.datetime:
    if pytz:
        return dt.datetime.now(pytz.timezone(MARKET_TZ_NAME))
    return dt.datetime.now()


def _now_text() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S %Z")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        folder = os.path.dirname(STATE_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _market_clock() -> Dict[str, Any]:
    now = _now()
    open_dt = now.replace(hour=REGULAR_OPEN_HOUR, minute=REGULAR_OPEN_MINUTE, second=0, microsecond=0)
    close_dt = now.replace(hour=REGULAR_CLOSE_HOUR, minute=REGULAR_CLOSE_MINUTE, second=0, microsecond=0)
    is_weekday = now.weekday() < 5
    is_open = bool(is_weekday and open_dt <= now <= close_dt)
    if not is_weekday:
        reason = "weekend"
    elif now < open_dt:
        reason = "before_regular_session"
    elif now > close_dt:
        reason = "after_regular_session"
    else:
        reason = "regular_session"
    minutes_to_close = max(0.0, (close_dt - now).total_seconds() / 60.0)
    return {
        "is_open": is_open,
        "reason": reason,
        "now_local": _now_text(),
        "minutes_to_close": round(minutes_to_close, 2),
        "in_eod_window": bool(is_open and minutes_to_close <= HYBRID_EOD_WINDOW_MINUTES),
        "eod_window_minutes": HYBRID_EOD_WINDOW_MINUTES,
        "timezone": MARKET_TZ_NAME,
    }


def _patch(module: Any, name: str, value: Any, mode: str) -> None:
    old = getattr(module, name, None)
    new = value
    try:
        if old is not None:
            if mode == "min":
                new = min(old, value)
            elif mode == "max":
                new = max(old, value)
        setattr(module, name, new)
        APPLIED[name] = {"old": old, "new": new, "mode": mode, "applied": True}
    except Exception as exc:
        APPLIED[name] = {"old": old, "new": value, "mode": mode, "applied": False, "error": str(exc)}


def _patch_bucket_allocations(module: Any) -> None:
    cfg = getattr(module, "BUCKET_CONFIG", None)
    if not isinstance(cfg, dict):
        LIVE_APPLIED["bucket_allocation_controls"] = {"applied": False, "reason": "BUCKET_CONFIG not found"}
        return
    changes: Dict[str, Any] = {}
    for bucket, reduction in BUCKET_ALLOC_REDUCTIONS.items():
        row = cfg.get(bucket)
        if not isinstance(row, dict):
            continue
        old = _f(row.get("alloc_factor"), 1.0)
        new = max(0.20, round(old * reduction, 4))
        row["alloc_factor"] = new
        changes[bucket] = {"old_alloc_factor": old, "new_alloc_factor": new, "reduction": reduction}
    LIVE_APPLIED["bucket_allocation_controls"] = {"applied": bool(changes), "bucket_changes": changes}


def _stop_pct() -> float:
    return max(HYBRID_VOL_STOP_MIN_PCT, min(HYBRID_VOL_STOP_MAX_PCT, HYBRID_LIVE_VOL_STOP_DEFAULT_PCT))


def _patch_global_stop_names(module: Any) -> None:
    stop = _stop_pct()
    live_changes: Dict[str, Any] = {}
    for name, value in {
        "STOP_LOSS": -stop,
        "STOP_LOSS_PCT": -stop,
        "LONG_STOP_LOSS": -stop,
        "LONG_STOP_LOSS_PCT": -stop,
        "DEFAULT_STOP_LOSS": -stop,
        "DEFAULT_STOP_LOSS_PCT": -stop,
        "TRAIL_LONG": 1.0 - stop,
        "LONG_TRAIL": 1.0 - stop,
        "TRAIL_LONG_PCT": 1.0 - stop,
        "TRAIL_SHORT": 1.0 + stop,
        "SHORT_TRAIL": 1.0 + stop,
        "TRAIL_SHORT_PCT": 1.0 + stop,
        "HYBRID_LIVE_VOLATILITY_STOP_PCT": stop,
        "HYBRID_LIVE_HIGH_VOL_ALLOC_REDUCTION": HYBRID_HIGH_VOL_ALLOC_REDUCTION,
    }.items():
        old = getattr(module, name, None)
        try:
            setattr(module, name, value)
            live_changes[name] = {"old": old, "new": value, "applied": True}
        except Exception as exc:
            live_changes[name] = {"old": old, "new": value, "applied": False, "error": str(exc)}
    try:
        setattr(module, "HYBRID_LIVE_VOLATILITY_VERSION", LIVE_VOL_VERSION)
    except Exception:
        pass
    LIVE_APPLIED["global_stop_values"] = live_changes


def _transform_risk_dict(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_transform_risk_dict(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {k: _transform_risk_dict(v) for k, v in obj.items()}
    stop = _stop_pct()
    if "stop_loss" in out:
        old = _f(out.get("stop_loss"), 0.0)
        out["stop_loss"] = -max(abs(old), stop) if old <= 0 else max(old, stop)
        out["volatility_stop_applied"] = True
        out["volatility_stop_pct"] = round(stop, 6)
    if "trail_long" in out:
        out["trail_long"] = min(_f(out.get("trail_long"), 1.0), 1.0 - stop)
    if "trail_short" in out:
        out["trail_short"] = max(_f(out.get("trail_short"), 1.0), 1.0 + stop)
    if "risk_parameters" in out and isinstance(out["risk_parameters"], dict):
        out["risk_parameters"].setdefault("live_volatility_controls", {})
        out["risk_parameters"]["live_volatility_controls"].update({
            "enabled": True,
            "version": LIVE_VOL_VERSION,
            "default_stop_pct": round(stop * 100, 2),
            "high_vol_alloc_reduction": HYBRID_HIGH_VOL_ALLOC_REDUCTION,
        })
    return out


def _function_mentions_risk(fn: Any) -> bool:
    try:
        consts = " ".join(str(c) for c in getattr(fn, "__code__", None).co_consts)
    except Exception:
        consts = ""
    name = getattr(fn, "__name__", "").lower()
    haystack = f"{name} {consts}".lower()
    return any(x in haystack for x in ["stop_loss", "trail_long", "trail_short", "risk_parameters"])


def _patch_risk_functions(module: Any) -> None:
    wrapped: List[str] = []
    for name, fn in list(getattr(module, "__dict__", {}).items()):
        if not inspect.isfunction(fn) or getattr(fn, "_live_vol_wrapped", False) or id(fn) in _PATCHED_FUNCTION_IDS:
            continue
        if not _function_mentions_risk(fn):
            continue
        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, **kwargs):
            result = __fn(*args, **kwargs)
            return _transform_risk_dict(result)
        wrapper._live_vol_wrapped = True  # type: ignore[attr-defined]
        try:
            setattr(module, name, wrapper)
            _PATCHED_FUNCTION_IDS.add(id(fn))
            wrapped.append(name)
        except Exception:
            pass
    LIVE_APPLIED["risk_function_wrappers"] = {"wrapped_count": len(wrapped), "wrapped_functions": wrapped[:40]}


def apply_runtime_overrides(module: Any | None = None) -> Dict[str, Any]:
    if module is None:
        for mod in list(sys.modules.values()):
            if getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
                module = mod
                break
    if module is None:
        return {"status": "not_applied", "reason": "trading module not found", "version": VERSION}

    _patch(module, "MAX_NEW_ENTRIES_PER_CYCLE", HYBRID_MAX_NEW_ENTRIES_PER_CYCLE, "min")
    _patch(module, "EXTENSION_MAX_FROM_MA20", HYBRID_EXTENSION_MAX_FROM_MA20, "min")
    _patch(module, "PULLBACK_MAX_ABOVE_MA20", HYBRID_PULLBACK_MAX_ABOVE_MA20, "min")
    _patch(module, "CONTROLLED_PULLBACK_ALLOC_FACTOR", HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR, "min")
    _patch(module, "POST_STOP_SCORE_BUMP", HYBRID_POST_STOP_SCORE_BUMP, "max")
    _patch(module, "POST_STOP_EXCEPTIONAL_SCORE", HYBRID_POST_STOP_EXCEPTIONAL_SCORE, "max")
    _patch(module, "POST_STOP_REQUIRE_SECTOR_LEADER", True, "set")
    _patch(module, "CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER", True, "set")
    _patch(module, "CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY", True, "set")
    try:
        setattr(module, "HYBRID_RISK_LAYER_VERSION", VERSION)
    except Exception:
        pass

    _patch_bucket_allocations(module)
    _patch_global_stop_names(module)
    _patch_risk_functions(module)

    state = _load_state()
    state.setdefault("hybrid_risk_layer", {})
    state["hybrid_risk_layer"].update({
        "version": VERSION,
        "enabled": True,
        "updated_local": _now_text(),
        "overrides": APPLIED,
        "mode": "intraday_churn_reduction_plus_eod_confirmation_bias",
        "ml_phase": "phase_1_shadow_logging",
    })
    state.setdefault("live_volatility_controls", {})
    state["live_volatility_controls"].update({
        "version": LIVE_VOL_VERSION,
        "enabled": True,
        "updated_local": _now_text(),
        "applied_controls": LIVE_APPLIED,
        "default_stop_pct": round(_stop_pct() * 100, 2),
        "high_vol_alloc_reduction": HYBRID_HIGH_VOL_ALLOC_REDUCTION,
    })
    _save_state(state)
    return {"status": "ok", "version": VERSION, "overrides": APPLIED, "live_volatility_controls": LIVE_APPLIED}


def _symbols_from_state(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    positions = state.get("positions", {})
    if isinstance(positions, dict):
        out += list(positions.keys())
    scanner = state.get("scanner_audit", {})
    if isinstance(scanner, dict):
        for key in ["accepted_entries", "blocked_entries", "rejected_signals", "long_signals", "short_signals"]:
            rows = scanner.get(key, [])
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, str):
                        out.append(row)
                    elif isinstance(row, dict) and row.get("symbol"):
                        out.append(str(row.get("symbol")))
    trades = state.get("trades", [])
    if isinstance(trades, list):
        for row in trades[-30:]:
            if isinstance(row, dict) and row.get("symbol"):
                out.append(str(row.get("symbol")))
    return list(dict.fromkeys([s.upper() for s in out if s]))[:40]


def _prices(symbols: Iterable[str]) -> Dict[str, List[float]]:
    if yf is None:
        return {}
    out: Dict[str, List[float]] = {}
    for sym in symbols:
        try:
            h = yf.Ticker(sym).history(period="1mo", interval="1d", auto_adjust=True)
            vals = [float(v) for v in h.get("Close", []).dropna().tolist()]
            if len(vals) >= 3:
                out[sym] = vals
        except Exception:
            pass
    return out


def _vol(vals: List[float]) -> float:
    rets = []
    for i in range(1, len(vals)):
        if vals[i - 1] > 0:
            rets.append(vals[i] / vals[i - 1] - 1.0)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return math.sqrt(max(0.0, var))


def _volatility_rows() -> List[Dict[str, Any]]:
    state = _load_state()
    symbols = _symbols_from_state(state)
    px = _prices(symbols)
    rows = []
    for sym, vals in px.items():
        daily_vol = _vol(vals[-11:])
        stop = max(HYBRID_VOL_STOP_MIN_PCT, min(HYBRID_VOL_STOP_MAX_PCT, daily_vol * HYBRID_VOL_STOP_MULTIPLIER))
        high_vol = stop >= 0.020
        rows.append({
            "symbol": sym,
            "daily_realized_vol_pct": round(daily_vol * 100, 2),
            "recommended_stop_pct": round(stop * 100, 2),
            "recommended_alloc_factor": HYBRID_HIGH_VOL_ALLOC_REDUCTION if high_vol else 1.0,
            "high_volatility": high_vol,
        })
    rows.sort(key=lambda r: r["recommended_stop_pct"], reverse=True)
    return rows


def _volatility_stop_plan() -> Dict[str, Any]:
    rows = _volatility_rows()
    return {
        "status": "ok",
        "type": "volatility_stop_plan",
        "version": VERSION,
        "generated_local": _now_text(),
        "symbols_reviewed": len(rows),
        "stop_model": {
            "min_stop_pct": HYBRID_VOL_STOP_MIN_PCT * 100,
            "max_stop_pct": HYBRID_VOL_STOP_MAX_PCT * 100,
            "vol_multiplier": HYBRID_VOL_STOP_MULTIPLIER,
            "high_vol_alloc_reduction": HYBRID_HIGH_VOL_ALLOC_REDUCTION,
        },
        "positions_and_recent_scanner_symbols": rows,
        "execution_note": "Advisory stop-sizing view. Live runtime controls are exposed at /paper/live-volatility-status.",
    }


def _live_volatility_status() -> Dict[str, Any]:
    rows = _volatility_rows()
    state = _load_state()
    live_state = state.get("live_volatility_controls", {}) if isinstance(state.get("live_volatility_controls"), dict) else {}
    return {
        "status": "ok",
        "type": "live_volatility_status",
        "version": LIVE_VOL_VERSION,
        "generated_local": _now_text(),
        "state_file": STATE_FILE,
        "enabled": {"live_vol_stops": True, "live_vol_alloc": True},
        "runtime_expectation": {
            "default_live_stop_pct": round(_stop_pct() * 100, 2),
            "high_vol_alloc_reduction": HYBRID_HIGH_VOL_ALLOC_REDUCTION,
            "max_new_entries_per_cycle_should_remain": 1,
        },
        "applied_runtime_overrides": APPLIED,
        "applied_live_controls": LIVE_APPLIED or live_state.get("applied_controls", {}),
        "recent_symbol_profiles": rows,
        "note": "This route is registered directly by risk_bootstrap, the same module that already powers /paper/risk-improvement-status.",
    }


def _follow_through_review() -> Dict[str, Any]:
    state = _load_state()
    trades = state.get("trades", [])
    stopped = []
    if isinstance(trades, list):
        for t in trades[-30:]:
            if not isinstance(t, dict):
                continue
            reason = str(t.get("exit_reason", "")).lower()
            action = str(t.get("action", "")).lower()
            if action == "exit" and "stop" in reason:
                stopped.append({
                    "symbol": str(t.get("symbol", "")).upper(),
                    "exit_price": _f(t.get("price")),
                    "pnl_pct": round(_f(t.get("pnl_pct")), 3),
                    "pnl_dollars": round(_f(t.get("pnl_dollars")), 2),
                    "exit_reason": t.get("exit_reason"),
                    "time": t.get("time"),
                })
    return {
        "status": "ok",
        "type": "follow_through_review",
        "version": VERSION,
        "generated_local": _now_text(),
        "reviewed_stop_losses": stopped,
        "summary": {"stop_loss_rows": len(stopped)},
        "recommended_use": "If stopped names repeatedly recover by the close, widen stops but reduce allocation instead of keeping tight flat stops.",
    }


def _next_session_risk_plan() -> Dict[str, Any]:
    state = _load_state()
    realized = state.get("realized_pnl", {}) if isinstance(state.get("realized_pnl"), dict) else {}
    risk = state.get("risk_controls", {}) if isinstance(state.get("risk_controls"), dict) else {}
    perf = state.get("performance", {}) if isinstance(state.get("performance"), dict) else {}
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    losses_today = int(_f(realized.get("losses_today", perf.get("losses_today", 0))))
    self_defense = bool(risk.get("self_defense_active") or losses_today >= 2)
    return {
        "status": "ok",
        "type": "next_session_risk_plan",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_clock": _market_clock(),
        "state_summary": {
            "equity": round(_f(state.get("equity", 0)), 2),
            "cash": round(_f(state.get("cash", 0)), 2),
            "open_positions": list(positions.keys()),
            "realized_pnl_today": round(_f(realized.get("today", perf.get("realized_pnl_today", 0))), 2),
            "wins_today": int(_f(realized.get("wins_today", perf.get("wins_today", 0)))),
            "losses_today": losses_today,
            "intraday_drawdown_pct": round(_f(risk.get("intraday_drawdown_pct", 0)), 3),
            "self_defense_inferred": self_defense,
        },
        "applied_runtime_overrides": APPLIED or state.get("hybrid_risk_layer", {}).get("overrides", {}),
        "recommended_rules_for_next_session": [
            "Start with one new intraday entry per cycle maximum.",
            "Block entries farther than 2.5% above 5-minute MA20 unless full EOD allocation is active.",
            "After one stop-loss, require a stronger score and sector leadership before a new entry.",
            "Use controlled-pullback starters at reduced size only; reserve full-size risk for EOD allocation confirmation.",
            "Use volatility-aware stops with smaller allocation instead of tight flat stops on high-beta symbols.",
            "Keep ML in Phase 1 shadow logging until 100+ scanner rows and 2-4 weeks of paper data are collected.",
        ],
    }


def register_routes(flask_app: Any) -> None:
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    # Do not return early. Route registration is idempotent by URL check, and
    # avoiding early return ensures newly added endpoints appear after deploys.
    if "/paper/risk-improvement-status" not in existing:
        flask_app.add_url_rule("/paper/risk-improvement-status", "risk_improvement_status_bootstrap", lambda: jsonify({
            "status": "ok",
            "version": VERSION,
            "generated_local": _now_text(),
            "state_file": STATE_FILE,
            "market_clock": _market_clock(),
            "applied_runtime_overrides": APPLIED,
            "applied_live_controls": LIVE_APPLIED,
            "mode": "intraday_churn_reduction_plus_eod_confirmation_bias",
            "live_ml_decider": False,
        }))
    if "/paper/live-volatility-status" not in existing:
        flask_app.add_url_rule("/paper/live-volatility-status", "live_volatility_status_bootstrap", lambda: jsonify(_live_volatility_status()))
    if "/paper/next-session-risk-plan" not in existing:
        flask_app.add_url_rule("/paper/next-session-risk-plan", "next_session_risk_plan_bootstrap", lambda: jsonify(_next_session_risk_plan()))
    if "/paper/volatility-stop-plan" not in existing:
        flask_app.add_url_rule("/paper/volatility-stop-plan", "volatility_stop_plan_bootstrap", lambda: jsonify(_volatility_stop_plan()))
    if "/paper/follow-through-review" not in existing:
        flask_app.add_url_rule("/paper/follow-through-review", "follow_through_review_bootstrap", lambda: jsonify(_follow_through_review()))

    REGISTERED_APP_IDS.add(id(flask_app))
