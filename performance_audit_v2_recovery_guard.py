"""Persistent recovery watchdog for the resumable performance audit V2 runner.

Railway can restore portfolio state after Gunicorn's post-worker initialization.
A one-shot startup recovery check can therefore run before the persisted queued
request is visible. This guard checks repeatedly and restarts an interrupted
queued/running advisory research request only when no research thread is alive
and the V2 engine lock is clear.

It does not change trading logic, thresholds, sizing, ML authority, or orders.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict

import performance_audit_lab_v2 as lab
import performance_audit_v2_async_route as async_route

VERSION = "performance-audit-v2-recovery-guard-2026-08-03-v1"
WATCHDOG_SECONDS = 10

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED: set[int] = set()
_LAST: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _core() -> Any | None:
    return lab._core()


def _save(core: Any) -> None:
    try:
        lab._save(core)
    except Exception:
        pass


def _section(core: Any) -> Dict[str, Any]:
    return lab._section(core)


def _guard_section(core: Any) -> Dict[str, Any]:
    section = _section(core)
    guard = section.get("recovery_guard")
    if not isinstance(guard, dict):
        guard = {}
        section["recovery_guard"] = guard
    guard["version"] = VERSION
    return guard


def attempt_recovery(core: Any = None, source: str = "watchdog") -> Dict[str, Any]:
    global _LAST
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        section = _section(core)
        request = _d(section.get("queued_request"))
        state = str(section.get("status") or "not_run")
        thread_alive = async_route._thread_alive(core)
        engine_locked = lab._RUN_LOCK.locked()
        guard = _guard_section(core)
        guard.update(
            {
                "checked_local": _now(core),
                "checked_epoch": time.time(),
                "source": source,
                "observed_state": state,
                "queued_request_present": bool(request),
                "thread_alive": thread_alive,
                "engine_locked": engine_locked,
            }
        )

        recoverable = bool(
            state in {"queued", "running"}
            and request
            and not thread_alive
            and not engine_locked
        )
        if not recoverable:
            result = {
                "status": "idle",
                "version": VERSION,
                "generated_local": _now(core),
                "state": state,
                "queued_request_present": bool(request),
                "thread_alive": thread_alive,
                "engine_locked": engine_locked,
                "recovery_started": False,
            }
            guard["last_result"] = dict(result)
            _LAST = result
            _save(core)
            return result

        period = str(request.get("period") or lab.AUTO_PERIOD)
        max_symbols = max(
            20,
            min(75, int(_f(request.get("max_symbols"), lab.AUTO_MAX_SYMBOLS))),
        )
        include_ablation = bool(request.get("include_ablation", True))
        force = bool(request.get("force", True))
        guard["recovery_attempt_local"] = _now(core)
        guard["recovery_attempt_count"] = int(guard.get("recovery_attempt_count", 0) or 0) + 1
        _save(core)

        launched = async_route.start(
            core,
            period=period,
            max_symbols=max_symbols,
            force=force,
            include_ablation=include_ablation,
            resume=True,
        )
        result = {
            "status": "recovery_started" if launched.get("status") in {"started", "running"} else launched.get("status", "unknown"),
            "version": VERSION,
            "generated_local": _now(core),
            "state_before": state,
            "period": period,
            "symbols": max_symbols,
            "ablation": include_ablation,
            "recovery_started": launched.get("status") in {"started", "running"},
            "launcher": launched,
        }
        guard["last_result"] = dict(result)
        _LAST = result
        _save(core)
        return result


def _watchdog(core: Any) -> None:
    # State hydration can occur after worker initialization, so keep checking.
    time.sleep(5.0)
    while True:
        try:
            attempt_recovery(core, source="watchdog")
        except Exception as exc:
            guard = _guard_section(core)
            guard["error"] = f"{type(exc).__name__}: {exc}"
            guard["error_local"] = _now(core)
            _save(core)
        time.sleep(WATCHDOG_SECONDS)


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    if id(core) not in _WATCHDOGS:
        _WATCHDOGS.add(id(core))
        threading.Thread(
            target=_watchdog,
            args=(core,),
            name="performance-audit-v2-recovery-guard",
            daemon=True,
        ).start()
    guard = _guard_section(core)
    guard.update(
        {
            "status": "ok",
            "watchdog_started": True,
            "watchdog_seconds": WATCHDOG_SECONDS,
            "started_local": guard.get("started_local") or _now(core),
        }
    )
    _save(core)
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "watchdog_started": True,
        "watchdog_seconds": WATCHDOG_SECONDS,
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_sizing": False,
            "places_orders": False,
        },
    }


def status(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    return {
        "status": "ok",
        "type": "performance_audit_v2_recovery_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "watchdog_started": id(core) in _WATCHDOGS,
        "guard": _d(_section(core).get("recovery_guard")),
        "last": dict(_LAST),
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _core()
    start_watchdog(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}

    def status_route():
        return jsonify(status(core or _core()))

    def recover_route():
        return jsonify(attempt_recovery(core or _core(), source="manual_route"))

    routes = (
        ("/paper/performance-v2-recovery-status", "performance_v2_recovery_status", status_route),
        ("/paper/performance-v2-recover", "performance_v2_recover", recover_route),
    )
    for path, endpoint, fn in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, fn)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [row[0] for row in routes]}


try:
    core = _core()
    if core is not None and getattr(core, "app", None) is not None:
        start_watchdog(core)
except Exception:
    pass
