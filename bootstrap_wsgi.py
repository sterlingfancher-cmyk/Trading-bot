"""Deferred WSGI dispatcher with startup visibility.

Gunicorn serves a lightweight bootstrap status before the legacy Flask
application and runtime registrations load in a background timer thread. Once
ready, all non-bootstrap requests delegate to the unchanged Flask app.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Iterable

VERSION = "deferred-wsgi-bootstrap-2026-08-06-v6-registration-heartbeat"
_START_MONOTONIC = time.monotonic()
_LOCK = threading.RLock()
_DELEGATE: Callable[..., Any] | None = None
_LOADER_THREAD: threading.Thread | None = None
_REGISTRATION_HEARTBEAT_INTERVAL_SECONDS = 5.0
_REGISTRATION_SLOW_AFTER_SECONDS = 60.0
_V2_ENABLED_VALUE = (
    os.environ["PERFORMANCE_AUDIT_V2_ENABLED"]
    if "PERFORMANCE_AUDIT_V2_ENABLED" in os.environ
    else "false"
)


def _loader_delay_seconds() -> float:
    raw = os.environ.get("DEFERRED_WSGI_START_DELAY_SECONDS", "1.0")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.1, min(value, 10.0))


_LOADER_DELAY_SECONDS = _loader_delay_seconds()
_STATE: dict[str, Any] = {
    "status": "loading",
    "phase": "bootstrap_scheduled",
    "version": VERSION,
    "started_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "research_isolated": _V2_ENABLED_VALUE.lower()
    in {"0", "false", "no", "off"},
    "loader_start_delay_seconds": _LOADER_DELAY_SECONDS,
}


def _set_state(**values: Any) -> None:
    with _LOCK:
        _STATE.update(values)
        _STATE["elapsed_seconds"] = round(time.monotonic() - _START_MONOTONIC, 3)
        _STATE["updated_local"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _snapshot() -> dict[str, Any]:
    with _LOCK:
        out = dict(_STATE)
        out["elapsed_seconds"] = round(time.monotonic() - _START_MONOTONIC, 3)
        out["delegate_ready"] = _DELEGATE is not None
        out["loader_thread_started"] = _LOADER_THREAD is not None
        out["loader_thread_alive"] = bool(
            _LOADER_THREAD is not None and _LOADER_THREAD.is_alive()
        )
        return out


def _bridge_has_error(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return True
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        return payload.get("status") == "error"
    return any(
        isinstance(row, dict) and row.get("status") == "error"
        for row in modules.values()
    )


def _registration_heartbeat_payload(
    started_monotonic: float,
    now_monotonic: float | None = None,
) -> dict[str, Any]:
    now_value = time.monotonic() if now_monotonic is None else float(now_monotonic)
    elapsed = max(0.0, now_value - float(started_monotonic))
    return {
        "status": "loading",
        "phase": "runtime_worker_registration",
        "registration_elapsed_seconds": round(elapsed, 3),
        "registration_slow": elapsed >= _REGISTRATION_SLOW_AFTER_SECONDS,
        "registration_heartbeat_interval_seconds": _REGISTRATION_HEARTBEAT_INTERVAL_SECONDS,
        "registration_message": (
            "Runtime registration is still active; startup has not failed."
            if elapsed < _REGISTRATION_SLOW_AFTER_SECONDS
            else "Runtime registration is taking longer than 60 seconds but remains active."
        ),
    }


def _registration_heartbeat_loop(
    stop_event: threading.Event,
    started_monotonic: float,
) -> None:
    while not stop_event.wait(_REGISTRATION_HEARTBEAT_INTERVAL_SECONDS):
        _set_state(**_registration_heartbeat_payload(started_monotonic))


def _load_application() -> None:
    global _DELEGATE
    registration_heartbeat_stop: threading.Event | None = None
    registration_started_monotonic: float | None = None
    try:
        _set_state(status="loading", phase="legacy_wsgi_import")
        import wsgi as legacy_wsgi

        delegate = getattr(legacy_wsgi, "app", None)
        if delegate is None or not callable(delegate):
            raise RuntimeError("legacy wsgi app missing or not callable")

        core = sys.modules.get("app")
        if core is None:
            raise RuntimeError("app module missing after legacy WSGI import")

        _set_state(status="loading", phase="data_integrity_registration")
        import data_integrity_startup_bridge

        integrity_apply = data_integrity_startup_bridge.apply(core)
        integrity_routes = data_integrity_startup_bridge.register_routes(delegate, core)
        if _bridge_has_error(integrity_apply) or _bridge_has_error(integrity_routes):
            raise RuntimeError(
                "data integrity registration failed: "
                + json.dumps(
                    {"apply": integrity_apply, "routes": integrity_routes},
                    sort_keys=True,
                    default=str,
                )[:3000]
            )

        registration_started_monotonic = time.monotonic()
        _set_state(
            status="loading",
            phase="runtime_worker_registration",
            registration_started_local=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            registration_elapsed_seconds=0.0,
            registration_slow=False,
            registration_heartbeat_interval_seconds=_REGISTRATION_HEARTBEAT_INTERVAL_SECONDS,
            registration_message="Runtime registration started.",
        )
        registration_heartbeat_stop = threading.Event()
        registration_heartbeat_thread = threading.Thread(
            target=_registration_heartbeat_loop,
            args=(registration_heartbeat_stop, registration_started_monotonic),
            daemon=True,
            name="runtime-registration-bootstrap-heartbeat",
        )
        registration_heartbeat_thread.start()

        import runtime_worker_registration

        try:
            registration = runtime_worker_registration.register(
                core,
                research_isolated=bool(_STATE.get("research_isolated", True)),
            )
        finally:
            registration_heartbeat_stop.set()

        registration_duration = round(
            time.monotonic() - registration_started_monotonic,
            3,
        )
        _set_state(
            status="loading",
            phase="runtime_worker_registration_complete",
            registration_elapsed_seconds=registration_duration,
            registration_duration_seconds=registration_duration,
            registration_slow=registration_duration >= _REGISTRATION_SLOW_AFTER_SECONDS,
            registration_message="Runtime registration completed; delegate activation is next.",
        )
        if registration.get("status") != "ok":
            raise RuntimeError(
                "runtime registration failed: "
                + str(registration.get("error") or registration.get("reason"))
            )

        with _LOCK:
            _DELEGATE = delegate
        _set_state(
            status="ready",
            phase="delegating",
            registration=registration,
            registration_duration_seconds=registration_duration,
            data_integrity_registration={
                "apply": integrity_apply,
                "routes": integrity_routes,
            },
            app_module=getattr(core, "__name__", "app"),
        )
    except Exception as exc:
        if registration_heartbeat_stop is not None:
            registration_heartbeat_stop.set()
        failure_values: dict[str, Any] = {}
        if registration_started_monotonic is not None:
            failure_values["registration_elapsed_seconds"] = round(
                time.monotonic() - registration_started_monotonic,
                3,
            )
        _set_state(
            status="error",
            phase="startup_failed",
            error=f"{type(exc).__name__}: {exc}",
            traceback="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-6000:],
            **failure_values,
        )


def _json_response(
    start_response: Callable[..., Any],
    payload: dict[str, Any],
    status: str = "200 OK",
) -> Iterable[bytes]:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


class DeferredApplication:
    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]):
        path = str(environ.get("PATH_INFO") or "/")
        state = _snapshot()

        if path == "/bootstrap-status":
            return _json_response(start_response, state)

        with _LOCK:
            delegate = _DELEGATE
        if delegate is not None:
            return delegate(environ, start_response)

        if path == "/":
            return _json_response(start_response, state)
        return _json_response(
            start_response,
            {
                **state,
                "requested_path": path,
                "message": (
                    "The paper application is still loading. "
                    "Use /bootstrap-status for progress."
                ),
            },
            "503 Service Unavailable",
        )


# The WSGI callable is fully constructed before the heavy loader is scheduled.
# This avoids starting the legacy import while Gunicorn is still importing this
# module and guarantees that the bootstrap listener can answer independently.
app = DeferredApplication()
_LOADER_THREAD = threading.Timer(
    _LOADER_DELAY_SECONDS,
    _load_application,
)
_LOADER_THREAD.name = "deferred-paper-application-loader"
_LOADER_THREAD.daemon = True
_LOADER_THREAD.start()
