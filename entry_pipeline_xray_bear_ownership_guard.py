"""Prevent Entry Pipeline X-Ray from wrapping above the bear-recovery owner.

The valid public paper-entry stack is:

    bear soft-pause short recovery
      -> Entry Pipeline X-Ray
        -> deterministic breakout/composition pipeline
          -> direct core entry implementation

Entry Pipeline X-Ray's legacy patcher only inspected the public callable. When the
bear-recovery gate was outermost, it did not see the X-Ray marker beneath that
gate and added another X-Ray above it. This guard makes the X-Ray patcher aware
of the outer bear owner, then asks the deterministic stack contract to normalize
any already-duplicated wrappers.

This module is paper-only composition governance. It does not create signals,
change thresholds or sizing, alter hard risk limits, place orders, or grant live
or ML authority.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict

VERSION = "entry-pipeline-xray-bear-ownership-2026-07-29-v1"
WATCHDOG_FAST_ITERATIONS = 60
WATCHDOG_MAX_ITERATIONS = 1200

_LOCK = threading.RLock()
_REGISTERED_APPS: set[int] = set()
_WATCHDOG_STARTED: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _meta(fn: Any) -> Dict[str, Any]:
    return {
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "module": getattr(fn, "__module__", None),
        "bear_recovery_outer": bool(
            getattr(fn, "_bear_soft_pause_short_recovery_guard", False)
        ),
        "bear_recovery_version": getattr(
            fn, "_bear_soft_pause_short_recovery_version", None
        ),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
        "composition_version": getattr(
            fn, "_paper_exposure_composition_version", None
        ),
        "direct_core_base": bool(
            getattr(fn, "_entry_pipeline_direct_core_base", False)
        ),
    }


def _bear_prior(fn: Any) -> Any:
    prior = getattr(fn, "_bear_soft_pause_short_recovery_prior", None)
    return prior if callable(prior) else None


def _valid_xray_below_bear(fn: Any) -> bool:
    if not callable(fn) or not getattr(
        fn, "_bear_soft_pause_short_recovery_guard", False
    ):
        return False
    below = _bear_prior(fn)
    return bool(
        callable(below)
        and getattr(below, "_entry_pipeline_xray_version", None)
        and not getattr(below, "_bear_soft_pause_short_recovery_guard", False)
    )


def install(core: Any) -> Dict[str, Any]:
    """Patch X-Ray once and normalize the public stack immediately."""
    global _LAST_INSTALL
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        import entry_pipeline_xray as xray

        current_patch = getattr(xray, "_patch", None)
        original_patch = getattr(
            current_patch, "_xray_bear_ownership_original", current_patch
        )
        patched_this_call = False

        if callable(original_patch) and not getattr(
            current_patch, "_xray_bear_ownership_guard", False
        ):

            def bear_aware_patch(
                supplied_core: Any = None,
                __original=original_patch,
            ) -> bool:
                target = supplied_core or core
                public = getattr(target, "try_entries_and_rotations", None)

                # The diagnostic wrapper already exists immediately below the
                # authoritative bear gate. Never add another X-Ray above it.
                if _valid_xray_below_bear(public):
                    try:
                        xray._PATCHED = True
                        xray._PATCH_TARGET = xray._callable_metadata(
                            _bear_prior(public)
                        )
                    except Exception:
                        pass
                    return False

                # A bear-owned stack without a valid immediate X-Ray is repaired
                # by bear_recovery_stack_contract, not by wrapping outside the
                # risk owner. Returning here prevents X-Ray -> bear nesting.
                if callable(public) and getattr(
                    public, "_bear_soft_pause_short_recovery_guard", False
                ):
                    return False

                return bool(__original(target))

            bear_aware_patch._xray_bear_ownership_guard = True
            bear_aware_patch._xray_bear_ownership_version = VERSION
            bear_aware_patch._xray_bear_ownership_original = original_patch
            xray._patch = bear_aware_patch
            patched_this_call = True

        # Normalize any X-Ray -> bear -> X-Ray drift that existed before this
        # patch was installed.
        contract_result: Dict[str, Any] = {}
        try:
            import bear_recovery_stack_contract as contract

            row = contract.enforce(core)
            contract_result = row if isinstance(row, dict) else {}
        except Exception as exc:
            contract_result = {
                "status": "warn",
                "reason": f"stack_contract_error:{type(exc).__name__}:{exc}",
            }

        public = getattr(core, "try_entries_and_rotations", None)
        active_patch = getattr(xray, "_patch", None)
        _LAST_INSTALL = {
            "status": "ok" if getattr(
                active_patch, "_xray_bear_ownership_guard", False
            ) else "warn",
            "overall": "pass" if getattr(
                active_patch, "_xray_bear_ownership_guard", False
            ) and contract_result.get("owned") else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "patched_this_call": patched_this_call,
            "xray_patch_guard_active": bool(
                getattr(active_patch, "_xray_bear_ownership_guard", False)
            ),
            "public_entry_callable": _meta(public),
            "valid_xray_below_bear": _valid_xray_below_bear(public),
            "stack_contract": contract_result,
        }
        return dict(_LAST_INSTALL)


def status_payload(core: Any) -> Dict[str, Any]:
    result = install(core)
    public = getattr(core, "try_entries_and_rotations", None) if core else None
    try:
        import entry_pipeline_xray as xray

        patch = getattr(xray, "_patch", None)
        guard_active = bool(getattr(patch, "_xray_bear_ownership_guard", False))
    except Exception:
        guard_active = False

    try:
        import bear_recovery_stack_contract as contract

        stack = contract.status_payload(core)
    except Exception as exc:
        stack = {"status": "warn", "reason": str(exc)}

    passed = bool(
        core is not None
        and guard_active
        and stack.get("owned")
        and stack.get("wrapper_counts", {}).get("bear_wrapper_count") == 1
        and stack.get("wrapper_counts", {}).get("xray_wrapper_count") == 1
    )
    return {
        "status": "ok" if passed else "warn",
        "overall": "pass" if passed else "warn",
        "type": "entry_pipeline_xray_bear_ownership_status",
        "version": VERSION,
        "generated_local": _now(core),
        "xray_patch_guard_active": guard_active,
        "valid_xray_below_bear": _valid_xray_below_bear(public),
        "public_entry_callable": _meta(public),
        "stack_contract": stack,
        "last_install": result,
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_signal_generation": False,
            "changes_thresholds": False,
            "changes_sizing": False,
            "changes_hard_risk_limits": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "composition_and_ownership_only": True,
        },
    }


def register_routes(flask_app: Any, core: Any) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    path = "/paper/entry-pipeline-xray-bear-ownership-status"
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "entry_pipeline_xray_bear_ownership_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any) -> Dict[str, Any]:
    install(core)
    flask_app = getattr(core, "app", None) if core is not None else None
    if flask_app is not None:
        register_routes(flask_app, core)
    if core is None or id(core) in _WATCHDOG_STARTED:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": core is not None and id(core) in _WATCHDOG_STARTED,
        }

    _WATCHDOG_STARTED.add(id(core))

    def watch() -> None:
        for iteration in range(WATCHDOG_MAX_ITERATIONS):
            try:
                install(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics

                    runtime_diagnostics.record_exception(
                        exc,
                        source="entry_pipeline_xray_bear_ownership_guard.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < WATCHDOG_FAST_ITERATIONS else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="entry-pipeline-xray-bear-ownership-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
