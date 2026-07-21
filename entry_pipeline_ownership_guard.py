"""Own and repair the public paper entry callable.

The deterministic composition guard owns the inner callable and Entry Pipeline
X-Ray owns the outer diagnostic wrapper. This guard disables the legacy public
paper-exposure patch and repairs the stack only when drift is detected.

Inspection is read-only. Persistence occurs only for installation, drift,
repair, or error events. No candidate, threshold, sizing, risk-control, broker,
or ML authority changes.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict

VERSION = "entry-pipeline-ownership-guard-2026-07-21-v2-read-only-inspection"
OWNER_TOKEN = "composition-guard-inner+xray-outer"
REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_LEGACY_PATCH_DISABLED = False


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _meta(fn: Any) -> Dict[str, Any]:
    return {
        "name": getattr(fn, "__name__", None),
        "module": getattr(fn, "__module__", None),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
        "composition_version": getattr(fn, "_paper_exposure_composition_version", None),
        "direct_core_base": bool(getattr(fn, "_entry_pipeline_direct_core_base", False)),
        "owner_token": getattr(fn, "_entry_pipeline_owner_token", None),
        "legacy_paper_exposure_wrapper": bool(
            getattr(fn, "_paper_exposure_debug_patched", False)
            and getattr(fn, "_paper_exposure_composition_version", None) is None
        ),
    }


def _inner(fn: Any) -> Any:
    original = getattr(fn, "_entry_pipeline_xray_original", None)
    return original if callable(original) else fn


def _owned(fn: Any) -> bool:
    inner = _inner(fn)
    return bool(
        callable(fn)
        and getattr(fn, "_entry_pipeline_xray_version", None)
        and callable(inner)
        and getattr(inner, "_entry_pipeline_direct_core_base", False)
        and getattr(inner, "_paper_exposure_composition_version", None)
    )


def _state(core: Any) -> Dict[str, Any]:
    try:
        row = core.load_state()
        if isinstance(row, dict):
            return row
    except Exception:
        pass
    row = getattr(core, "portfolio", {}) or {}
    return row if isinstance(row, dict) else {}


def _disable_legacy_public_patch() -> bool:
    global _LEGACY_PATCH_DISABLED
    try:
        import paper_exposure_rotation as exposure
        current = getattr(exposure, "_patch_try_entries", None)
        if getattr(current, "_entry_pipeline_ownership_guard_version", None) == VERSION:
            _LEGACY_PATCH_DISABLED = True
            return False

        def ownership_managed_patch(_core: Any) -> bool:
            return False

        ownership_managed_patch._entry_pipeline_ownership_guard_version = VERSION  # type: ignore[attr-defined]
        ownership_managed_patch._legacy_public_wrapper_disabled = True  # type: ignore[attr-defined]
        exposure._patch_try_entries = ownership_managed_patch
        _LEGACY_PATCH_DISABLED = True
        return True
    except Exception:
        return False


def _persist_event(core: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    def updater(state: Dict[str, Any]) -> Dict[str, Any]:
        telemetry = state.get("entry_pipeline_ownership_guard")
        if not isinstance(telemetry, dict):
            telemetry = {}
        counters = telemetry.get("counters")
        if not isinstance(counters, dict):
            counters = {}
        counters["checks_total"] = int(counters.get("checks_total") or 0) + 1
        if event.get("drift_detected"):
            counters["drift_detected_total"] = int(counters.get("drift_detected_total") or 0) + 1
            telemetry["last_drift_local"] = event.get("generated_local")
            telemetry["last_displaced_callable"] = event.get("before")
        if event.get("drift_repaired"):
            counters["drift_repaired_total"] = int(counters.get("drift_repaired_total") or 0) + 1
            telemetry["last_repair_local"] = event.get("generated_local")
        if event.get("error"):
            counters["errors_total"] = int(counters.get("errors_total") or 0) + 1
            telemetry["last_error_local"] = event.get("generated_local")
        telemetry.update({
            "version": VERSION,
            "owner_token": OWNER_TOKEN,
            "updated_local": event.get("generated_local"),
            "legacy_public_patch_disabled": bool(_LEGACY_PATCH_DISABLED),
            "current_callable": event.get("current_callable"),
            "inner_callable": event.get("inner_callable"),
            "owned": bool(event.get("owned")),
            "last_error": event.get("error"),
            "counters": counters,
        })
        state["entry_pipeline_ownership_guard"] = telemetry
        return state

    update_state = getattr(core, "update_state", None)
    if callable(update_state):
        try:
            return update_state(updater, source="entry_pipeline_ownership_guard")
        except Exception as exc:
            return {"status": "warn", "written": False, "error": f"transactional_update_failed:{type(exc).__name__}:{exc}"}

    state = _state(core)
    updated = updater(state)
    try:
        core.save_state(updated)
        core.portfolio = updated
        return {"status": "ok", "written": True, "fallback": "save_state"}
    except Exception as exc:
        return {"status": "warn", "written": False, "error": f"save_failed:{type(exc).__name__}:{exc}"}


def inspect(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    current = getattr(core, "try_entries_and_rotations", None)
    inner = _inner(current)
    owned = _owned(current)
    state = _state(core)
    telemetry = state.get("entry_pipeline_ownership_guard")
    if not isinstance(telemetry, dict):
        telemetry = {}
    return {
        "status": "ok" if owned else "warn",
        "overall": "pass" if owned else "warn",
        "type": "entry_pipeline_ownership_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "owner_token": OWNER_TOKEN,
        "legacy_public_patch_disabled": bool(_LEGACY_PATCH_DISABLED),
        "owned": bool(owned),
        "drift_detected": not owned,
        "current_callable": _meta(current),
        "inner_callable": _meta(inner),
        "counters": telemetry.get("counters") or {},
        "last_drift_local": telemetry.get("last_drift_local"),
        "last_repair_local": telemetry.get("last_repair_local"),
        "last_error": telemetry.get("last_error"),
        "inspection_mutates_runtime": False,
        "authority_changed": False,
        "logic_changed": False,
    }


def enforce(core: Any = None, *, force: bool = False) -> Dict[str, Any]:
    global _PATCHED
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}

    disabled_this_call = _disable_legacy_public_patch()
    before_fn = getattr(core, "try_entries_and_rotations", None)
    before = _meta(before_fn)
    drift_detected = not _owned(before_fn)

    composition: Dict[str, Any] = {}
    xray_patched = False
    error = None
    if drift_detected or force:
        try:
            import entry_pipeline_composition_guard as composition_guard
            composition = composition_guard.enforce(core)
            import starter_valve_reason_sanitizer as sanitizer
            sanitizer.apply(core)
            import entry_pipeline_xray as xray
            xray_patched = bool(xray._patch(core))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

    current = getattr(core, "try_entries_and_rotations", None)
    inner = _inner(current)
    owned_after = _owned(current)
    if callable(current):
        current._entry_pipeline_owner_token = OWNER_TOKEN  # type: ignore[attr-defined]
        current._entry_pipeline_ownership_guard_version = VERSION  # type: ignore[attr-defined]
    if callable(inner):
        inner._entry_pipeline_owner_token = OWNER_TOKEN  # type: ignore[attr-defined]
        inner._entry_pipeline_ownership_guard_version = VERSION  # type: ignore[attr-defined]

    event = {
        "generated_local": _now(core),
        "before": before,
        "current_callable": _meta(current),
        "inner_callable": _meta(inner),
        "owned": bool(owned_after),
        "drift_detected": bool(drift_detected),
        "drift_repaired": bool(drift_detected and owned_after),
        "error": error,
    }
    persist = bool(disabled_this_call or drift_detected or force or error)
    persistence = _persist_event(core, event) if persist else {"status": "ok", "written": False, "no_change": True}
    _PATCHED = bool(owned_after)

    result = inspect(core)
    result.update({
        "disabled_this_call": bool(disabled_this_call),
        "drift_detected": bool(drift_detected),
        "drift_repaired": bool(drift_detected and owned_after),
        "composition": composition,
        "xray_patched_this_call": bool(xray_patched),
        "repair_attempted": bool(drift_detected or force),
        "persistence": persistence,
        "error": error,
    })
    if error or not owned_after:
        result["status"] = "warn"
        result["overall"] = "warn"
    return result


def apply(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return inspect(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/entry-pipeline-ownership-status" not in existing:
        flask_app.add_url_rule(
            "/paper/entry-pipeline-ownership-status",
            "entry_pipeline_ownership_status",
            lambda: jsonify(inspect(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    enforce(core or _mod())


try:
    enforce(_mod())
except Exception:
    pass
