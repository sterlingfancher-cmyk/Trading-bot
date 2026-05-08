"""Direct risk-control bootstrap routes for the trading bot.

This module is designed to be loaded by usercustomize.py during Python startup.
It avoids importing app.py directly, so it works with the current Railway Procfile
that executes app.py as __main__.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, List

try:
    import pytz
except Exception:
    pytz = None

try:
    import yfinance as yf
except Exception:
    yf = None

VERSION = "risk-bootstrap-2026-05-08"
REGISTERED_APP_IDS: set[int] = set()
APPLIED: Dict[str, Dict[str, Any]] = {}

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
    _save_state(state)
    return {"status": "ok", "version": VERSION, "overrides": APPLIED}


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
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(max(0.0, var))


def _volatility_stop_plan() -> Dict[str, Any]:
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
        "execution_note": "Advisory stop-sizing plan. Full adaptive exit replacement requires a later core app.py execution update.",
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
            "wins_today": int(_f(realized.get("wins_today", perf.get("wins_today", 0)))) ,
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
            "Review stopped-out symbols after the close; if they recover repeatedly, switch to wider stops plus smaller size.",
            "Keep ML in Phase 1 shadow logging until 100+ scanner rows and 2-4 weeks of paper data are collected.",
        ],
    }


def register_routes(flask_app: Any) -> None:
    if id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/risk-improvement-status" not in existing:
        flask_app.add_url_rule("/paper/risk-improvement-status", "risk_improvement_status_bootstrap", lambda: jsonify({
            "status": "ok",
            "version": VERSION,
            "generated_local": _now_text(),
            "state_file": STATE_FILE,
            "market_clock": _market_clock(),
            "applied_runtime_overrides": APPLIED,
            "mode": "intraday_churn_reduction_plus_eod_confirmation_bias",
            "live_ml_decider": False,
        }))
    if "/paper/next-session-risk-plan" not in existing:
        flask_app.add_url_rule("/paper/next-session-risk-plan", "next_session_risk_plan_bootstrap", lambda: jsonify(_next_session_risk_plan()))
    if "/paper/volatility-stop-plan" not in existing:
        flask_app.add_url_rule("/paper/volatility-stop-plan", "volatility_stop_plan_bootstrap", lambda: jsonify(_volatility_stop_plan()))
    if "/paper/follow-through-review" not in existing:
        flask_app.add_url_rule("/paper/follow-through-review", "follow_through_review_bootstrap", lambda: jsonify(_follow_through_review()))

    REGISTERED_APP_IDS.add(id(flask_app))
