"""Own and repair the public paper entry callable.

The deterministic composition guard owns the inner callable and Entry Pipeline
X-Ray owns the outer diagnostic wrapper.  paper_exposure_rotation may still run
its legacy public-wrapper patch later in startup and displace both layers.  This
module disables that legacy public patch, repairs the composed stack, reapplies
X-Ray, and persists drift telemetry.

No candidate, threshold, sizing, risk-control, broker, or ML authority changes.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict

VERSION = "entry-pipeline-ownership-guard-2026-07-20-v1"
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
    try:
        row = getattr(core, "portfolio", {}) or {}
        return row if isinstance(row, dict) else {}
    except Exception:
        return {}


def _save(core: Any, state: Dict[str, Any]) -> None:
    try:
        core.save_state(state)
        core.portfolio = state
    except Exception:
        try:
            core.portfolio = state
        except Exception:
            pass


def _disable_legacy_public_patch() -> bool:
    global _LEGACY_PATCH_DISABLED
    try:
        import paper_exposure_rotation as exposure
        current = getattr(exposure, "_patch_try_entries", None)
        if getattr(current, "_entry_pipeline_ownership_guard_version", None) == VERSION:
            _LEGACY_PATCH_DISABLED = True
            return False

        def ownership_managed_patch(_core: Any) -> bool:
            # The composition guard already includes paper-exposure diagnostics.
            # Never replace app.try_entries_and_rotations from this legacy path.
            return False

        ownership_managed_patch._entry_pipeline_ownership_guard_version = VERSION  # type: ignore[attr-defined]
        ownership_managed_patch._legacy_public_wrapper_disabled = True  # type: ignore[attr-defined]
        exposure._patch_try_entries = ownership_managed_patch
        _LEGACY_PATCH_DISABLED = True
        return True
    except Exception:
        return False


def enforce(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}

    disabled_this_call = _disable_legacy_public_patch()
    before_fn = getattr(core, "try_entries_and_rotations", None)
    before = _meta(before_fn)
    drift_detected = not _owned(before_fn)

    composition = {}
    xray_patched = False
    error = None
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

    state = _state(core)
    telemetry = state.setdefault("entry_pipeline_ownership_guard", {})
    if not isinstance(telemetry, dict):
        telemetry = {}
        state["entry_pipeline_ownership_guard"] = telemetry
    counters = telemetry.setdefault("counters", {})
    if not isinstance(counters, dict):
        counters = {}
        telemetry["counters"] = counters
    counters["checks_total"] = int(counters.get("checks_total") or 0) + 1
    if drift_detected:
        counters["drift_detected_total"] = int(counters.get("drift_detected_total") or 0) + 1
        telemetry["last_drift_local"] = _now(core)
        telemetry["last_displaced_callable"] = before
    if drift_detected and owned_after:
        counters["drift_repaired_total"] = int(counters.get("drift_repaired_total") or 0) + 1
        telemetry["last_repair_local"] = _now(core)

    telemetry.update({
        "version": VERSION,
        "owner_token": OWNER_TOKEN,
        "updated_local": _now(core),
        "legacy_public_patch_disabled": bool(_LEGACY_PATCH_DISABLED),
        "current_callable": _meta(current),
        "inner_callable": _meta(inner),
        "owned": bool(owned_after),
        "last_error": error,
    })
    _save(core, state)
    _PATCHED = bool(owned_after)

    return {
        "status": "ok" if owned_after and not error else "warn",
        "overall": "pass" if owned_after and not error else "warn",
        "type": "entry_pipeline_ownership_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "owner_token": OWNER_TOKEN,
        "legacy_public_patch_disabled": bool(_LEGACY_PATCH_DISABLED),
        "disabled_this_call": bool(disabled_this_call),
        "drift_detected": bool(drift_detected),
        "drift_repaired": bool(drift_detected and owned_after),
        "owned": bool(owned_after),
        "before": before,
        "current_callable": _meta(current),
        "inner_callable": _meta(inner),
        "composition": composition if isinstance(composition, dict) else {},
        "xray_patched_this_call": bool(xray_patched),
        "counters": counters,
        "error": error,
        "authority_changed": False,
        "logic_changed": False,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION}
    return enforce(core)


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
            lambda: jsonify(enforce(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    enforce(core or _mod())


try:
    enforce(_mod())
except Exception:
    pass
