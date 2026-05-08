"""Hybrid risk-control improvement layer.

This module is imported from wsgi.py after the main app is loaded. It applies
safe runtime overrides to the existing app.py globals and registers monitoring
endpoints for next-session risk planning.

Why this is a separate module:
- app.py is large and already running successfully.
- These changes reduce intraday churn without rewriting the core engine.
- Full EOD allocator execution integration can happen after we verify behavior.

Applied controls:
1) Smaller intraday entry authority.
2) Tighter extended-from-MA guard before entries.
3) Stronger post-stop recovery requirements.
4) Smaller controlled-pullback starter size.
5) Follow-through / stopped-out-name review endpoints.
6) Volatility-aware stop sizing guidance for next engine integration.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import time
from typing import Any, Dict, Iterable, List, Tuple

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

try:
    from flask import jsonify
except Exception:  # pragma: no cover
    jsonify = None

VERSION = "hybrid-risk-controls-2026-05-08"

# Runtime override defaults. Environment variables still win if Railway is set.
HYBRID_MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("HYBRID_MAX_NEW_ENTRIES_PER_CYCLE", "1"))
HYBRID_EXTENSION_MAX_FROM_MA20 = float(os.environ.get("HYBRID_EXTENSION_MAX_FROM_MA20", "0.025"))
HYBRID_PULLBACK_MAX_ABOVE_MA20 = float(os.environ.get("HYBRID_PULLBACK_MAX_ABOVE_MA20", "0.008"))
HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR = float(os.environ.get("HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR", "0.35"))
HYBRID_POST_STOP_SCORE_BUMP = float(os.environ.get("HYBRID_POST_STOP_SCORE_BUMP", "0.006"))
HYBRID_POST_STOP_EXCEPTIONAL_SCORE = float(os.environ.get("HYBRID_POST_STOP_EXCEPTIONAL_SCORE", "0.035"))
HYBRID_CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES = int(os.environ.get("HYBRID_CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES", "60"))
HYBRID_EOD_FULL_ALLOCATION_WINDOW_MINUTES = int(os.environ.get("HYBRID_EOD_FULL_ALLOCATION_WINDOW_MINUTES", "45"))
HYBRID_FOLLOW_THROUGH_LOOKBACK_TRADES = int(os.environ.get("HYBRID_FOLLOW_THROUGH_LOOKBACK_TRADES", "30"))
HYBRID_VOL_STOP_MIN_PCT = float(os.environ.get("HYBRID_VOL_STOP_MIN_PCT", "0.012"))
HYBRID_VOL_STOP_MAX_PCT = float(os.environ.get("HYBRID_VOL_STOP_MAX_PCT", "0.028"))
HYBRID_VOL_STOP_MULTIPLIER = float(os.environ.get("HYBRID_VOL_STOP_MULTIPLIER", "1.35"))
HYBRID_HIGH_VOL_ALLOC_REDUCTION = float(os.environ.get("HYBRID_HIGH_VOL_ALLOC_REDUCTION", "0.65"))

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
MARKET_TZ_NAME = os.environ.get("MARKET_TZ", "America/Chicago")
REGULAR_OPEN_HOUR = int(os.environ.get("REGULAR_OPEN_HOUR", "8"))
REGULAR_OPEN_MINUTE = int(os.environ.get("REGULAR_OPEN_MINUTE", "30"))
REGULAR_CLOSE_HOUR = int(os.environ.get("REGULAR_CLOSE_HOUR", "15"))
REGULAR_CLOSE_MINUTE = int(os.environ.get("REGULAR_CLOSE_MINUTE", "0"))

_APPLIED_OVERRIDES: Dict[str, Dict[str, Any]] = {}


def _now_local() -> _dt.datetime:
    if pytz:
        return _dt.datetime.now(pytz.timezone(MARKET_TZ_NAME))
    return _dt.datetime.now()


def _now_text() -> str:
    return _now_local().strftime("%Y-%m-%d %H:%M:%S %Z")


def _today_key() -> str:
    return _now_local().strftime("%Y-%m-%d")


def _market_clock() -> Dict[str, Any]:
    now = _now_local()
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
        "in_eod_window": bool(is_open and minutes_to_close <= HYBRID_EOD_FULL_ALLOCATION_WINDOW_MINUTES),
        "eod_window_minutes": HYBRID_EOD_FULL_ALLOCATION_WINDOW_MINUTES,
        "timezone": MARKET_TZ_NAME,
    }


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        d = os.path.dirname(STATE_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _patch_value(core: Any, name: str, new_value: Any, mode: str = "set") -> None:
    """Patch a core app.py global safely and record original/new values."""
    old = getattr(core, name, None)
    chosen = new_value
    try:
        if old is not None:
            if mode == "min":
                chosen = min(old, new_value)
            elif mode == "max":
                chosen = max(old, new_value)
            else:
                chosen = new_value
        setattr(core, name, chosen)
        _APPLIED_OVERRIDES[name] = {"old": old, "new": chosen, "mode": mode, "applied": True}
    except Exception as exc:
        _APPLIED_OVERRIDES[name] = {"old": old, "new": new_value, "mode": mode, "applied": False, "error": str(exc)}


def _apply_core_overrides() -> Dict[str, Any]:
    """Apply runtime controls to app.py globals used by the existing engine."""
    try:
        import app as core  # The main trading engine module.
    except Exception as exc:
        return {"status": "error", "error": f"could not import app module: {exc}", "version": VERSION}

    # Reduce all-day churn. Full-sized decisions should increasingly come from EOD confirmation.
    _patch_value(core, "MAX_NEW_ENTRIES_PER_CYCLE", HYBRID_MAX_NEW_ENTRIES_PER_CYCLE, "min")

    # Earlier extension throttling. This makes the scanner less likely to buy stretched 5-minute moves.
    _patch_value(core, "EXTENSION_MAX_FROM_MA20", HYBRID_EXTENSION_MAX_FROM_MA20, "min")
    _patch_value(core, "PULLBACK_MAX_ABOVE_MA20", HYBRID_PULLBACK_MAX_ABOVE_MA20, "min")

    # Stronger recovery-quality requirements after stop-outs.
    _patch_value(core, "POST_STOP_SCORE_BUMP", HYBRID_POST_STOP_SCORE_BUMP, "max")
    _patch_value(core, "POST_STOP_EXCEPTIONAL_SCORE", HYBRID_POST_STOP_EXCEPTIONAL_SCORE, "max")
    _patch_value(core, "POST_STOP_REQUIRE_SECTOR_LEADER", True, "set")

    # Smaller tactical starters during noisy sessions.
    _patch_value(core, "CONTROLLED_PULLBACK_ALLOC_FACTOR", HYBRID_CONTROLLED_PULLBACK_ALLOC_FACTOR, "min")
    _patch_value(core, "CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER", True, "set")
    _patch_value(core, "CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY", True, "set")
    _patch_value(core, "CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES", HYBRID_CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES, "max")

    # Expose non-invasive constants for the dashboard and next core integration pass.
    setattr(core, "HYBRID_RISK_LAYER_VERSION", VERSION)
    setattr(core, "HYBRID_VOL_STOP_MIN_PCT", HYBRID_VOL_STOP_MIN_PCT)
    setattr(core, "HYBRID_VOL_STOP_MAX_PCT", HYBRID_VOL_STOP_MAX_PCT)
    setattr(core, "HYBRID_VOL_STOP_MULTIPLIER", HYBRID_VOL_STOP_MULTIPLIER)
    setattr(core, "HYBRID_HIGH_VOL_ALLOC_REDUCTION", HYBRID_HIGH_VOL_ALLOC_REDUCTION)

    # Persist a small operational note so checkup/status users can see this layer is active.
    state = _load_state()
    state.setdefault("hybrid_risk_layer", {})
    state["hybrid_risk_layer"].update({
        "version": VERSION,
        "enabled": True,
        "updated_local": _now_text(),
        "overrides": _APPLIED_OVERRIDES,
        "mode": "intraday_churn_reduction_plus_eod_confirmation_bias",
        "ml_phase": "phase_1_shadow_logging",
    })
    _save_state(state)

    return {"status": "ok", "version": VERSION, "overrides": _APPLIED_OVERRIDES}


def _download_prices(symbols: Iterable[str], period: str = "1mo") -> Dict[str, List[float]]:
    if yf is None:
        return {}
    out: Dict[str, List[float]] = {}
    for sym in list(dict.fromkeys([s for s in symbols if s])):
        try:
            hist = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
            vals = [float(v) for v in hist.get("Close", []).dropna().tolist()]
            if len(vals) >= 2:
                out[sym] = vals
        except Exception:
            continue
    return out


def _realized_vol_pct(vals: List[float], lookback: int = 10) -> float:
    if len(vals) < 3:
        return 0.0
    window = vals[-max(3, min(lookback + 1, len(vals))):]
    rets = []
    for i in range(1, len(window)):
        if window[i - 1] > 0:
            rets.append((window[i] / window[i - 1]) - 1.0)
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return math.sqrt(max(0.0, variance))


def _vol_stop_pct(symbol: str, prices: Dict[str, List[float]]) -> Dict[str, Any]:
    vals = prices.get(symbol, [])
    daily_vol = _realized_vol_pct(vals, 10)
    raw_stop = daily_vol * HYBRID_VOL_STOP_MULTIPLIER
    stop = max(HYBRID_VOL_STOP_MIN_PCT, min(HYBRID_VOL_STOP_MAX_PCT, raw_stop))
    high_vol = bool(stop >= 0.020)
    return {
        "symbol": symbol,
        "daily_realized_vol_pct": round(daily_vol * 100, 2),
        "recommended_stop_pct": round(stop * 100, 2),
        "recommended_alloc_factor": HYBRID_HIGH_VOL_ALLOC_REDUCTION if high_vol else 1.0,
        "high_volatility": high_vol,
        "note": "Use wider stop with smaller size for high-volatility names; this is advisory until fully integrated into app.py execution stops.",
    }


def _extract_symbols_from_state(state: Dict[str, Any]) -> List[str]:
    symbols: List[str] = []
    positions = state.get("positions", {})
    if isinstance(positions, dict):
        symbols.extend(list(positions.keys()))
    scanner = state.get("scanner_audit", {})
    if isinstance(scanner, dict):
        for key in ["accepted_entries", "blocked_entries", "rejected_signals", "long_signals", "short_signals"]:
            rows = scanner.get(key, [])
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("symbol"):
                        symbols.append(str(row.get("symbol")))
                    elif isinstance(row, str):
                        symbols.append(row)
    pullbacks = state.get("pullback_watchlist", {})
    if isinstance(pullbacks, dict):
        symbols.extend(list(pullbacks.keys()))
    trades = state.get("trades", state.get("recent_trades", []))
    if isinstance(trades, list):
        for t in trades[-HYBRID_FOLLOW_THROUGH_LOOKBACK_TRADES:]:
            if isinstance(t, dict) and t.get("symbol"):
                symbols.append(str(t.get("symbol")))
    return list(dict.fromkeys([s.upper() for s in symbols if s]))[:40]


def _stopped_symbols(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    trades = state.get("trades", state.get("recent_trades", []))
    rows: List[Dict[str, Any]] = []
    if not isinstance(trades, list):
        return rows
    for t in trades[-HYBRID_FOLLOW_THROUGH_LOOKBACK_TRADES:]:
        if not isinstance(t, dict):
            continue
        reason = str(t.get("exit_reason", "")).lower()
        action = str(t.get("action", "")).lower()
        if action == "exit" and "stop" in reason:
            rows.append({
                "symbol": str(t.get("symbol", "")).upper(),
                "exit_price": _f(t.get("price")),
                "pnl_pct": round(_f(t.get("pnl_pct")), 3),
                "pnl_dollars": round(_f(t.get("pnl_dollars")), 2),
                "exit_reason": t.get("exit_reason"),
                "time": t.get("time"),
            })
    return rows


def _latest_price(symbol: str) -> float:
    if yf is None:
        return 0.0
    try:
        h = yf.Ticker(symbol).history(period="2d", interval="5m", auto_adjust=True)
        vals = h.get("Close", []).dropna().tolist()
        return float(vals[-1]) if vals else 0.0
    except Exception:
        return 0.0


def _follow_through_review() -> Dict[str, Any]:
    state = _load_state()
    stopped = _stopped_symbols(state)
    reviewed: List[Dict[str, Any]] = []
    for row in stopped:
        sym = row.get("symbol")
        last = _latest_price(sym)
        exit_price = _f(row.get("exit_price"))
        follow_through_pct = ((last / exit_price) - 1.0) if last > 0 and exit_price > 0 else 0.0
        verdict = "unknown"
        if follow_through_pct >= 0.012:
            verdict = "likely_too_tight_or_too_early_stop"
        elif follow_through_pct <= -0.006:
            verdict = "stop_probably_helped"
        elif last > 0:
            verdict = "mixed_follow_through"
        reviewed.append({**row, "latest_price": round(last, 4), "post_stop_follow_through_pct": round(follow_through_pct * 100, 2), "verdict": verdict})
    return {
        "status": "ok",
        "type": "follow_through_review",
        "version": VERSION,
        "generated_local": _now_text(),
        "reviewed_stop_losses": reviewed,
        "summary": {
            "stop_loss_rows": len(reviewed),
            "likely_too_tight_count": sum(1 for r in reviewed if r.get("verdict") == "likely_too_tight_or_too_early_stop"),
            "stop_helped_count": sum(1 for r in reviewed if r.get("verdict") == "stop_probably_helped"),
        },
        "recommended_use": "If stopped names repeatedly recover by the close, widen stops but reduce allocation instead of keeping tight flat stops.",
    }


def _volatility_stop_plan() -> Dict[str, Any]:
    state = _load_state()
    symbols = _extract_symbols_from_state(state)
    prices = _download_prices(symbols, period="1mo")
    rows = [_vol_stop_pct(sym, prices) for sym in symbols if sym in prices]
    rows.sort(key=lambda r: (r.get("high_volatility", False), r.get("recommended_stop_pct", 0)), reverse=True)
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
        "execution_note": "This endpoint is the stop-sizing plan for the next app.py core integration. Current runtime patch reduces size/chase risk; full adaptive exit replacement requires editing the core execution branch.",
    }


def _next_session_risk_plan() -> Dict[str, Any]:
    state = _load_state()
    risk_layer = state.get("hybrid_risk_layer", {}) if isinstance(state.get("hybrid_risk_layer"), dict) else {}
    realized = state.get("realized_pnl", {}) if isinstance(state.get("realized_pnl"), dict) else {}
    risk_controls = state.get("risk_controls", {}) if isinstance(state.get("risk_controls"), dict) else {}
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    losses_today = int(_f(realized.get("losses_today", 0)))
    self_defense = bool(risk_controls.get("self_defense_active") or (losses_today >= 2))
    clock = _market_clock()
    plan = {
        "status": "ok",
        "type": "next_session_risk_plan",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_clock": clock,
        "state_summary": {
            "equity": round(_f(state.get("equity", 0)), 2),
            "cash": round(_f(state.get("cash", 0)), 2),
            "open_positions": list(positions.keys()),
            "realized_pnl_today": round(_f(realized.get("today", state.get("performance", {}).get("realized_pnl_today", 0))), 2),
            "wins_today": int(_f(realized.get("wins_today", 0))),
            "losses_today": losses_today,
            "intraday_drawdown_pct": round(_f(risk_controls.get("intraday_drawdown_pct", 0)), 3),
            "self_defense_inferred": self_defense,
        },
        "applied_runtime_overrides": _APPLIED_OVERRIDES or risk_layer.get("overrides", {}),
        "recommended_rules_for_next_session": [
            "Start with one new intraday entry per cycle maximum.",
            "Block entries farther than 2.5% above 5-minute MA20 unless the next full core update explicitly allows EOD basket entries.",
            "After one stop-loss, require a stronger score and sector leadership before a new entry.",
            "Use controlled-pullback starters at reduced size only; reserve full-size risk for EOD allocation confirmation.",
            "Review stopped-out symbols after the close; if they recover repeatedly, switch to wider stops plus smaller size.",
            "Keep ML in Phase 1 shadow logging until 100+ scanner rows and 2-4 weeks of paper data are collected.",
        ],
    }
    return plan


def register_routes(flask_app: Any) -> None:
    if jsonify is None:
        return
    existing = {str(rule) for rule in flask_app.url_map.iter_rules()}

    if "/paper/risk-improvement-status" not in existing:
        @flask_app.route("/paper/risk-improvement-status")
        def paper_risk_improvement_status():  # type: ignore
            return jsonify({
                "status": "ok",
                "version": VERSION,
                "generated_local": _now_text(),
                "state_file": STATE_FILE,
                "market_clock": _market_clock(),
                "applied_runtime_overrides": _APPLIED_OVERRIDES,
                "mode": "intraday_churn_reduction_plus_eod_confirmation_bias",
                "live_ml_decider": False,
            })

    if "/paper/next-session-risk-plan" not in existing:
        @flask_app.route("/paper/next-session-risk-plan")
        def paper_next_session_risk_plan():  # type: ignore
            return jsonify(_next_session_risk_plan())

    if "/paper/volatility-stop-plan" not in existing:
        @flask_app.route("/paper/volatility-stop-plan")
        def paper_volatility_stop_plan():  # type: ignore
            return jsonify(_volatility_stop_plan())

    if "/paper/follow-through-review" not in existing:
        @flask_app.route("/paper/follow-through-review")
        def paper_follow_through_review():  # type: ignore
            return jsonify(_follow_through_review())


def _register_routes(flask_app: Any) -> None:
    _apply_core_overrides()
    register_routes(flask_app)
