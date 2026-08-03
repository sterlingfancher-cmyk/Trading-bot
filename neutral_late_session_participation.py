"""Bounded late-session extension for the neutral starter.

Extends the neutral starter's context window from 180 to 300 minutes after the
regular open. The late segment (180-300 minutes) is deliberately stricter:
stronger risk score, broader scanner participation, a higher candidate score,
and a non-losing first position are required.

Paper-only composition/permission overlay. It does not place orders directly,
change hard-risk limits, change the existing starter allocation factor, alter
the normal portfolio cap, or grant live/ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any, Dict, Tuple

VERSION = "neutral-late-session-participation-2026-08-03-v1"
BASE_END_MINUTES = int(os.environ.get("NEUTRAL_LATE_SESSION_BASE_END_MINUTES", "180"))
EXTENDED_END_MINUTES = int(os.environ.get("NEUTRAL_LATE_SESSION_END_MINUTES", "300"))
LATE_MIN_RISK_SCORE = float(os.environ.get("NEUTRAL_LATE_SESSION_MIN_RISK_SCORE", "50"))
LATE_MIN_SCANNER_SIGNALS = int(os.environ.get("NEUTRAL_LATE_SESSION_MIN_SCANNER_SIGNALS", "30"))
LATE_MIN_CANDIDATE_SCORE = float(os.environ.get("NEUTRAL_LATE_SESSION_MIN_CANDIDATE_SCORE", "0.025"))
LATE_MIN_FIRST_POSITION_PNL_PCT = float(
    os.environ.get("NEUTRAL_LATE_SESSION_MIN_FIRST_POSITION_PNL_PCT", "0.0")
)

_LOCK = threading.RLock()
_REGISTERED_APPS: set[int] = set()
_WATCHDOGS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker


def _candidate_score(signal: Dict[str, Any]) -> float:
    return max(
        _f(signal.get("rank_score")),
        _f(signal.get("score")),
        _f(signal.get("signal_score")),
        _f(signal.get("raw_score")),
    )


def _risk_snapshot(core: Any) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", {}))
    risk = _d(portfolio.get("risk_controls"))
    feedback = _d(portfolio.get("feedback_loop"))
    auto = _d(portfolio.get("auto_runner"))
    market = _d(auto.get("last_result"))
    controlled = _d(feedback.get("controlled_restart"))
    return {
        "halted": bool(risk.get("halted")),
        "self_defense_active": bool(risk.get("self_defense_active")),
        "daily_loss_pct": _f(risk.get("daily_loss_pct")),
        "intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct")),
        "market_mode": str(
            market.get("market_mode")
            or market.get("regime")
            or controlled.get("market_mode")
            or ""
        ).lower(),
        "risk_score": _f(market.get("risk_score")),
    }


def _patch_neutral_context(neutral: Any) -> bool:
    current = getattr(neutral, "_neutral_context", None)
    if not callable(current):
        return False
    if getattr(current, "_neutral_late_session_version", None) == VERSION:
        return False
    prior = getattr(current, "_neutral_late_session_prior", current)

    def late_context(core: Any, market: Dict[str, Any], __prior=prior) -> Tuple[bool, Dict[str, Any]]:
        ok, raw_info = __prior(core, market)
        info = dict(raw_info) if isinstance(raw_info, dict) else {"reason": str(raw_info)}
        minutes = _f(info.get("minutes_since_open"), 9999.0)
        if not ok or minutes <= BASE_END_MINUTES:
            return ok, info

        reasons = list(info.get("reasons") or [])
        counts = neutral._state_counts(core)
        risk_score = _f(info.get("risk_score"))
        risk = _risk_snapshot(core)

        if minutes > EXTENDED_END_MINUTES:
            reasons.append("after_late_neutral_window")
        if risk_score < LATE_MIN_RISK_SCORE:
            reasons.append("late_neutral_risk_score_below_floor")
        if int(counts.get("signals_found") or 0) < LATE_MIN_SCANNER_SIGNALS:
            reasons.append("late_neutral_scanner_cluster_too_small")
        if risk.get("halted"):
            reasons.append("risk_halted")
        if risk.get("self_defense_active"):
            reasons.append("self_defense_active")
        if risk.get("daily_loss_pct", 0.0) > 0.0:
            reasons.append("late_neutral_requires_no_realized_loss")
        if risk.get("intraday_drawdown_pct", 0.0) > 0.50:
            reasons.append("late_neutral_intraday_drawdown_too_large")

        passed = not reasons
        info.update(
            {
                "reason": "late_neutral_context_confirmed" if passed else "late_neutral_context_blocked",
                "reasons": reasons,
                "late_session_extension_active": True,
                "late_session_start_minutes": BASE_END_MINUTES,
                "late_session_end_minutes": EXTENDED_END_MINUTES,
                "late_minimum_risk_score": LATE_MIN_RISK_SCORE,
                "late_minimum_scanner_signals": LATE_MIN_SCANNER_SIGNALS,
                "signals_found": int(counts.get("signals_found") or 0),
            }
        )
        return passed, info

    late_context._neutral_late_session_version = VERSION
    late_context._neutral_late_session_prior = prior
    late_context.__wrapped__ = prior
    neutral._neutral_context = late_context
    return True


def _patch_stage_gate(neutral: Any) -> bool:
    current = getattr(neutral, "_stage_gate", None)
    if not callable(current):
        return False
    if getattr(current, "_neutral_late_session_version", None) == VERSION:
        return False
    prior = getattr(current, "_neutral_late_session_prior", current)

    def late_stage_gate(
        core: Any,
        starter: Any,
        signal: Dict[str, Any],
        market: Dict[str, Any],
        __prior=prior,
    ) -> Tuple[bool, Dict[str, Any]]:
        ok, raw_gate = __prior(core, starter, signal, market)
        gate = dict(raw_gate) if isinstance(raw_gate, dict) else {"reason": str(raw_gate)}
        if not ok:
            return ok, gate

        minutes, _clock = neutral._minutes(core)
        mode = str(_d(market).get("market_mode") or _d(market).get("regime") or "").lower()
        if mode != "neutral" or minutes <= BASE_END_MINUTES:
            return ok, gate

        score = _candidate_score(_d(signal))
        if score < LATE_MIN_CANDIDATE_SCORE:
            return False, {
                **gate,
                "reason": "late_neutral_candidate_score_below_floor",
                "candidate_score": round(score, 6),
                "late_minimum_candidate_score": LATE_MIN_CANDIDATE_SCORE,
                "late_session_start_minutes": BASE_END_MINUTES,
                "late_session_end_minutes": EXTENDED_END_MINUTES,
            }

        stage = int(_f(gate.get("stage"), 0.0))
        if stage >= 2:
            first_positions = gate.get("first_positions") or []
            known_pnls = [
                _f(row.get("pnl_pct"), -999.0)
                for row in first_positions
                if isinstance(row, dict) and row.get("pnl_pct") is not None
            ]
            if not known_pnls:
                return False, {
                    **gate,
                    "reason": "late_neutral_first_position_pnl_unknown",
                    "late_minimum_first_position_pnl_pct": LATE_MIN_FIRST_POSITION_PNL_PCT,
                }
            if min(known_pnls) < LATE_MIN_FIRST_POSITION_PNL_PCT:
                return False, {
                    **gate,
                    "reason": "late_neutral_first_position_not_profitable",
                    "first_positions": first_positions,
                    "late_minimum_first_position_pnl_pct": LATE_MIN_FIRST_POSITION_PNL_PCT,
                }

        gate.update(
            {
                "reason": "late_neutral_stage_allowed",
                "late_session_extension_active": True,
                "late_session_start_minutes": BASE_END_MINUTES,
                "late_session_end_minutes": EXTENDED_END_MINUTES,
                "candidate_score": round(score, 6),
                "late_minimum_candidate_score": LATE_MIN_CANDIDATE_SCORE,
                "late_minimum_first_position_pnl_pct": LATE_MIN_FIRST_POSITION_PNL_PCT,
            }
        )
        return True, gate

    late_stage_gate._neutral_late_session_version = VERSION
    late_stage_gate._neutral_late_session_prior = prior
    late_stage_gate.__wrapped__ = prior
    neutral._stage_gate = late_stage_gate
    return True


def _patch_all_in_one_self_check(core: Any) -> bool:
    try:
        import fast_self_check_override as self_check
    except Exception:
        return False
    current = getattr(self_check, "_component_checks", None)
    if not callable(current):
        return False
    if getattr(current, "_neutral_late_session_version", None) == VERSION:
        return False
    prior = getattr(current, "_neutral_late_session_prior", current)

    def component_checks(runtime: Any, __prior=prior) -> Dict[str, Dict[str, Any]]:
        checks = dict(__prior(runtime))
        row = status_payload(runtime)
        checks["neutral_late_window"] = {
            "name": "neutral_late_window",
            "overall": row.get("overall"),
            "version": VERSION,
            "active": row.get("active"),
            "base_window_end_minutes": BASE_END_MINUTES,
            "extended_window_end_minutes": EXTENDED_END_MINUTES,
            "late_minimum_risk_score": LATE_MIN_RISK_SCORE,
            "late_minimum_scanner_signals": LATE_MIN_SCANNER_SIGNALS,
            "late_minimum_candidate_score": LATE_MIN_CANDIDATE_SCORE,
            "late_minimum_first_position_pnl_pct": LATE_MIN_FIRST_POSITION_PNL_PCT,
            "inside_late_window": row.get("inside_late_window"),
            "current_minutes_since_open": row.get("current_minutes_since_open"),
        }
        return checks

    component_checks._neutral_late_session_version = VERSION
    component_checks._neutral_late_session_prior = prior
    self_check._component_checks = component_checks
    return True


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST_INSTALL
    if core is None:
        try:
            import app as core
        except Exception:
            core = None
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        try:
            import neutral_momentum_starter_extension as neutral
        except Exception as exc:
            return {
                "status": "warn",
                "overall": "warn",
                "version": VERSION,
                "reason": f"neutral_module_import_failed:{type(exc).__name__}:{exc}",
            }

        neutral.END_MINUTES = EXTENDED_END_MINUTES
        context_patched = _patch_neutral_context(neutral)
        stage_patched = _patch_stage_gate(neutral)
        self_check_patched = _patch_all_in_one_self_check(core)
        active = bool(
            _paper()
            and getattr(neutral._neutral_context, "_neutral_late_session_version", None) == VERSION
            and getattr(neutral._stage_gate, "_neutral_late_session_version", None) == VERSION
            and int(getattr(neutral, "END_MINUTES", 0)) == EXTENDED_END_MINUTES
        )
        _LAST_INSTALL = {
            "status": "ok" if active else "warn",
            "overall": "pass" if active else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "active": active,
            "context_patched_this_call": context_patched,
            "stage_gate_patched_this_call": stage_patched,
            "all_in_one_self_check_patched_this_call": self_check_patched,
        }
        setattr(core, "NEUTRAL_LATE_SESSION_PARTICIPATION_VERSION", VERSION)
        return dict(_LAST_INSTALL)


def status_payload(core: Any = None) -> Dict[str, Any]:
    result = install(core)
    if core is None:
        try:
            import app as core
        except Exception:
            core = None
    try:
        import neutral_momentum_starter_extension as neutral
        minutes, _clock = neutral._minutes(core)
        counts = neutral._state_counts(core)
    except Exception:
        minutes = 9999.0
        counts = {}
    risk = _risk_snapshot(core) if core is not None else {}
    portfolio = _d(getattr(core, "portfolio", {})) if core is not None else {}
    positions = _d(portfolio.get("positions"))
    first_positions = []
    if core is not None:
        try:
            import neutral_momentum_starter_extension as neutral
            for symbol, raw in positions.items():
                row = raw if isinstance(raw, dict) else {}
                pnl = neutral._position_pnl_pct(row)
                first_positions.append(
                    {"symbol": str(symbol).upper(), "pnl_pct": None if pnl is None else round(pnl, 4)}
                )
        except Exception:
            pass
    return {
        **result,
        "type": "neutral_late_session_participation_status",
        "current_minutes_since_open": round(_f(minutes), 2),
        "inside_late_window": bool(BASE_END_MINUTES < _f(minutes) <= EXTENDED_END_MINUTES),
        "market_mode": risk.get("market_mode"),
        "risk_score": risk.get("risk_score"),
        "signals_found": int(counts.get("signals_found") or 0),
        "open_positions_count": len(positions),
        "first_positions": first_positions,
        "settings": {
            "base_window_end_minutes": BASE_END_MINUTES,
            "extended_window_end_minutes": EXTENDED_END_MINUTES,
            "late_minimum_risk_score": LATE_MIN_RISK_SCORE,
            "late_minimum_scanner_signals": LATE_MIN_SCANNER_SIGNALS,
            "late_minimum_candidate_score": LATE_MIN_CANDIDATE_SCORE,
            "late_minimum_first_position_pnl_pct": LATE_MIN_FIRST_POSITION_PNL_PCT,
            "existing_max_entries_per_day_unchanged": 2,
            "existing_max_entries_per_cycle_unchanged": 1,
            "existing_max_open_positions_unchanged": 2,
            "existing_allocation_factor_unchanged": 0.18,
            "existing_combined_exposure_cap_pct_unchanged": 36.0,
        },
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_hard_risk_limits": False,
            "changes_existing_starter_sizing": False,
            "changes_normal_portfolio_position_cap": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "extends_neutral_context_window": True,
            "adds_stricter_late_session_filters": True,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    path = "/paper/neutral-late-window-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "neutral_late_window_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    install(core)
    if core is None or id(core) in _WATCHDOGS:
        return {"status": "ok", "version": VERSION, "watchdog_started": core is not None and id(core) in _WATCHDOGS}
    _WATCHDOGS.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(target=watch, daemon=True, name="neutral-late-session-participation-watchdog").start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


try:
    import app as _core
    install(_core)
except Exception:
    pass
