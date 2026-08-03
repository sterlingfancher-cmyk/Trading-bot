"""Keep performance-audit and underdeployment cycle wrappers composition-stable.

Both modules use watchdogs. This guard propagates wrapper ownership markers from
the callable chain to the top callable so neither watchdog mistakes the other's
wrapper for a missing installation and repeatedly adds layers.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from typing import Any, Dict

VERSION = "performance-audit-composition-guard-2026-08-03-v1"
MARKERS = (
    "_paper_underdeployment_cycle_version",
    "_performance_audit_lab_version",
)
_LINKS = ("__wrapped__", "_paper_underdeployment_cycle_prior", "_performance_audit_prior")
_WATCHDOGS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _chain(fn: Any) -> list[Any]:
    queue = [fn]
    seen: set[int] = set()
    out: list[Any] = []
    while queue and len(out) < 40:
        item = queue.pop(0)
        if not callable(item) or id(item) in seen:
            continue
        seen.add(id(item))
        out.append(item)
        for attr in _LINKS:
            linked = getattr(item, attr, None)
            if callable(linked):
                queue.append(linked)
    return out


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _module()
    try:
        import core_entry_pipeline as pipeline
    except Exception as exc:
        return {"status": "pending", "version": VERSION, "reason": f"pipeline_import_failed:{type(exc).__name__}:{exc}"}
    top = getattr(pipeline, "_core_try_entries_and_rotations", None)
    if not callable(top):
        return {"status": "pending", "version": VERSION, "reason": "cycle_callable_missing"}
    chain = _chain(top)
    propagated: Dict[str, Any] = {}
    for marker in MARKERS:
        value = None
        for fn in chain:
            candidate = getattr(fn, marker, None)
            if candidate:
                value = candidate
                break
        if value:
            try:
                setattr(top, marker, value)
                propagated[marker] = value
            except Exception:
                pass
    _LAST = {
        "status": "ok", "overall": "pass", "version": VERSION,
        "generated_local": _now(core), "chain_depth": len(chain),
        "propagated_markers": propagated,
        "stable": all(getattr(top, marker, None) for marker in MARKERS),
    }
    if core is not None:
        try:
            core.portfolio.setdefault("performance_audit_composition_guard", {}).update(_LAST)
        except Exception:
            pass
    return dict(_LAST)


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    result = install(core)
    key = id(core) if core is not None else 0
    if key not in _WATCHDOGS:
        _WATCHDOGS.add(key)
        def worker():
            while True:
                try:
                    install(core)
                except Exception:
                    pass
                time.sleep(5)
        threading.Thread(target=worker, name="performance-audit-composition-guard", daemon=True).start()
    return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {**install(core or _module()), "type": "performance_audit_composition_guard_status"}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/performance-audit-composition-status" not in existing:
        flask_app.add_url_rule(
            "/paper/performance-audit-composition-status",
            "performance_audit_composition_status",
            lambda: jsonify(status_payload(core or _module())),
        )
    return start_watchdog(core or _module())


try:
    start_watchdog(_module())
except Exception:
    pass
