"""Final ownership guard for staged paper-risk controlled restart.

The core entry pipeline is a deliberate non-wrapper replacement. Because it can be
installed after performance_risk_calibration, this module continuously verifies
that the calibrated feedback and entry wrappers remain outermost.

Paper-only. It does not place orders directly and does not grant live or ML authority.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict, List

import performance_risk_calibration as calibration

VERSION = "performance-risk-activation-guard-2026-07-29-v2"
_WATCHDOG_STARTED: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LOCK = threading.RLock()
_LAST_INSTALL: Dict[str, Any] = {}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any) -> Dict[str, Any]:
    return _dict(getattr(core, "portfolio", {}))


def _clock(core: Any) -> Dict[str, Any]:
    try:
        return _dict(core.market_clock())
    except Exception:
        return {}


def _market(core: Any, supplied: Any = None) -> Dict[str, Any]:
    if isinstance(supplied, dict):
        return supplied
    return _dict(_state(core).get("last_market"))


def _risk(core: Any, supplied: Any = None) -> Dict[str, Any]:
    if isinstance(supplied, dict):
        return supplied
    return _dict(_state(core).get("risk_controls"))


def _feedback_args(core: Any, args: tuple[Any, ...], kwargs: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], bool]:
    market = _market(core, kwargs.get("market") if isinstance(kwargs.get("market"), dict) else (args[0] if args and isinstance(args[0], dict) else None))
    risk = _risk(core, kwargs.get("risk_controls") if isinstance(kwargs.get("risk_controls"), dict) else (args[2] if len(args) >= 3 and isinstance(args[2], dict) else None))
    clock = kwargs.get("clock") if isinstance(kwargs.get("clock"), dict) else (args[3] if len(args) >= 4 and isinstance(args[3], dict) else _clock(core))
    persist = bool(kwargs.get("persist", args[4] if len(args) >= 5 else True))
    return market, risk, _dict(clock), persist


def _live_restart(core: Any, market: Dict[str, Any] | None = None, risk: Dict[str, Any] | None = None, feedback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = _state(core)
    market = _market(core, market)
    risk = _risk(core, risk)
    feedback = _dict(feedback) if isinstance(feedback, dict) else _dict(state.get("feedback_loop"))
    calibration._decorate_risk(core, risk)
    return calibration._restart_payload(core, market, _clock(core), risk, feedback)


def _block_rows(signals: Any, reason: str, restart: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for signal in _list(signals)[:10]:
        if not isinstance(signal, dict):
            continue
        rows.append({
            "symbol": signal.get("symbol"),
            "side": signal.get("side"),
            "score": signal.get("score"),
            "reason": reason,
            "controlled_restart": restart,
        })
    return rows


def install(core: Any) -> Dict[str, Any]:
    global _LAST_INSTALL
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    patched: Dict[str, bool] = {}
    with _LOCK:
        try:
            calibration.install(core)
        except Exception:
            pass

        current_feedback = getattr(core, "feedback_loop_status", None)
        if callable(current_feedback) and not getattr(current_feedback, "_performance_risk_activation_guard", False):
            def guarded_feedback(*args, __prior=current_feedback, **kwargs):
                row = __prior(*args, **kwargs)
                row = row if isinstance(row, dict) else {}
                market, risk, clock, persist = _feedback_args(core, args, kwargs)
                return calibration._rewrite_feedback(core, row, market, clock, risk, persist)

            guarded_feedback._performance_risk_activation_guard = True
            guarded_feedback._performance_risk_activation_version = VERSION
            guarded_feedback._performance_risk_prior = current_feedback
            core.feedback_loop_status = guarded_feedback
            patched["feedback_loop_status"] = True

        current_entries = getattr(core, "try_entries_and_rotations", None)
        if callable(current_entries) and not getattr(current_entries, "_performance_risk_activation_guard", False):
            def guarded_entries(
                long_signals,
                short_signals,
                params,
                market,
                new_entries_allowed=True,
                entry_block_reason=None,
                __prior=current_entries,
            ):
                state = _state(core)
                risk = _risk(core)
                feedback = _dict(state.get("feedback_loop"))
                restart = _live_restart(core, _dict(market), risk, feedback)

                if not restart.get("soft_pause_active"):
                    return __prior(
                        long_signals,
                        short_signals,
                        params,
                        market,
                        new_entries_allowed=new_entries_allowed,
                        entry_block_reason=entry_block_reason,
                    )

                if restart.get("hard_halt_active"):
                    return [], [], _block_rows(
                        list(_list(long_signals)) + list(_list(short_signals)),
                        "performance_risk_hard_halt",
                        restart,
                    )

                if not restart.get("active"):
                    return [], [], _block_rows(
                        list(_list(long_signals)) + list(_list(short_signals)),
                        "controlled_restart_not_eligible",
                        restart,
                    )

                section = calibration._restart_state(core)
                used = int(section.get("controlled_restart_entries_used") or 0)
                if used >= calibration.RESTART_MAX_ENTRIES:
                    return [], [], _block_rows(
                        long_signals,
                        "controlled_restart_daily_allowance_exhausted",
                        restart,
                    )

                required = _f(restart.get("required_long_score"))
                candidates = sorted(
                    [dict(row) for row in _list(long_signals) if isinstance(row, dict)],
                    key=lambda row: _f(row.get("score")),
                    reverse=True,
                )
                qualified = [row for row in candidates if _f(row.get("score")) >= required]
                if not qualified:
                    return [], [], _block_rows(
                        candidates,
                        "controlled_restart_score_floor",
                        restart,
                    )

                positions = _dict(state.get("positions"))
                safe_params = dict(params or {})
                normal_max = int(safe_params.get("max_positions") or 0)
                if normal_max <= len(positions):
                    return [], [], _block_rows(
                        qualified[:1],
                        "controlled_restart_no_rotation",
                        restart,
                    )

                signal = dict(qualified[0])
                signal["alloc_factor"] = min(
                    _f(signal.get("alloc_factor"), 1.0),
                    calibration.RESTART_ALLOC_FACTOR,
                )
                signal["entry_context"] = (
                    f"{str(signal.get('entry_context') or 'scanner')}|controlled_restart"
                )
                signal["controlled_restart"] = True
                safe_params["max_positions"] = min(normal_max, len(positions) + 1)

                section["controlled_restart_attempts"] = int(
                    section.get("controlled_restart_attempts") or 0
                ) + 1
                entries, _rotations, blocked = __prior(
                    [signal],
                    [],
                    safe_params,
                    market,
                    new_entries_allowed=True,
                    entry_block_reason=None,
                )

                if entries:
                    new_used = used + len(entries)
                    section["controlled_restart_entries_used"] = new_used
                    section["last_controlled_restart_entry_local"] = _now(core)
                    restart["entries_used"] = new_used
                    restart["entries_remaining"] = max(
                        0, calibration.RESTART_MAX_ENTRIES - new_used
                    )
                    state.setdefault("feedback_loop", {})["controlled_restart"] = restart
                    for entry in entries:
                        if isinstance(entry, dict):
                            entry["controlled_restart"] = True
                            entry["controlled_restart_alloc_factor"] = (
                                calibration.RESTART_ALLOC_FACTOR
                            )

                section["last_controlled_restart_blocked"] = blocked
                return entries, [], blocked

            guarded_entries._performance_risk_activation_guard = True
            guarded_entries._performance_risk_activation_version = VERSION
            guarded_entries._performance_risk_prior = current_entries
            core.try_entries_and_rotations = guarded_entries
            patched["try_entries_and_rotations"] = True

        try:
            setattr(core, "PERFORMANCE_RISK_ACTIVATION_GUARD_VERSION", VERSION)
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
                getattr(feedback_fn, "_performance_risk_activation_guard", False)
            ),
            "entry_guard_active": bool(
                getattr(entry_fn, "_performance_risk_activation_guard", False)
            ),
            "feedback_callable": getattr(feedback_fn, "__qualname__", None),
            "entry_callable": getattr(entry_fn, "__qualname__", None),
        }
        return dict(_LAST_INSTALL)


def status_payload(core: Any) -> Dict[str, Any]:
    state = _state(core) if core is not None else {}
    risk = _dict(state.get("risk_controls"))
    feedback = _dict(state.get("feedback_loop"))
    market = _dict(state.get("last_market"))
    restart = _live_restart(core, market, risk, feedback) if core is not None else {}
    feedback_fn = getattr(core, "feedback_loop_status", None) if core is not None else None
    entry_fn = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    feedback_active = bool(
        getattr(feedback_fn, "_performance_risk_activation_guard", False)
    )
    entry_active = bool(
        getattr(entry_fn, "_performance_risk_activation_guard", False)
    )
    return {
        "status": "ok" if core is not None and feedback_active and entry_active else "warn",
        "overall": "pass" if core is not None and feedback_active and entry_active else "warn",
        "type": "performance_risk_activation_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "feedback_guard_active": feedback_active,
        "entry_guard_active": entry_active,
        "feedback_callable": getattr(feedback_fn, "__qualname__", None),
        "entry_callable": getattr(entry_fn, "__qualname__", None),
        "controlled_restart_live": restart,
        "stored_controlled_restart": feedback.get("controlled_restart", {}),
        "last_install": dict(_LAST_INSTALL),
        "authority": {
            "paper_only": True,
            "changes_thresholds": True,
            "changes_risk_or_sizing": True,
            "places_orders_directly": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
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
    path = "/paper/performance-risk-activation-status"
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "performance_risk_activation_guard_status",
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

    def watch():
        for iteration in range(1200):
            try:
                install(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics

                    runtime_diagnostics.record_exception(
                        exc,
                        source="performance_risk_activation_guard.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="performance-risk-activation-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
