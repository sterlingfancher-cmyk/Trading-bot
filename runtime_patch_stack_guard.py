"""Small guard that prevents paper aggression patchers from stacking every watchdog loop."""
from __future__ import annotations

import datetime as dt
import functools
import sys
from typing import Any, Dict, List, Tuple

VERSION = "patch-stack-guard-2026-05-26-v1"
_PATCHED = False
_LAST: Dict[str, Any] = {}

ORIGINAL_ATTRS = (
    "_risk_on_concentration_policy_original",
    "_paper_participation_original",
    "_paper_exposure_original",
)
TARGETS = (
    ("paper_exposure_rotation", "_paper_exposure_patched"),
    ("paper_participation_allocator", "_paper_participation_patched"),
    ("paper_risk_on_concentration_policy", "_risk_on_concentration_policy_patched"),
)


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    return None


def _next(fn: Any) -> Any | None:
    for attr in ORIGINAL_ATTRS:
        nxt = getattr(fn, attr, None)
        if callable(nxt):
            return nxt
    return None


def _chain(fn: Any, limit: int = 30) -> Tuple[List[Dict[str, Any]], bool]:
    nodes: List[Dict[str, Any]] = []
    seen: set[int] = set()
    cur = fn
    while callable(cur) and id(cur) not in seen and len(nodes) < limit:
        seen.add(id(cur))
        nodes.append({
            "name": getattr(cur, "__name__", str(cur)),
            "module": getattr(cur, "__module__", ""),
            "markers": [marker for _module_name, marker in TARGETS if getattr(cur, marker, False)],
        })
        nxt = _next(cur)
        if not callable(nxt):
            return nodes, False
        cur = nxt
    return nodes, bool(callable(cur) and id(cur) in seen)


def _chain_has_marker(fn: Any, marker: str) -> bool:
    nodes, _cycle = _chain(fn)
    return any(marker in (node.get("markers") or []) for node in nodes)


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    global _PATCHED, _LAST
    app_module = m or _mod()
    patched: List[str] = []
    already: List[str] = []
    errors: List[Dict[str, str]] = []

    for module_name, marker in TARGETS:
        try:
            module = sys.modules.get(module_name) or __import__(module_name)
            installer = getattr(module, "_patch_aggression", None)
            if not callable(installer):
                errors.append({"module": module_name, "error": "installer_missing"})
                continue
            if getattr(installer, "_patch_stack_guarded", False):
                already.append(module_name)
                continue

            @functools.wraps(installer)
            def guarded_patch(target_module: Any, __installer=installer, __marker=marker) -> bool:
                try:
                    current = getattr(target_module, "apply_aggression_adjustments", None)
                    if _chain_has_marker(current, __marker):
                        return False
                except Exception:
                    pass
                return bool(__installer(target_module))

            guarded_patch._patch_stack_guarded = True  # type: ignore[attr-defined]
            guarded_patch._patch_stack_original = installer  # type: ignore[attr-defined]
            setattr(module, "_patch_aggression", guarded_patch)
            patched.append(module_name)
        except Exception as exc:
            errors.append({"module": module_name, "error": str(exc)})

    chain, cycle = _chain(getattr(app_module, "apply_aggression_adjustments", None) if app_module is not None else None)
    _PATCHED = True
    _LAST = {
        "status": "ok",
        "type": "patch_stack_guard_status",
        "version": VERSION,
        "generated_local": _now(),
        "module_found": bool(app_module is not None),
        "patched": patched,
        "already_guarded": already,
        "errors": errors,
        "aggression_chain_depth": len(chain),
        "aggression_chain_cycle_detected": bool(cycle),
        "aggression_chain": chain[:12],
    }
    try:
        if app_module is not None and hasattr(app_module, "portfolio"):
            app_module.portfolio["patch_stack_guard"] = _LAST
    except Exception:
        pass
    return _LAST


def status(m: Any | None = None) -> Dict[str, Any]:
    if not _PATCHED:
        return apply_runtime_overrides(m or _mod())
    return dict(_LAST)


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/patch-stack-guard-status" not in existing:
        flask_app.add_url_rule("/paper/patch-stack-guard-status", "patch_stack_guard_status", lambda: jsonify(status(m or _mod())))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
