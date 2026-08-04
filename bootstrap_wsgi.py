"""Deferred WSGI dispatcher with startup visibility.

Gunicorn can serve a lightweight bootstrap status immediately while the legacy
Flask application and runtime registrations load in a background thread. Once
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

VERSION = "deferred-wsgi-bootstrap-2026-08-03-v1"
_START_MONOTONIC = time.monotonic()
_LOCK = threading.RLock()
_DELEGATE: Callable[..., Any] | None = None
_STATE: dict[str, Any] = {
    "status": "loading",
    "phase": "bootstrap_imported",
    "version": VERSION,
    "started_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "research_isolated": os.environ.get(
        "PERFORMANCE_AUDIT_V2_ENABLED", "false"
    ).lower()
    in {"0", "false", "no", "off"},
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
        return out


def _load_application() -> None:
    global _DELEGATE
    try:
        _set_state(status="loading", phase="legacy_wsgi_import")
        import wsgi as legacy_wsgi

        delegate = getattr(legacy_wsgi, "app", None)
        if delegate is None or not callable(delegate):
            raise RuntimeError("legacy wsgi app missing or not callable")

        core = sys.modules.get("app")
        if core is None:
            raise RuntimeError("app module missing after legacy WSGI import")

        _set_state(status="loading", phase="runtime_worker_registration")
        import runtime_worker_registration

        registration = runtime_worker_registration.register(
            core,
            research_isolated=bool(_STATE.get("research_isolated", True)),
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
            app_module=getattr(core, "__name__", "app"),
        )
    except Exception as exc:
        _set_state(
            status="error",
            phase="startup_failed",
            error=f"{type(exc).__name__}: {exc}",
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:],
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
                "message": "The paper application is still loading. Use /bootstrap-status for progress.",
            },
            "503 Service Unavailable",
        )


app = DeferredApplication()
threading.Thread(
    target=_load_application,
    name="deferred-paper-application-loader",
    daemon=True,
).start()
