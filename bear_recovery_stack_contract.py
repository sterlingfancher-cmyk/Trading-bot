"""Deterministic ownership contract for bear soft-pause short recovery.

Desired public entry stack:

    bear soft-pause short recovery (outer side-aware risk gate)
      -> entry pipeline X-ray (diagnostic)
        -> breakout/composition guard
          -> direct core entry pipeline

This module reconciles the existing recurring composition and ownership guards with
the newer bear-recovery layer. It does not create signals, place orders directly,
or change live/ML authority, thresholds, or hard risk limits.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict, List

VERSION = "bear-recovery-stack-contract-2026-07-29-v1"
WATCHDOG_FAST_ITERATIONS = 60
WATCHDOG_MAX_ITERATIONS = 1200

_LOCK = threading.RLock()
_REGISTERED_APPS: set[int] = set()
_WATCHDOG_STARTED: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_ENFORCE: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _bear_prior(fn: Any) -> Any:
    prior = getattr(fn, "_bear_soft_pause_short_recovery_prior", None)
    return prior if callable(prior) else None


def _xray_prior(fn: Any) -> Any:
    prior = getattr(fn, "_entry_pipeline_xray_original", None)
    return prior if callable(prior) else None


def _composition_inner(fn: Any) -> Any:
    """Return the deterministic composition callable beneath known outer guards."""
    current = fn
    seen: set[int] = set()
    for _ in range(12):
        if not callable(current) or id(current) in seen:
            break
        seen.add(id(current))
        prior = _bear_prior(current)
        if callable(prior):
            current = prior
            continue
        prior = _xray_prior(current)
        if callable(prior):
            current = prior
            continue
        break
    return current


def _xray_callable(fn: Any) -> Any:
    """Return the X-ray wrapper directly beneath the bear gate."""
    prior = _bear_prior(fn)
    return prior if callable(prior) else fn


def _ownership_inner(fn: Any) -> Any:
    xray = _xray_callable(fn)
    prior = _xray_prior(xray)
    return prior if callable(prior) else xray


def _owned(fn: Any) -> bool:
    """Require bear outer -> X-ray -> deterministic composition."""
    if not callable(fn):
        return False
    if not getattr(fn, "_bear_soft_pause_short_recovery_guard", False):
        return False
    xray = _xray_callable(fn)
    if not callable(xray) or not getattr(xray, "_entry_pipeline_xray_version", None):
        return False
    inner = _ownership_inner(fn)
    return bool(
        callable(inner)
        and getattr(inner, "_entry_pipeline_direct_core_base", False)
        and getattr(inner, "_paper_exposure_composition_version", None)
        and getattr(inner, "_core_entry_pipeline_non_wrapper_patched", False)
    )


def _meta(fn: Any) -> Dict[str, Any]:
    return {
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "module": getattr(fn, "__module__", None),
        "bear_recovery_version": getattr(
            fn, "_bear_soft_pause_short_recovery_version", None
        ),
        "bear_recovery_outer": bool(
            getattr(fn, "_bear_soft_pause_short_recovery_guard", False)
        ),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
        "composition_version": getattr(
            fn, "_paper_exposure_composition_version", None
        ),
        "direct_core_base": bool(
            getattr(fn, "_entry_pipeline_direct_core_base", False)
        ),
        "core_entry_pipeline_version": getattr(
            fn, "_core_entry_pipeline_version", None
        ),
        "owner_token": getattr(fn, "_entry_pipeline_owner_token", None),
    }


def _scanner_snapshot(core: Any) -> Dict[str, Any]:
    state = _state(core)
    auto = _d(state.get("auto_runner"))
    last = _d(auto.get("last_result"))
    audit = _d(state.get("scanner_audit"))
    short_symbols = _l(last.get("short_signals")) or _l(audit.get("short_signals"))
    long_symbols = _l(last.get("long_signals")) or _l(audit.get("long_signals"))
    rejected = [
        row
        for row in (_l(last.get("rejected_signals")) or _l(audit.get("rejected_signals")))
        if isinstance(row, dict)
    ]
    rejected_shorts = [
        row
        for row in rejected
        if str(row.get("side") or "").lower() == "short"
    ]
    return {
        "last_run_local": auto.get("last_run_local"),
        "last_successful_run_local": auto.get("last_successful_run_local"),
        "signals_found": last.get("signals_found", audit.get("signals_found")),
        "short_signals_count": len(short_symbols),
        "short_signal_symbols": short_symbols[:20],
        "long_signals_count": len(long_symbols),
        "long_signal_symbols": long_symbols[:10],
        "rejected_short_preview": rejected_shorts[:12],
        "note": (
            "Zero short candidates is a scanner outcome, not an ownership failure."
            if not short_symbols
            else "Stored short candidates are available for the recovery gate."
        ),
    }


def _patch_contract_modules(core: Any) -> Dict[str, Any]:
    """Patch helper contracts without rebuilding trading logic."""
    import entry_pipeline_composition_guard as composition
    import entry_pipeline_ownership_guard as ownership
    import bear_soft_pause_short_recovery as bear

    patched: Dict[str, bool] = {}

    if getattr(composition, "_inner_callable", None) is not _composition_inner:
        composition._inner_callable = _composition_inner
        patched["composition_inner_callable"] = True

    if getattr(ownership, "_inner", None) is not _ownership_inner:
        ownership._inner = _ownership_inner
        patched["ownership_inner_callable"] = True

    if getattr(ownership, "_owned", None) is not _owned:
        ownership._owned = _owned
        patched["ownership_predicate"] = True

    original_meta = getattr(ownership, "_meta", None)
    if not getattr(original_meta, "_bear_recovery_stack_contract", False):
        def ownership_meta(fn: Any) -> Dict[str, Any]:
            base = {}
            try:
                base = original_meta(fn) if callable(original_meta) else {}
            except Exception:
                base = {}
            base.update(_meta(fn))
            return base

        ownership_meta._bear_recovery_stack_contract = True
        ownership_meta._bear_recovery_stack_contract_original = original_meta
        ownership._meta = ownership_meta
        patched["ownership_meta"] = True

    current_enforce = getattr(ownership, "enforce", None)
    if callable(current_enforce) and not getattr(
        current_enforce, "_bear_recovery_stack_contract", False
    ):
        def contract_enforce(
            supplied_core: Any = None,
            *,
            force: bool = False,
            __prior=current_enforce,
        ) -> Dict[str, Any]:
            target = supplied_core or core

            # Normalize an incomplete bear wrapper before the legacy ownership
            # repair adds X-ray. This prevents bear -> X-ray -> bear nesting.
            current_public = getattr(target, "try_entries_and_rotations", None)
            if getattr(
                current_public, "_bear_soft_pause_short_recovery_guard", False
            ):
                direct_below_bear = _bear_prior(current_public)
                if callable(direct_below_bear) and not getattr(
                    direct_below_bear, "_entry_pipeline_xray_version", None
                ):
                    target.try_entries_and_rotations = direct_below_bear

            prior_result: Dict[str, Any] = {}
            try:
                row = __prior(target, force=force)
                prior_result = row if isinstance(row, dict) else {}
            except TypeError:
                row = __prior(target)
                prior_result = row if isinstance(row, dict) else {}
            bear.install(target)
            final = ownership.inspect(target)
            final["contract_version"] = VERSION
            final["prior_ownership_result"] = prior_result
            final["bear_recovery_reapplied"] = True
            return final

        contract_enforce._bear_recovery_stack_contract = True
        contract_enforce._bear_recovery_stack_contract_original = current_enforce
        ownership.enforce = contract_enforce
        ownership.apply = contract_enforce
        ownership.apply_runtime_overrides = contract_enforce
        patched["ownership_enforce"] = True

    return {
        "patched": patched,
        "composition_version": getattr(composition, "VERSION", None),
        "ownership_version": getattr(ownership, "VERSION", None),
        "bear_recovery_version": getattr(bear, "VERSION", None),
    }


def enforce(core: Any) -> Dict[str, Any]:
    global _LAST_ENFORCE
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        module_patch = _patch_contract_modules(core)
        import entry_pipeline_ownership_guard as ownership
        import bear_soft_pause_short_recovery as bear

        ownership_result = ownership.enforce(core)
        bear.install(core)

        current = getattr(core, "try_entries_and_rotations", None)
        xray = _xray_callable(current)
        inner = _ownership_inner(current)
        owned = _owned(current)
        _LAST_ENFORCE = {
            "status": "ok" if owned else "warn",
            "overall": "pass" if owned else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "owned": owned,
            "public_entry_callable": _meta(current),
            "xray_callable": _meta(xray),
            "composition_callable": _meta(inner),
            "module_patch": module_patch,
            "ownership_result": ownership_result,
            "desired_stack": [
                "bear_soft_pause_short_recovery_outer",
                "entry_pipeline_xray",
                "paper_exposure_breakout_composition",
                "direct_core_entry_pipeline",
            ],
        }
        try:
            state = _state(core)
            state["bear_recovery_stack_contract"] = dict(_LAST_ENFORCE)
        except Exception:
            pass
        return dict(_LAST_ENFORCE)


def status_payload(core: Any) -> Dict[str, Any]:
    current = getattr(core, "try_entries_and_rotations", None) if core else None
    xray = _xray_callable(current)
    inner = _ownership_inner(current)
    owned = _owned(current)
    return {
        "status": "ok" if core is not None and owned else "warn",
        "overall": "pass" if core is not None and owned else "warn",
        "type": "bear_recovery_stack_contract_status",
        "version": VERSION,
        "generated_local": _now(core),
        "owned": owned,
        "entry_guard_active": bool(
            getattr(current, "_bear_soft_pause_short_recovery_guard", False)
        ),
        "public_entry_callable": _meta(current),
        "xray_callable": _meta(xray),
        "composition_callable": _meta(inner),
        "scanner_snapshot": _scanner_snapshot(core) if core is not None else {},
        "last_enforce": dict(_LAST_ENFORCE),
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_thresholds": False,
            "changes_hard_risk_limits": False,
            "changes_signal_generation": False,
            "composition_and_ownership_only": True,
        },
    }


def register_routes(flask_app: Any, core: Any) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    enforce(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    path = "/paper/bear-recovery-stack-status"
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "bear_recovery_stack_contract_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any) -> Dict[str, Any]:
    enforce(core)
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
                enforce(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics
                    runtime_diagnostics.record_exception(
                        exc,
                        source="bear_recovery_stack_contract.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < WATCHDOG_FAST_ITERATIONS else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="bear-recovery-stack-contract-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
