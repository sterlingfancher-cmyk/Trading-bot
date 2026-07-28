"""Persistent read-only runtime diagnostics for Railway deployments.

Captures uncaught exceptions, thread exceptions, Flask request failures, startup
module load events, and deployment metadata in bounded JSON files on the Railway
volume. This module never places orders or changes strategy, thresholds, sizing,
risk controls, ML authority, or live authority.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import sys
import threading
import time
import traceback
from collections import Counter
from typing import Any, Dict, List, Optional

VERSION = "runtime-diagnostics-2026-07-28-v1"
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ERROR_FILE = os.path.join(STATE_DIR, "runtime_errors.json")
LOAD_TRACE_FILE = os.path.join(STATE_DIR, "module_load_trace.json")
MAX_ERRORS = max(20, int(os.environ.get("RUNTIME_DIAGNOSTICS_MAX_ERRORS", "100")))
MAX_LOAD_EVENTS = max(50, int(os.environ.get("RUNTIME_DIAGNOSTICS_MAX_LOAD_EVENTS", "500")))
STARTED_TS = time.time()
STARTED_LOCAL = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_HOOKS_INSTALLED = False


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path: str, payload: Any) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _load_list(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    except Exception:
        return []


def deployment_info() -> Dict[str, Any]:
    env_keys = (
        "RAILWAY_DEPLOYMENT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID", "RAILWAY_PROJECT_NAME", "RAILWAY_SERVICE_ID",
        "RAILWAY_SERVICE_NAME", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_BRANCH",
        "RAILWAY_PUBLIC_DOMAIN", "PORT",
    )
    return {
        "status": "ok",
        "type": "deployment_info",
        "version": VERSION,
        "generated_local": _now(),
        "started_local": STARTED_LOCAL,
        "uptime_seconds": round(time.time() - STARTED_TS, 3),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "pid": os.getpid(),
        "environment": {key: os.environ.get(key) for key in env_keys if os.environ.get(key)},
        "authority": {
            "changes_strategy": False, "changes_thresholds": False,
            "changes_risk_or_sizing": False, "places_orders": False,
            "changes_ml_authority": False, "changes_live_authority": False,
        },
    }


def record_exception(
    exc: BaseException,
    *,
    source: str,
    module: Optional[str] = None,
    function: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        tb = repr(exc)
    event = {
        "timestamp_local": _now(),
        "timestamp_ts": time.time(),
        "source": source,
        "module": module,
        "function": function,
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": tb[-30000:],
        "thread": threading.current_thread().name,
        "deployment": deployment_info().get("environment", {}),
        "context": context or {},
    }
    try:
        with _LOCK:
            rows = _load_list(ERROR_FILE)
            rows.append(event)
            _atomic_write(ERROR_FILE, rows[-MAX_ERRORS:])
    except Exception:
        pass
    return event


def record_module_event(module: str, status: str, *, function: Optional[str] = None, error: Optional[str] = None) -> None:
    event = {
        "timestamp_local": _now(),
        "timestamp_ts": time.time(),
        "module": module,
        "function": function,
        "status": status,
        "error": error,
    }
    try:
        with _LOCK:
            rows = _load_list(LOAD_TRACE_FILE)
            rows.append(event)
            _atomic_write(LOAD_TRACE_FILE, rows[-MAX_LOAD_EVENTS:])
    except Exception:
        pass


def runtime_errors_payload() -> Dict[str, Any]:
    rows = _load_list(ERROR_FILE)
    return {
        "status": "ok",
        "type": "runtime_errors",
        "version": VERSION,
        "generated_local": _now(),
        "retained_count": len(rows),
        "max_errors": MAX_ERRORS,
        "errors": list(reversed(rows)),
        "authority_changed": False,
    }


def module_load_trace_payload() -> Dict[str, Any]:
    rows = _load_list(LOAD_TRACE_FILE)
    return {
        "status": "ok",
        "type": "module_load_trace",
        "version": VERSION,
        "generated_local": _now(),
        "retained_count": len(rows),
        "max_events": MAX_LOAD_EVENTS,
        "events": list(reversed(rows)),
        "authority_changed": False,
    }


def exception_summary_payload() -> Dict[str, Any]:
    rows = _load_list(ERROR_FILE)
    by_type = Counter(str(row.get("exception_type") or "Unknown") for row in rows)
    by_module = Counter(str(row.get("module") or row.get("source") or "unknown") for row in rows)
    latest = rows[-1] if rows else None
    return {
        "status": "ok",
        "type": "exception_summary",
        "version": VERSION,
        "generated_local": _now(),
        "total_retained": len(rows),
        "by_exception_type": dict(by_type.most_common()),
        "by_module_or_source": dict(by_module.most_common()),
        "latest_error": latest,
        "authority_changed": False,
    }


def install_hooks() -> None:
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True
    old_sys_hook = sys.excepthook

    def sys_hook(exc_type, exc, tb):
        if isinstance(exc, BaseException):
            record_exception(exc, source="sys.excepthook", module=getattr(exc_type, "__module__", None))
        old_sys_hook(exc_type, exc, tb)

    sys.excepthook = sys_hook
    if hasattr(threading, "excepthook"):
        old_thread_hook = threading.excepthook

        def thread_hook(args):
            try:
                record_exception(
                    args.exc_value,
                    source="threading.excepthook",
                    module=getattr(args.thread, "name", None),
                    context={"thread_name": getattr(args.thread, "name", None)},
                )
            finally:
                old_thread_hook(args)

        threading.excepthook = thread_hook


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify, request

    install_hooks()
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    routes = {
        "/paper/runtime-errors": ("runtime_errors", runtime_errors_payload),
        "/paper/module-load-trace": ("module_load_trace", module_load_trace_payload),
        "/paper/exception-summary": ("exception_summary", exception_summary_payload),
        "/paper/deployment-info": ("deployment_info", deployment_info),
    }
    for path, (endpoint, builder) in routes.items():
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, lambda builder=builder: jsonify(builder()))

    @flask_app.errorhandler(Exception)
    def _diagnostic_error_handler(exc):
        record_exception(
            exc,
            source="flask.errorhandler",
            module=getattr(request, "endpoint", None),
            context={"path": request.path, "method": request.method},
        )
        code = int(getattr(exc, "code", 500) or 500)
        return jsonify({"status": "error", "error": str(exc), "type": type(exc).__name__, "diagnostics_recorded": True}), code

    _REGISTERED_APP_IDS.add(id(flask_app))
    record_module_event("runtime_diagnostics", "registered")


install_hooks()
