from __future__ import annotations

import sys
from typing import Any, Dict, List, Set, Tuple

VERSION = "scanner-stack-emergency-reset-2026-07-27-v1"
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    return None


def _callable_label(fn: Any) -> Dict[str, Any]:
    return {
        "module": getattr(fn, "__module__", None),
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "id": id(fn) if callable(fn) else None,
    }


def _linked_callables(fn: Any) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    if not callable(fn):
        return out
    try:
        attrs = vars(fn)
    except Exception:
        attrs = {}
    for key, value in attrs.items():
        key_l = str(key).lower()
        if callable(value) and ("original" in key_l or "wrapped" in key_l or "base" in key_l or "inner" in key_l):
            out.append((str(key), value))
    wrapped = getattr(fn, "__wrapped__", None)
    if callable(wrapped):
        out.append(("__wrapped__", wrapped))
    return out


def _discover(current: Any, limit: int = 256) -> Dict[str, Any]:
    queue: List[Tuple[Any, List[str]]] = [(current, [])]
    seen: Set[int] = set()
    rows: List[Dict[str, Any]] = []
    candidates: List[Any] = []
    cycle_detected = False

    while queue and len(rows) < limit:
        fn, path = queue.pop(0)
        if not callable(fn):
            continue
        ident = id(fn)
        if ident in seen:
            cycle_detected = True
            continue
        seen.add(ident)
        label = _callable_label(fn)
        label["path"] = path
        rows.append(label)

        name = str(getattr(fn, "__name__", ""))
        module = str(getattr(fn, "__module__", ""))
        qualname = str(getattr(fn, "__qualname__", ""))
        is_core_named = name == "scan_signals" and module in {"app", "__main__"}
        is_nested_patch = "<locals>" in qualname or name in {"wrapped", "patched_scan_signals"}
        if is_core_named and not is_nested_patch:
            candidates.append(fn)

        for attr, linked in _linked_callables(fn):
            queue.append((linked, path + [attr]))

    selected = candidates[-1] if candidates else None
    return {
        "selected": selected,
        "cycle_detected": cycle_detected,
        "nodes": rows,
        "candidate_count": len(candidates),
        "truncated": bool(queue),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION}

    current = getattr(core, "scan_signals", None)
    discovery = _discover(current)
    selected = discovery.pop("selected", None)
    changed = False
    reason = "core_scanner_not_found"

    if callable(selected):
        core.scan_signals = selected
        changed = selected is not current
        reason = "restored_deepest_core_app_scan_signals"

    # Prevent the registration watchdog from rebuilding scanner overlays after reset.
    setattr(core, "SCANNER_OVERLAYS_QUARANTINED", True)

    _LAST = {
        "status": "ok" if callable(selected) else "warn",
        "overall": "pass" if callable(selected) else "warn",
        "version": VERSION,
        "changed": changed,
        "reason": reason,
        "before": _callable_label(current),
        "after": _callable_label(getattr(core, "scan_signals", None)),
        "cycle_detected": discovery.get("cycle_detected"),
        "candidate_count": discovery.get("candidate_count"),
        "nodes_inspected": len(discovery.get("nodes") or []),
        "chain_preview": (discovery.get("nodes") or [])[:20],
        "scanner_overlays_quarantined": True,
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
    }
    return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    payload = dict(_LAST) if _LAST else apply(core)
    if core is not None:
        payload["current"] = _callable_label(getattr(core, "scan_signals", None))
        payload["scanner_overlays_quarantined"] = bool(getattr(core, "SCANNER_OVERLAYS_QUARANTINED", False))
    return payload


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/scanner-stack-emergency-reset-status" not in existing:
        flask_app.add_url_rule(
            "/paper/scanner-stack-emergency-reset-status",
            "scanner_stack_emergency_reset_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
