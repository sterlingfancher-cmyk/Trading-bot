"""Side-aware bear-market short recovery during a paper soft-loss pause.

Purpose:
- preserve the 1.00% soft pause, 2.50% hard halt, and 3.00% absolute ceiling;
- keep longs blocked in confirmed risk-off conditions;
- allow at most one reduced-size, high-quality short through the existing core entry pipeline;
- prevent rotations and avoid granting live or ML authority.

This module is an outer ownership guard. It does not place orders directly.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from typing import Any, Dict, List, Tuple

import performance_risk_calibration as calibration

VERSION = "bear-soft-pause-short-recovery-2026-07-29-v1"
SHORT_ALLOC_FACTOR = float(os.environ.get("BEAR_SOFT_PAUSE_SHORT_ALLOC_FACTOR", "0.50"))
SHORT_SCORE_BUMP = float(os.environ.get("BEAR_SOFT_PAUSE_SHORT_SCORE_BUMP", "0.002"))
MAX_SHORT_ENTRIES_PER_DAY = max(
    1, int(os.environ.get("BEAR_SOFT_PAUSE_MAX_SHORT_ENTRIES_PER_DAY", "1"))
)
ALLOWED_MARKET_MODES = {
    item.strip().lower()
    for item in os.environ.get("BEAR_SOFT_PAUSE_ALLOWED_MARKET_MODES", "risk_off").split(",")
    if item.strip()
}
ALLOWED_TRADE_PERMISSIONS = {
    item.strip().lower()
    for item in os.environ.get("BEAR_SOFT_PAUSE_ALLOWED_TRADE_PERMISSIONS", "short_bias").split(",")
    if item.strip()
}
WATCHDOG_FAST_ITERATIONS = max(
    1, int(os.environ.get("BEAR_SOFT_PAUSE_FAST_WATCHDOG_ITERATIONS", "60"))
)
WATCHDOG_MAX_ITERATIONS = max(
    WATCHDOG_FAST_ITERATIONS,
    int(os.environ.get("BEAR_SOFT_PAUSE_WATCHDOG_ITERATIONS", "1200")),
)

_LOCK = threading.RLock()
_WATCHDOG_STARTED: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_DECISION: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _state(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _paper_context() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _clock(core: Any) -> Dict[str, Any]:
    try:
        return _d(core.market_clock())
    except Exception:
        return {}


def _market(core: Any, supplied: Any = None) -> Dict[str, Any]:
    if isinstance(supplied, dict):
        return supplied
    return _d(_state(core).get("last_market"))


def _risk(core: Any, supplied: Any = None) -> Dict[str, Any]:
    if isinstance(supplied, dict):
        return supplied
    return _d(_state(core).get("risk_controls"))


def _recovery_state(core: Any) -> Dict[str, Any]:
    state = _state(core)
    section = state.setdefault("bear_soft_pause_short_recovery", {})
    today = _today(core)
    if section.get("date") != today:
        section.clear()
        section.update({
            "date": today,
            "short_entries_used": 0,
            "short_attempts": 0,
        })
    section.setdefault("short_entries_used", 0)
    section.setdefault("short_attempts", 0)
    section.setdefault("version", VERSION)
    return section


def _base_short_score(core: Any, market: Dict[str, Any]) -> float:
    try:
        return _f(core.min_entry_score_for_market(market, "short"))
    except Exception:
        return _f(getattr(core, "MIN_SHORT_ENTRY_SCORE", 0.0))


def _unwrap_performance_entry(fn: Any) -> Any:
    """Remove only the older performance-risk wrappers, preserving other pipeline layers."""
    current = fn
    seen: set[int] = set()
    for _ in range(12):
        if not callable(current) or id(current) in seen:
            break
        seen.add(id(current))
        prior = getattr(current, "_performance_risk_prior", None)
        if not callable(prior):
            prior = getattr(current, "_performance_risk_original", None)
        if not callable(prior):
            break
        current = prior
    return current


def _eligibility(
    core: Any,
    market: Dict[str, Any],
    risk: Dict[str, Any],
    feedback: Dict[str, Any],
    clock: Dict[str, Any],
) -> Dict[str, Any]:
    calibration._decorate_risk(core, risk)
    restart = calibration._restart_payload(core, market, clock, risk, feedback)
    recovery = _recovery_state(core)
    used = _i(recovery.get("short_entries_used"))
    mode = str(market.get("market_mode") or "").lower()
    permission = str(market.get("trade_permission") or "").lower()
    bear_confirmed = bool(market.get("bear_confirmed"))
    hard = bool(restart.get("hard_halt_active"))
    late = bool(restart.get("late_day_block"))
    profit = bool(restart.get("profit_guard_block"))
    market_open = bool(restart.get("market_open"))
    soft = bool(restart.get("soft_pause_active"))
    normal_short_floor = _base_short_score(core, market)
    required = normal_short_floor + SHORT_SCORE_BUMP

    reasons: List[str] = []
    if not _paper_context():
        reasons.append("not_paper_context")
    if not soft:
        reasons.append("soft_pause_not_active")
    if hard:
        reasons.append("hard_halt_active")
    if not market_open:
        reasons.append("market_closed")
    if late:
        reasons.append("late_day_block")
    if profit:
        reasons.append("profit_guard_block")
    if mode not in ALLOWED_MARKET_MODES:
        reasons.append("market_mode_not_allowed")
    if permission not in ALLOWED_TRADE_PERMISSIONS:
        reasons.append("trade_permission_not_short_bias")
    if not bear_confirmed:
        reasons.append("bear_not_confirmed")
    if used >= MAX_SHORT_ENTRIES_PER_DAY:
        reasons.append("daily_short_recovery_allowance_exhausted")

    active = not reasons
    return {
        "active": active,
        "soft_pause_active": soft,
        "hard_halt_active": hard,
        "market_open": market_open,
        "late_day_block": late,
        "profit_guard_block": profit,
        "market_mode": mode,
        "trade_permission": permission,
        "bear_confirmed": bear_confirmed,
        "required_short_score": round(required, 6),
        "base_short_score": round(normal_short_floor, 6),
        "score_bump": SHORT_SCORE_BUMP,
        "alloc_factor": SHORT_ALLOC_FACTOR,
        "max_short_entries_per_day": MAX_SHORT_ENTRIES_PER_DAY,
        "short_entries_used": used,
        "short_entries_remaining": max(0, MAX_SHORT_ENTRIES_PER_DAY - used),
        "allow_longs": False,
        "allow_shorts": active,
        "allow_rotations": False,
        "reasons": reasons,
        "risk_metrics": {
            "daily_loss_fraction": risk.get("daily_loss_fraction"),
            "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_fraction": risk.get("intraday_drawdown_fraction"),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
            "realized_loss_fraction": risk.get("realized_loss_fraction"),
            "realized_loss_pct": risk.get("realized_loss_pct"),
        },
        "hard_limits": {
            "realized_loss_fraction": calibration.HARD_REALIZED,
            "intraday_drawdown_fraction": calibration.HARD_INTRADAY,
            "absolute_daily_loss_fraction": calibration.ABSOLUTE_DAILY,
        },
    }


def _feedback_args(
    core: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], bool]:
    market = _market(
        core,
        kwargs.get("market")
        if isinstance(kwargs.get("market"), dict)
        else (args[0] if args and isinstance(args[0], dict) else None),
    )
    risk = _risk(
        core,
        kwargs.get("risk_controls")
        if isinstance(kwargs.get("risk_controls"), dict)
        else (args[2] if len(args) >= 3 and isinstance(args[2], dict) else None),
    )
    clock = (
        kwargs.get("clock")
        if isinstance(kwargs.get("clock"), dict)
        else (args[3] if len(args) >= 4 and isinstance(args[3], dict) else _clock(core))
    )
    persist = bool(kwargs.get("persist", args[4] if len(args) >= 5 else True))
    return market, risk, _d(clock), persist


def _rewrite_feedback(
    core: Any,
    feedback: Dict[str, Any],
    market: Dict[str, Any],
    risk: Dict[str, Any],
    clock: Dict[str, Any],
    persist: bool,
) -> Dict[str, Any]:
    recovery = _eligibility(core, market, risk, feedback, clock)
    feedback["bear_short_recovery"] = recovery
    feedback["entry_permission_by_side"] = {
        "long": False if recovery.get("soft_pause_active") and market.get("market_mode") == "risk_off" else not bool(feedback.get("block_new_entries")),
        "short": bool(recovery.get("active")),
    }

    if recovery.get("active"):
        old_reasons = [
            str(reason)
            for reason in _l(feedback.get("reasons"))
            if "controlled restart is unavailable in risk_off mode" not in str(reason).lower()
        ]
        old_reasons.append(
            f"bear short recovery active: score >= {recovery['required_short_score']:.4f}, "
            f"{recovery['alloc_factor']:.0%} size, one entry, no rotations"
        )
        actions = [str(action) for action in _l(feedback.get("actions"))]
        actions.extend((
            "block_recovery_longs_in_confirmed_bear",
            "allow_one_high_quality_short_candidate",
            "reduce_bear_recovery_short_size",
            "disable_rotations_during_bear_recovery",
        ))
        feedback["block_new_entries"] = False
        feedback["reasons"] = list(dict.fromkeys(old_reasons))
        feedback["actions"] = list(dict.fromkeys(actions))
        feedback["side_aware_soft_pause"] = True
    else:
        feedback["side_aware_soft_pause"] = bool(
            recovery.get("soft_pause_active")
            and recovery.get("market_mode") == "risk_off"
        )

    if persist:
        state = _state(core)
        state["feedback_loop"] = feedback
        section = _recovery_state(core)
        section.update({
            "version": VERSION,
            "updated_local": _now(core),
            "eligibility": recovery,
            "authority": {
                "paper_only": True,
                "places_orders_directly": False,
                "changes_live_authority": False,
                "changes_ml_authority": False,
            },
        })
    return feedback


def _block_rows(signals: Any, reason: str, recovery: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for signal in _l(signals)[:12]:
        if not isinstance(signal, dict):
            continue
        rows.append({
            "symbol": signal.get("symbol"),
            "side": signal.get("side"),
            "score": signal.get("score"),
            "reason": reason,
            "bear_short_recovery": recovery,
        })
    return rows


def install(core: Any) -> Dict[str, Any]:
    global _LAST_INSTALL, _LAST_DECISION
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    patched: Dict[str, bool] = {}
    with _LOCK:
        current_feedback = getattr(core, "feedback_loop_status", None)
        if callable(current_feedback) and not getattr(
            current_feedback, "_bear_soft_pause_short_recovery_guard", False
        ):
            def guarded_feedback(*args, __prior=current_feedback, **kwargs):
                row = __prior(*args, **kwargs)
                row = row if isinstance(row, dict) else {}
                market, risk, clock, persist = _feedback_args(core, args, kwargs)
                return _rewrite_feedback(core, row, market, risk, clock, persist)

            guarded_feedback._bear_soft_pause_short_recovery_guard = True
            guarded_feedback._bear_soft_pause_short_recovery_version = VERSION
            guarded_feedback._bear_soft_pause_short_recovery_prior = current_feedback
            guarded_feedback._performance_risk_activation_guard = True
            guarded_feedback._performance_risk_activation_version = getattr(
                current_feedback, "_performance_risk_activation_version", None
            )
            core.feedback_loop_status = guarded_feedback
            patched["feedback_loop_status"] = True

        current_entries = getattr(core, "try_entries_and_rotations", None)
        if callable(current_entries) and not getattr(
            current_entries, "_bear_soft_pause_short_recovery_guard", False
        ):
            base_entries = _unwrap_performance_entry(current_entries)

            def guarded_entries(
                long_signals,
                short_signals,
                params,
                market,
                new_entries_allowed=True,
                entry_block_reason=None,
                __prior=current_entries,
                __base=base_entries,
            ):
                global _LAST_DECISION
                state = _state(core)
                risk = _risk(core)
                feedback = _d(state.get("feedback_loop"))
                market_dict = _market(core, market)
                recovery = _eligibility(core, market_dict, risk, feedback, _clock(core))

                if not recovery.get("soft_pause_active"):
                    return __prior(
                        long_signals,
                        short_signals,
                        params,
                        market,
                        new_entries_allowed=new_entries_allowed,
                        entry_block_reason=entry_block_reason,
                    )

                if not recovery.get("active"):
                    _LAST_DECISION = {
                        "status": "blocked",
                        "generated_local": _now(core),
                        "reason": "bear_short_recovery_not_eligible",
                        "recovery": recovery,
                    }
                    return [], [], _block_rows(
                        list(_l(long_signals)) + list(_l(short_signals)),
                        "bear_short_recovery_not_eligible",
                        recovery,
                    )

                section = _recovery_state(core)
                used = _i(section.get("short_entries_used"))
                candidates = sorted(
                    [
                        {**dict(row), "side": "short"}
                        for row in _l(short_signals)
                        if isinstance(row, dict)
                    ],
                    key=lambda row: _f(row.get("score")),
                    reverse=True,
                )
                required = _f(recovery.get("required_short_score"))
                qualified = [row for row in candidates if _f(row.get("score")) >= required]

                if not qualified:
                    _LAST_DECISION = {
                        "status": "blocked",
                        "generated_local": _now(core),
                        "reason": "bear_short_recovery_score_floor",
                        "required_short_score": required,
                        "candidate_count": len(candidates),
                        "recovery": recovery,
                    }
                    return [], [], _block_rows(
                        candidates,
                        "bear_short_recovery_score_floor",
                        recovery,
                    )

                positions = _d(state.get("positions"))
                safe_params = dict(params or {})
                normal_max = _i(safe_params.get("max_positions"))
                if normal_max <= len(positions):
                    _LAST_DECISION = {
                        "status": "blocked",
                        "generated_local": _now(core),
                        "reason": "bear_short_recovery_no_rotation",
                        "recovery": recovery,
                    }
                    return [], [], _block_rows(
                        qualified[:1],
                        "bear_short_recovery_no_rotation",
                        recovery,
                    )

                signal = dict(qualified[0])
                signal["side"] = "short"
                signal["alloc_factor"] = min(
                    _f(signal.get("alloc_factor"), 1.0),
                    SHORT_ALLOC_FACTOR,
                )
                signal["entry_context"] = (
                    f"{str(signal.get('entry_context') or 'scanner')}|bear_soft_pause_short_recovery"
                )
                signal["trade_class"] = "bear_soft_pause_short_recovery"
                signal["bear_short_recovery"] = True
                signal["required_short_score"] = required

                safe_params["allow_longs"] = False
                safe_params["allow_shorts"] = True
                safe_params["max_positions"] = min(normal_max, len(positions) + 1)
                section["short_attempts"] = _i(section.get("short_attempts")) + 1
                section["last_attempt_local"] = _now(core)
                section["last_candidate"] = {
                    "symbol": signal.get("symbol"),
                    "score": signal.get("score"),
                    "required_short_score": required,
                }

                if not callable(__base):
                    return [], [], _block_rows(
                        [signal],
                        "bear_short_recovery_base_pipeline_missing",
                        recovery,
                    )

                entries, rotations, blocked = __base(
                    [],
                    [signal],
                    safe_params,
                    market_dict,
                    new_entries_allowed=True,
                    entry_block_reason=None,
                )

                if rotations:
                    blocked = list(_l(blocked)) + [{
                        "symbol": signal.get("symbol"),
                        "side": "short",
                        "reason": "bear_short_recovery_rotation_discarded",
                        "rotation_count": len(_l(rotations)),
                    }]
                    rotations = []

                if entries:
                    new_used = used + len(_l(entries))
                    section["short_entries_used"] = new_used
                    section["last_entry_local"] = _now(core)
                    recovery["short_entries_used"] = new_used
                    recovery["short_entries_remaining"] = max(
                        0, MAX_SHORT_ENTRIES_PER_DAY - new_used
                    )
                    state.setdefault("feedback_loop", {})["bear_short_recovery"] = recovery
                    for entry in _l(entries):
                        if isinstance(entry, dict):
                            entry["bear_short_recovery"] = True
                            entry["bear_short_recovery_alloc_factor"] = SHORT_ALLOC_FACTOR
                            entry["bear_short_recovery_required_score"] = required

                section["last_blocked"] = _l(blocked)
                _LAST_DECISION = {
                    "status": "entry_opened" if entries else "attempted_no_entry",
                    "generated_local": _now(core),
                    "candidate": section.get("last_candidate"),
                    "entries_count": len(_l(entries)),
                    "blocked_count": len(_l(blocked)),
                    "recovery": recovery,
                }
                return _l(entries), [], _l(blocked)

            guarded_entries._bear_soft_pause_short_recovery_guard = True
            guarded_entries._bear_soft_pause_short_recovery_version = VERSION
            guarded_entries._bear_soft_pause_short_recovery_prior = current_entries
            guarded_entries._bear_soft_pause_short_recovery_base = base_entries
            guarded_entries._performance_risk_activation_guard = True
            guarded_entries._performance_risk_activation_version = getattr(
                current_entries, "_performance_risk_activation_version", None
            )
            core.try_entries_and_rotations = guarded_entries
            patched["try_entries_and_rotations"] = True

        try:
            setattr(core, "BEAR_SOFT_PAUSE_SHORT_RECOVERY_VERSION", VERSION)
        except Exception:
            pass

        feedback_fn = getattr(core, "feedback_loop_status", None)
        entry_fn = getattr(core, "try_entries_and_rotations", None)
        _LAST_INSTALL = {
            "status": "ok",
            "version": VERSION,
            "generated_local": _now(core),
            "patched_this_call": patched,
            "feedback_guard_active": bool(
                getattr(feedback_fn, "_bear_soft_pause_short_recovery_guard", False)
            ),
            "entry_guard_active": bool(
                getattr(entry_fn, "_bear_soft_pause_short_recovery_guard", False)
            ),
            "feedback_callable": getattr(feedback_fn, "__qualname__", None),
            "entry_callable": getattr(entry_fn, "__qualname__", None),
            "base_entry_callable": getattr(
                getattr(entry_fn, "_bear_soft_pause_short_recovery_base", None),
                "__qualname__",
                None,
            ),
        }
        return dict(_LAST_INSTALL)


def status_payload(core: Any) -> Dict[str, Any]:
    state = _state(core) if core is not None else {}
    market = _d(state.get("last_market"))
    risk = _d(state.get("risk_controls"))
    feedback = _d(state.get("feedback_loop"))
    recovery = (
        _eligibility(core, market, risk, feedback, _clock(core))
        if core is not None
        else {}
    )
    feedback_fn = getattr(core, "feedback_loop_status", None) if core is not None else None
    entry_fn = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    feedback_active = bool(
        getattr(feedback_fn, "_bear_soft_pause_short_recovery_guard", False)
    )
    entry_active = bool(
        getattr(entry_fn, "_bear_soft_pause_short_recovery_guard", False)
    )
    return {
        "status": "ok" if core is not None and feedback_active and entry_active else "warn",
        "overall": "pass" if core is not None and feedback_active and entry_active else "warn",
        "type": "bear_soft_pause_short_recovery_status",
        "version": VERSION,
        "generated_local": _now(core),
        "feedback_guard_active": feedback_active,
        "entry_guard_active": entry_active,
        "feedback_callable": getattr(feedback_fn, "__qualname__", None),
        "entry_callable": getattr(entry_fn, "__qualname__", None),
        "recovery_live": recovery,
        "stored_recovery": _d(state.get("bear_soft_pause_short_recovery")),
        "last_decision": dict(_LAST_DECISION),
        "last_install": dict(_LAST_INSTALL),
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_risk_or_sizing": True,
            "changes_thresholds": True,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "allows_only_confirmed_bear_shorts_during_soft_pause": True,
            "adds_risk_off_long_exception": False,
        },
    }


def register_routes(flask_app: Any, core: Any) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    path = "/paper/bear-short-recovery-status"
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "bear_soft_pause_short_recovery_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any) -> Dict[str, Any]:
    install(core)
    flask_app = getattr(core, "app", None)
    if flask_app is not None:
        register_routes(flask_app, core)
    if core is None or id(core) in _WATCHDOG_STARTED:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": core is not None and id(core) in _WATCHDOG_STARTED,
        }

    _WATCHDOG_STARTED.add(id(core))

    def watch() -> None:
        for iteration in range(WATCHDOG_MAX_ITERATIONS):
            try:
                install(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics

                    runtime_diagnostics.record_exception(
                        exc,
                        source="bear_soft_pause_short_recovery.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < WATCHDOG_FAST_ITERATIONS else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="bear-soft-pause-short-recovery-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
