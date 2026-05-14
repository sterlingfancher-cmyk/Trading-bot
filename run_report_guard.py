from __future__ import annotations

import datetime as dt
import functools
import os
import threading
from typing import Any, Dict, List

VERSION = "run-report-guard-2026-05-14"
_APPLIED: set[int] = set()
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}
_RECENT: List[Dict[str, Any]] = []


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


def _inline_enabled() -> bool:
    return str(os.environ.get("RUN_CYCLE_INLINE_REPORTS", "false")).lower() in {"1", "true", "yes", "on"}


def _deferred(core: Any, report_type: str, args: tuple, kwargs: dict) -> Dict[str, Any]:
    item = {
        "status": "deferred",
        "type": report_type or "intraday",
        "date": _today(core),
        "generated_local": _now(core),
        "version": VERSION,
        "reason": "Inline report compilation is skipped during /paper/run to prevent request timeouts.",
        "report_links": ["/paper/intraday-report", "/paper/risk-review", "/paper/report/today", "/paper/end-of-day-report"],
        "args_seen": len(args),
        "kwargs_seen": sorted(list(kwargs.keys())),
    }
    _RECENT.append(item)
    del _RECENT[:-10]
    return item


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None or not hasattr(core, "run_cycle"):
        return {"status": "not_applied", "version": VERSION, "reason": "core_or_run_cycle_missing"}
    if id(core) in _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}
    original = core.run_cycle
    if getattr(original, "_run_report_guard", False):
        _APPLIED.add(id(core))
        return {"status": "ok", "version": VERSION, "already_wrapped": True}

    @functools.wraps(original)
    def wrapped_run_cycle(*args, **kwargs):
        global _LAST
        if _inline_enabled():
            return original(*args, **kwargs)
        original_store = getattr(core, "store_compiled_report", None)
        deferred: List[Dict[str, Any]] = []

        def store_stub(report_type="intraday", *s_args, **s_kwargs):
            item = _deferred(core, report_type, s_args, s_kwargs)
            deferred.append(item)
            return item

        with _LOCK:
            try:
                if callable(original_store):
                    core.store_compiled_report = store_stub
                result = original(*args, **kwargs)
                if isinstance(result, dict):
                    result["run_report_guard"] = {
                        "version": VERSION,
                        "inline_report_compilation": False,
                        "normal_test_link": "/paper/self-check",
                        "report_links": ["/paper/intraday-report", "/paper/risk-review", "/paper/report/today", "/paper/end-of-day-report"],
                    }
                    if deferred:
                        result["compiled_report"] = deferred[-1]
                        result["deferred_reports_count"] = len(deferred)
                _LAST = {"status": "ok", "version": VERSION, "generated_local": _now(core), "deferred_reports_count": len(deferred)}
                return result
            finally:
                if callable(original_store):
                    try:
                        core.store_compiled_report = original_store
                    except Exception:
                        pass

    wrapped_run_cycle._run_report_guard = True
    core.run_cycle = wrapped_run_cycle
    try:
        core.RUN_REPORT_GUARD_VERSION = VERSION
    except Exception:
        pass
    _APPLIED.add(id(core))
    return {"status": "ok", "version": VERSION, "patched": ["run_cycle"]}


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "run_report_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "installed": bool(core is not None and id(core) in _APPLIED),
        "inline_report_compilation": _inline_enabled(),
        "normal_test_link": "/paper/self-check",
        "recent_deferred_reports": list(_RECENT),
        "last_status": _LAST,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/run-report-guard-status" in existing:
        return
    from flask import jsonify
    flask_app.add_url_rule("/paper/run-report-guard-status", "run_report_guard_status", lambda: jsonify(status_payload(core)))
