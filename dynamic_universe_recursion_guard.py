"""Emergency recursion guard for scanner overlay instrumentation.

This module now prioritizes runtime continuity. It prevents dynamic-universe scanner
rewrapping and, after startup registration completes, restores the deepest core
app.scan_signals callable through scanner_stack_emergency_reset. Trading strategy,
thresholds, sizing, risk controls, ML authority, and live authority are unchanged.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Any, Dict

VERSION = "dynamic-universe-recursion-guard-2026-07-27-v2-emergency-reset"
_MARKER = "_dynamic_universe_builder_patched"
_ORIGINAL_ATTRS = (
    "_dynamic_universe_builder_original",
    "_shared_cycle_identity_original",
    "_scanner_v2_lifecycle_trace_original",
    "__wrapped__",
)
_PATCHED = False
_RESET_STARTED = False
_LAST_RESET: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    return None


def _chain_has_marker(fn: Any, marker: str = _MARKER, limit: int = 80) -> bool:
    seen: set[int] = set()
    current = fn
    for _ in range(limit):
        if not callable(current) or id(current) in seen:
            return False
        seen.add(id(current))
        if bool(getattr(current, marker, False)):
            return True
        next_fn = None
        for attr in _ORIGINAL_ATTRS:
            candidate = getattr(current, attr, None)
            if callable(candidate):
                next_fn = candidate
                break
        current = next_fn
    return False


def _run_delayed_reset() -> None:
    global _LAST_RESET
    # Allow usercustomize to finish its one-time module registration first.
    time.sleep(2.0)
    try:
        import scanner_stack_emergency_reset as reset
        core = _mod()
        if core is not None:
            setattr(core, "SCANNER_OVERLAYS_QUARANTINED", True)
        _LAST_RESET = reset.apply(core)
    except Exception as exc:
        _LAST_RESET = {
            "status": "warn",
            "version": VERSION,
            "error": f"delayed_reset_failed:{type(exc).__name__}:{exc}",
        }


def _start_delayed_reset() -> None:
    global _RESET_STARTED
    if _RESET_STARTED:
        return
    _RESET_STARTED = True
    try:
        threading.Thread(target=_run_delayed_reset, daemon=True).start()
    except Exception as exc:
        global _LAST_RESET
        _LAST_RESET = {"status": "warn", "error": f"reset_thread_failed:{type(exc).__name__}:{exc}"}


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    core = core or _mod()
    try:
        import dynamic_universe_builder as module
    except Exception as exc:
        return {"status": "pending", "version": VERSION, "error": f"import_failed:{type(exc).__name__}"}

    original_patch = getattr(module, "_patch_scan_signals", None)
    if not callable(original_patch):
        return {"status": "pending", "version": VERSION, "error": "patch_function_missing"}

    if not getattr(original_patch, "_dynamic_universe_recursion_guard_v2", False):
        def guarded_patch_scan_signals(runtime: Any) -> bool:
            if runtime is None:
                return False
            if bool(getattr(runtime, "SCANNER_OVERLAYS_QUARANTINED", False)):
                return False
            current = getattr(runtime, "scan_signals", None)
            if not callable(current):
                return False
            if _chain_has_marker(current):
                return False
            return bool(original_patch(runtime))

        guarded_patch_scan_signals._dynamic_universe_recursion_guard_v2 = True  # type: ignore[attr-defined]
        guarded_patch_scan_signals._dynamic_universe_original_patch = original_patch  # type: ignore[attr-defined]
        module._patch_scan_signals = guarded_patch_scan_signals

    if core is not None:
        setattr(core, "SCANNER_OVERLAYS_QUARANTINED", True)
    _start_delayed_reset()
    _PATCHED = True
    return {
        "status": "ok",
        "version": VERSION,
        "patched": True,
        "chain_marker_detection": True,
        "scanner_overlays_quarantined": bool(getattr(core, "SCANNER_OVERLAYS_QUARANTINED", False)) if core is not None else False,
        "delayed_reset_started": _RESET_STARTED,
        "authority_changed": False,
    }


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    current = getattr(core, "scan_signals", None) if core is not None else None
    return {
        "status": "ok" if _PATCHED else "pending",
        "version": VERSION,
        "patched": _PATCHED,
        "dynamic_marker_present_in_chain": _chain_has_marker(current) if callable(current) else False,
        "scanner_overlays_quarantined": bool(getattr(core, "SCANNER_OVERLAYS_QUARANTINED", False)) if core is not None else False,
        "current_callable": getattr(current, "__qualname__", None) if callable(current) else None,
        "delayed_reset_started": _RESET_STARTED,
        "last_reset": dict(_LAST_RESET),
        "authority_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/dynamic-universe-recursion-guard-status" not in existing:
        flask_app.add_url_rule(
            "/paper/dynamic-universe-recursion-guard-status",
            "dynamic_universe_recursion_guard_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
