"""Runtime guard for dynamic-universe scan_signals instrumentation.

Prevents dynamic_universe_builder from repeatedly wrapping scan_signals when another
scanner wrapper is outermost. This is authority-neutral: it only makes the existing
patch idempotent across the complete callable chain.
"""
from __future__ import annotations

import sys
from typing import Any, Dict

VERSION = "dynamic-universe-recursion-guard-2026-07-27-v1"
_MARKER = "_dynamic_universe_builder_patched"
_ORIGINAL_ATTRS = (
    "_dynamic_universe_builder_original",
    "_shared_cycle_identity_original",
    "_scanner_v2_lifecycle_trace_original",
    "__wrapped__",
)
_PATCHED = False


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

    if not getattr(original_patch, "_dynamic_universe_recursion_guard", False):
        def guarded_patch_scan_signals(runtime: Any) -> bool:
            current = getattr(runtime, "scan_signals", None)
            if not callable(current):
                return False
            if _chain_has_marker(current):
                return False
            return bool(original_patch(runtime))

        guarded_patch_scan_signals._dynamic_universe_recursion_guard = True  # type: ignore[attr-defined]
        guarded_patch_scan_signals._dynamic_universe_original_patch = original_patch  # type: ignore[attr-defined]
        module._patch_scan_signals = guarded_patch_scan_signals

    _PATCHED = True
    return {
        "status": "ok",
        "version": VERSION,
        "patched": True,
        "chain_marker_detection": True,
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
