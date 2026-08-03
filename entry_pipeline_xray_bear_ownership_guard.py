"""Atomic ownership for the public paper-entry stack.

Required public entry stack:

    bear soft-pause short recovery
      -> Entry Pipeline X-Ray
        -> deterministic breakout/composition pipeline
          -> direct core entry implementation

This guard closes a watchdog race in which the bear layer could be reinstalled
while the ownership contract was temporarily rebuilding X-Ray. It also marks
the bounded neutral staged participation valve as the canonical risk-on outer
helper so the composition guard does not remove it on its next integrity pass.

Paper-only composition governance. No signal, threshold, sizing, hard-risk,
live-authority, ML-authority, or direct-order change.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict

VERSION = "entry-pipeline-xray-bear-ownership-2026-08-03-v2-atomic"
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
        "bear_recovery_outer": bool(getattr(fn, "_bear_soft_pause_short_recovery_guard", False)),
        "bear_recovery_version": getattr(fn, "_bear_soft_pause_short_recovery_version", None),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
        "composition_version": getattr(fn, "_paper_exposure_composition_version", None),
        "direct_core_base": bool(getattr(fn, "_entry_pipeline_direct_core_base", False)),
        "owner_token": getattr(fn, "_entry_pipeline_owner_token", None),
    }


def _bear_prior(fn: Any) -> Any:
    prior = getattr(fn, "_bear_soft_pause_short_recovery_prior", None)
    return prior if callable(prior) else None


def _valid_xray_below_bear(fn: Any) -> bool:
    if not callable(fn) or not getattr(fn, "_bear_soft_pause_short_recovery_guard", False):
        return False
    below = _bear_prior(fn)
    return bool(
        callable(below)
        and getattr(below, "_entry_pipeline_xray_version", None)
        and not getattr(below, "_bear_soft_pause_short_recovery_guard", False)
    )


def _raw_xray_patch(xray: Any) -> Any:
    current = getattr(xray, "_patch", None)
    return getattr(current, "_xray_bear_ownership_original", current)


def _decorate_neutral_chain(core: Any) -> Dict[str, Any]:
    """Make the staged neutral valve a stable canonical participation outer."""
    try:
        import core_entry_pipeline as pipeline
        import entry_pipeline_composition_guard as composition
    except Exception as exc:
        return {"status": "warn", "active": False, "reason": f"chain_import_failed:{type(exc).__name__}:{exc}"}

    fn = getattr(pipeline, "_participation_valve_ok", None)
    neutral_version = getattr(fn, "_neutral_momentum_starter_extension_version", None)
    if not callable(fn) or not neutral_version:
        return {"status": "pending", "active": False, "reason": "neutral_staged_valve_not_outermost"}

    fn._participation_valve_chain_version = composition.VALVE_CHAIN_VERSION
    fn._participation_valve_chain_role = "risk_on_outer"
    fn._neutral_staged_chain_owned = True
    fn._neutral_staged_chain_owner_version = VERSION
    return {
        "status": "ok",
        "active": True,
        "neutral_version": neutral_version,
        "participation_valve_chain_version": composition.VALVE_CHAIN_VERSION,
        "participation_valve_chain_role": "risk_on_outer",
    }


def _patch_neutral_install(core: Any) -> Dict[str, Any]:
    """Decorate every neutral install, including later watchdog reinstalls."""
    try:
        import neutral_momentum_starter_extension as neutral
    except Exception as exc:
        return {"status": "warn", "reason": f"neutral_import_failed:{type(exc).__name__}:{exc}"}

    current = getattr(neutral, "install", None)
    original = getattr(current, "_atomic_entry_stack_original", current)
    patched = False
    if callable(original) and not getattr(current, "_atomic_entry_stack_neutral_chain_guard", False):
        def chain_owned_install(supplied_core: Any = None, __original=original):
            target = supplied_core or core
            row = __original(target)
            chain = _decorate_neutral_chain(target)
            if isinstance(row, dict):
                row = dict(row)
                row["participation_valve_chain_ownership"] = chain
            return row

        chain_owned_install._atomic_entry_stack_neutral_chain_guard = True
        chain_owned_install._atomic_entry_stack_owner_version = VERSION
        chain_owned_install._atomic_entry_stack_original = original
        neutral.install = chain_owned_install
        patched = True

    try:
        result = neutral.install(core)
    except Exception as exc:
        return {
            "status": "warn",
            "patched_this_call": patched,
            "reason": f"neutral_install_failed:{type(exc).__name__}:{exc}",
        }
    return {
        "status": "ok",
        "patched_this_call": patched,
        "install": result if isinstance(result, dict) else {},
        "chain": _decorate_neutral_chain(core),
    }


def _atomic_rebuild(core: Any) -> Dict[str, Any]:
    """Rebuild composition -> X-Ray -> bear while blocking the bear watchdog."""
    import bear_recovery_stack_contract as contract
    import bear_soft_pause_short_recovery as bear
    import entry_pipeline_composition_guard as composition
    import entry_pipeline_xray as xray

    with contract._LOCK:
        with bear._LOCK:
            before = getattr(core, "try_entries_and_rotations", None)
            base = contract._composition_inner(before)
            if callable(base):
                core.try_entries_and_rotations = base

            composition_result = composition.enforce(core)
            _patch_neutral_install(core)

            raw_patch = _raw_xray_patch(xray)
            xray_patched = bool(raw_patch(core)) if callable(raw_patch) else False
            bear_result = bear.install(core)

            current = getattr(core, "try_entries_and_rotations", None)
            owned = contract._owned(current)
            return {
                "status": "ok" if owned else "warn",
                "overall": "pass" if owned else "warn",
                "version": VERSION,
                "generated_local": _now(core),
                "owned": owned,
                "before": _meta(before),
                "after": _meta(current),
                "wrapper_counts": contract._wrapper_counts(current),
                "xray_patched": xray_patched,
                "composition": composition_result if isinstance(composition_result, dict) else {},
                "bear": bear_result if isinstance(bear_result, dict) else {},
                "neutral_chain": _decorate_neutral_chain(core),
            }


def _patch_contract_enforce(core: Any) -> Dict[str, Any]:
    """Serialize every contract enforcement with the bear installer lock."""
    import bear_recovery_stack_contract as contract
    import bear_soft_pause_short_recovery as bear

    current = getattr(contract, "enforce", None)
    original = getattr(current, "_atomic_entry_stack_original", current)
    patched = False
    if callable(original) and not getattr(current, "_atomic_entry_stack_contract_guard", False):
        def atomic_contract_enforce(supplied_core: Any, __original=original):
            target = supplied_core or core
            with contract._LOCK:
                with bear._LOCK:
                    row = __original(target)
                    result = row if isinstance(row, dict) else {}
                    if not result.get("owned"):
                        repair = _atomic_rebuild(target)
                        refreshed = contract.status_payload(target)
                        refreshed["atomic_repair"] = repair
                        refreshed["last_prior_enforce"] = result
                        return refreshed
                    return result

        atomic_contract_enforce._atomic_entry_stack_contract_guard = True
        atomic_contract_enforce._atomic_entry_stack_owner_version = VERSION
        atomic_contract_enforce._atomic_entry_stack_original = original
        contract.enforce = atomic_contract_enforce
        patched = True
    return {"status": "ok", "patched_this_call": patched}


def _patch_ownership_enforce(core: Any) -> Dict[str, Any]:
    """Serialize direct ownership-guard calls made outside the stack contract."""
    import bear_recovery_stack_contract as contract
    import bear_soft_pause_short_recovery as bear
    import entry_pipeline_ownership_guard as ownership

    current = getattr(ownership, "enforce", None)
    original = getattr(current, "_atomic_entry_stack_original", current)
    patched = False
    if callable(original) and not getattr(current, "_atomic_entry_stack_ownership_guard", False):
        def atomic_ownership_enforce(supplied_core: Any = None, *, force: bool = False, __original=original):
            target = supplied_core or core
            with contract._LOCK:
                with bear._LOCK:
                    try:
                        row = __original(target, force=force)
                    except TypeError:
                        row = __original(target)
                    result = row if isinstance(row, dict) else {}
                    if not result.get("owned"):
                        repair = _atomic_rebuild(target)
                        refreshed = ownership.inspect(target)
                        refreshed["atomic_repair"] = repair
                        refreshed["last_prior_enforce"] = result
                        return refreshed
                    return result

        atomic_ownership_enforce._atomic_entry_stack_ownership_guard = True
        atomic_ownership_enforce._atomic_entry_stack_owner_version = VERSION
        atomic_ownership_enforce._atomic_entry_stack_original = original
        # Preserve the marker checked by bear_recovery_stack_contract so it does
        # not wrap this transaction layer as a new legacy ownership function.
        atomic_ownership_enforce._bear_recovery_stack_contract_v2 = True
        atomic_ownership_enforce._bear_recovery_stack_contract_original = getattr(
            original, "_bear_recovery_stack_contract_original", original
        )
        ownership.enforce = atomic_ownership_enforce
        ownership.apply = atomic_ownership_enforce
        ownership.apply_runtime_overrides = atomic_ownership_enforce
        patched = True
    return {"status": "ok", "patched_this_call": patched}


def _patch_xray(core: Any) -> Dict[str, Any]:
    import entry_pipeline_xray as xray

    current = getattr(xray, "_patch", None)
    original = getattr(current, "_xray_bear_ownership_original", current)
    patched = False
    if callable(original) and not getattr(current, "_xray_bear_ownership_guard", False):
        def bear_aware_patch(supplied_core: Any = None, __original=original) -> bool:
            target = supplied_core or core
            public = getattr(target, "try_entries_and_rotations", None)
            if _valid_xray_below_bear(public):
                try:
                    xray._PATCHED = True
                    xray._PATCH_TARGET = xray._callable_metadata(_bear_prior(public))
                except Exception:
                    pass
                return False

            # Unlike v1, a bear-owned stack missing X-Ray is repaired atomically
            # rather than ignored. This is the race that produced the Aug. 3 drift.
            if callable(public) and getattr(public, "_bear_soft_pause_short_recovery_guard", False):
                return bool(_atomic_rebuild(target).get("owned"))

            return bool(__original(target))

        bear_aware_patch._xray_bear_ownership_guard = True
        bear_aware_patch._xray_bear_ownership_version = VERSION
        bear_aware_patch._xray_bear_ownership_original = original
        xray._patch = bear_aware_patch
        patched = True
    return {"status": "ok", "patched_this_call": patched}


def install(core: Any) -> Dict[str, Any]:
    global _LAST_INSTALL
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        xray_patch = _patch_xray(core)
        neutral_patch = _patch_neutral_install(core)
        contract_patch = _patch_contract_enforce(core)

        import bear_recovery_stack_contract as contract
        contract_result = contract.enforce(core)
        ownership_patch = _patch_ownership_enforce(core)

        public = getattr(core, "try_entries_and_rotations", None)
        if not contract._owned(public):
            repair = _atomic_rebuild(core)
            public = getattr(core, "try_entries_and_rotations", None)
        else:
            repair = {"status": "ok", "overall": "pass", "reason": "already_owned"}

        active_patch = None
        try:
            import entry_pipeline_xray as xray
            active_patch = getattr(xray, "_patch", None)
        except Exception:
            pass

        owned = contract._owned(public)
        _LAST_INSTALL = {
            "status": "ok" if owned else "warn",
            "overall": "pass" if owned else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "owned": owned,
            "entry_guard_active": bool(getattr(public, "_bear_soft_pause_short_recovery_guard", False)),
            "valid_xray_below_bear": _valid_xray_below_bear(public),
            "wrapper_counts": contract._wrapper_counts(public),
            "public_entry_callable": _meta(public),
            "xray_patch_guard_active": bool(getattr(active_patch, "_xray_bear_ownership_guard", False)),
            "xray_patch": xray_patch,
            "contract_patch": contract_patch,
            "ownership_patch": ownership_patch,
            "neutral_chain_patch": neutral_patch,
            "contract": contract_result if isinstance(contract_result, dict) else {},
            "atomic_repair": repair,
        }
        return dict(_LAST_INSTALL)


def status_payload(core: Any) -> Dict[str, Any]:
    result = install(core)
    public = getattr(core, "try_entries_and_rotations", None) if core else None
    try:
        import bear_recovery_stack_contract as contract
        stack = contract.status_payload(core)
    except Exception as exc:
        stack = {"status": "warn", "reason": str(exc)}
    passed = bool(
        core is not None
        and result.get("owned")
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
        "owned": passed,
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
            "atomic_runtime_transaction": True,
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
