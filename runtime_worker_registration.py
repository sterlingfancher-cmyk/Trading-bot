"""Explicit idempotent registration for the paper-trading web worker.

This module consolidates the former Gunicorn ``post_worker_init`` registration
block. It is called after the legacy Flask application has finished importing.
It does not change signal formulas, thresholds, sizing, risk limits, order
placement, live authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
from typing import Any, Dict

import runtime_diagnostics as diagnostics

VERSION = "runtime-worker-registration-2026-09-03-v9-system-sentinel"
_LOCK = threading.RLock()
_REGISTERED_CORE_IDS: set[int] = set()
_KICKOFF_STARTED: set[int] = set()
_LAST: Dict[str, Any] = {}
_TRUE = {"1", "true", "yes", "on"}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _restore_deferred_auto_configuration(core: Any) -> Dict[str, Any]:
    deferred = os.environ.get("AUTO_RUN_DEFERRED_BOOTSTRAP", "false").lower() in _TRUE
    requested_text = os.environ.get("AUTO_RUN_REQUESTED", os.environ.get("AUTO_RUN_ENABLED", "true"))
    requested = requested_text.lower() not in {"0", "false", "no", "off"}
    if deferred:
        try:
            core.AUTO_RUN_ENABLED = requested
        except Exception:
            pass
        portfolio = getattr(core, "portfolio", {})
        if isinstance(portfolio, dict):
            auto = portfolio.setdefault("auto_runner", {})
            if isinstance(auto, dict):
                auto["enabled"] = requested
                auto["deferred_bootstrap"] = True
                auto["deferred_bootstrap_restored_local"] = _now()
        os.environ["AUTO_RUN_ENABLED"] = "true" if requested else "false"
    return {
        "deferred": deferred,
        "requested_enabled": requested,
        "restored": deferred,
    }


def _start_immediate_kickoff(core: Any, enabled: bool) -> Dict[str, Any]:
    if not enabled:
        return {"started": False, "reason": "auto_runner_disabled"}
    if id(core) in _KICKOFF_STARTED:
        return {"started": False, "reason": "already_started"}
    run_cycle = getattr(core, "run_cycle", None)
    if not callable(run_cycle):
        return {"started": False, "reason": "run_cycle_missing"}

    def kickoff() -> None:
        try:
            run_cycle(source="auto", allow_after_hours=False)
        except Exception as exc:
            diagnostics.record_exception(
                exc,
                source="runtime_worker_registration.immediate_kickoff",
                module="app",
            )

    thread = threading.Thread(
        target=kickoff,
        daemon=True,
        name="paper-auto-post-composition-kickoff",
    )
    _KICKOFF_STARTED.add(id(core))
    thread.start()
    portfolio = getattr(core, "portfolio", {})
    if isinstance(portfolio, dict):
        auto = portfolio.setdefault("auto_runner", {})
        if isinstance(auto, dict):
            auto["post_composition_kickoff_started"] = True
            auto["post_composition_kickoff_local"] = _now()
    return {
        "started": True,
        "reason": "post_composition_immediate_cycle",
        "thread_name": thread.name,
    }


def _start_auto_runner(core: Any) -> Dict[str, Any]:
    """Start the existing app-owned loop after restoring deferred configuration."""
    restored = _restore_deferred_auto_configuration(core)
    ensure = getattr(core, "ensure_auto_thread", None)
    if not callable(ensure):
        return {
            "status": "error",
            "started": False,
            "reason": "ensure_auto_thread_missing",
            "deferred_configuration": restored,
        }
    ensure()
    portfolio = getattr(core, "portfolio", {})
    auto = portfolio.get("auto_runner", {}) if isinstance(portfolio, dict) else {}
    global_started = bool(getattr(core, "AUTO_THREAD_STARTED", False))
    reported_before_sync = bool(auto.get("thread_started")) if isinstance(auto, dict) else False

    # Older persisted state can retain thread_started=false even when the app's
    # authoritative process-global owner is already active. Synchronize only
    # this diagnostic field; no strategy, risk, or execution behavior changes.
    diagnostic_state_synchronized = False
    if global_started and isinstance(auto, dict) and not reported_before_sync:
        auto["thread_started"] = True
        auto["thread_start_owner"] = "runtime_worker_registration"
        auto["thread_state_synchronized_local"] = _now()
        diagnostic_state_synchronized = True

    reported = bool(auto.get("thread_started")) if isinstance(auto, dict) else False
    enabled = bool(auto.get("enabled")) if isinstance(auto, dict) else bool(restored.get("requested_enabled"))
    started = bool(reported or global_started)
    kickoff = _start_immediate_kickoff(core, enabled) if restored.get("deferred") else {"started": False, "reason": "not_deferred"}
    return {
        "status": "ok" if started else "error",
        "started": started,
        "reported_thread_started": reported,
        "reported_before_sync": reported_before_sync,
        "global_thread_started": global_started,
        "diagnostic_state_synchronized": diagnostic_state_synchronized,
        "enabled": enabled,
        "interval_seconds": auto.get("interval_seconds") if isinstance(auto, dict) else None,
        "owner": "app.ensure_auto_thread",
        "ordering": "after_runtime_composition",
        "deferred_configuration": restored,
        "immediate_kickoff": kickoff,
    }


def register(core: Any, *, research_isolated: bool = True) -> Dict[str, Any]:
    global _LAST
    if core is None or getattr(core, "app", None) is None:
        return {
            "status": "error",
            "version": VERSION,
            "reason": "core_or_flask_app_missing",
        }

    with _LOCK:
        if id(core) in _REGISTERED_CORE_IDS:
            auto_runner = _start_auto_runner(core)
            return {
                "status": "ok" if auto_runner.get("status") == "ok" else "error",
                "overall": "pass" if auto_runner.get("status") == "ok" else "warn",
                "version": VERSION,
                "already_registered": True,
                "research_isolated": research_isolated,
                "auto_runner": auto_runner,
            }

        try:
            import provider_timeout_contract
            import state_persistence_contract
            import cycle_completion_contract
            import daily_audit_repair_overlay
            import run_report_guard
            import shadow_ai_adversarial_reviewer
            import shadow_ai_evidence_store
            import shadow_ai_observability
            import system_sentinel_runtime
            import performance_risk_activation_guard
            import regime_integrity_underdeployment
            import regime_integrity_cache_guard
            import bear_soft_pause_short_recovery
            import bear_recovery_stack_contract
            import entry_pipeline_xray_bear_ownership_guard
            import opening_surge_participation
            import opening_surge_score_calibration
            import breakout_scanner_ownership_guard
            import scanner_runtime_contract
            import neutral_momentum_starter_extension
            import neutral_late_session_participation
            import paper_underdeployment_repair
            import paper_underdeployment_time_guard
            import paper_regime_adaptive_policy
            import performance_audit_lab
            import performance_audit_lab_v2
            import performance_audit_composition_guard

            if research_isolated:
                performance_audit_lab.AUTO_BACKTEST = False
                performance_audit_lab_v2.AUTO_BACKTEST = False
                performance_audit_lab_v2.ENABLED = False

            # Operational contracts must be in place before the first real auto
            # cycle: mounted state first, provider timeout second, lifecycle
            # telemetry third. They do not change trading decisions.
            state_result = state_persistence_contract.apply(core)
            state_persistence_contract.register_routes(core.app, core)
            provider_result = provider_timeout_contract.apply(core)
            provider_timeout_contract.register_routes(core.app, core)
            cycle_result = cycle_completion_contract.apply(core)
            cycle_completion_contract.register_routes(core.app, core)
            daily_overlay_result = daily_audit_repair_overlay.apply(core)
            daily_audit_repair_overlay.register_routes(core.app, core)

            # The target module is fully imported in this web worker now. Apply
            # the epoch-aware parser synchronously before any entry cycle can
            # evaluate second-starter spacing. The configured spacing remains
            # unchanged; only timestamp timezone semantics are corrected.
            entry_time_guard_result = paper_underdeployment_time_guard.apply()
            if not entry_time_guard_result.get("patched"):
                raise RuntimeError(
                    "paper underdeployment entry-time guard failed to install: "
                    + str(entry_time_guard_result)
                )

            regime_integrity_underdeployment.start_watchdog(core)
            regime_integrity_underdeployment.register_routes(core.app, core)
            regime_integrity_cache_guard.start_watchdog(core)
            performance_risk_activation_guard.start_watchdog(core)
            performance_risk_activation_guard.register_routes(core.app, core)
            bear_soft_pause_short_recovery.start_watchdog(core)
            bear_soft_pause_short_recovery.register_routes(core.app, core)
            bear_recovery_stack_contract.start_watchdog(core)
            bear_recovery_stack_contract.register_routes(core.app, core)
            entry_pipeline_xray_bear_ownership_guard.start_watchdog(core)
            entry_pipeline_xray_bear_ownership_guard.register_routes(core.app, core)
            opening_surge_participation.start_watchdog(core)
            opening_surge_participation.register_routes(core.app, core)
            opening_surge_score_calibration.start_watchdog(core)
            opening_surge_score_calibration.register_routes(core.app, core)
            breakout_scanner_ownership_guard.start_watchdog(core)
            breakout_scanner_ownership_guard.register_routes(core.app, core)
            scanner_runtime_contract.start_watchdog(core)
            scanner_runtime_contract.register_routes(core.app, core)
            neutral_momentum_starter_extension.start_watchdog(core)
            neutral_momentum_starter_extension.register_routes(core.app, core)
            neutral_late_session_participation.start_watchdog(core)
            neutral_late_session_participation.register_routes(core.app, core)
            paper_underdeployment_repair.start_watchdog(core)
            paper_underdeployment_repair.register_routes(core.app, core)

            paper_regime_adaptive_policy.start_watchdog(core)
            paper_regime_adaptive_policy.register_routes(core.app, core)

            performance_audit_lab.apply(core)
            performance_audit_lab.register_routes(core.app, core)
            try:
                performance_audit_lab.restriction_audit(core)
            except Exception:
                pass

            performance_audit_lab_v2.apply(core)
            performance_audit_lab_v2.register_routes(core.app, core)

            performance_audit_composition_guard.start_watchdog(core)
            performance_audit_composition_guard.register_routes(core.app, core)
            diagnostics.register_routes(core.app, core)

            # Final run_cycle owner: attach the observer only after every startup
            # component has completed its callable composition. The completion
            # contract remains immediately below this final observer.
            run_report_guard_apply = run_report_guard.apply(core)
            run_report_guard.register_routes(core.app, core)
            if run_report_guard_apply.get("status") != "ok":
                raise RuntimeError(
                    "final run-cycle observer failed to install: "
                    + str(run_report_guard_apply)
                )

            # Configure bounded research-evidence persistence and its read-only
            # route before the disabled-by-default reviewer is installed.  This
            # store is not portfolio state or canonical execution evidence.
            shadow_ai_observability_result = shadow_ai_observability.install(core.app)
            shadow_ai_reviewer = shadow_ai_adversarial_reviewer.install()

            # Register the sentinel as an on-demand read-only route. It starts
            # no worker and is not part of the execution or cycle path.
            system_sentinel_result = system_sentinel_runtime.install(core.app, core)

            auto_runner = _start_auto_runner(core)
            if auto_runner.get("status") != "ok":
                raise RuntimeError(
                    "auto runner failed to start after runtime composition: "
                    + str(auto_runner.get("reason") or auto_runner)
                )

            versions = [
                state_persistence_contract.VERSION,
                provider_timeout_contract.VERSION,
                cycle_completion_contract.VERSION,
                daily_audit_repair_overlay.VERSION,
                paper_underdeployment_time_guard.VERSION,
                performance_risk_activation_guard.VERSION,
                regime_integrity_underdeployment.VERSION,
                regime_integrity_cache_guard.VERSION,
                bear_soft_pause_short_recovery.VERSION,
                bear_recovery_stack_contract.VERSION,
                entry_pipeline_xray_bear_ownership_guard.VERSION,
                opening_surge_participation.VERSION,
                opening_surge_score_calibration.VERSION,
                breakout_scanner_ownership_guard.VERSION,
                scanner_runtime_contract.VERSION,
                neutral_momentum_starter_extension.VERSION,
                neutral_late_session_participation.VERSION,
                paper_underdeployment_repair.VERSION,
                paper_regime_adaptive_policy.VERSION,
                performance_audit_lab.VERSION,
                performance_audit_lab_v2.VERSION,
                performance_audit_composition_guard.VERSION,
                run_report_guard.VERSION,
                shadow_ai_adversarial_reviewer.VERSION,
                shadow_ai_evidence_store.VERSION,
                shadow_ai_observability.VERSION,
                system_sentinel_runtime.VERSION,
            ]
            _REGISTERED_CORE_IDS.add(id(core))
            _LAST = {
                "status": "ok",
                "overall": "pass",
                "version": VERSION,
                "registered_local": _now(),
                "research_isolated": research_isolated,
                "component_versions": versions,
                "state_persistence_contract": state_result,
                "provider_timeout_contract": provider_result,
                "cycle_completion_contract": cycle_result,
                "daily_audit_repair_overlay": daily_overlay_result,
                "paper_underdeployment_time_guard": entry_time_guard_result,
                "run_cycle_observer": run_report_guard_apply,
                "shadow_ai_adversarial_reviewer": shadow_ai_reviewer,
                "shadow_ai_observability": shadow_ai_observability_result,
                "system_sentinel_runtime": system_sentinel_result,
                "auto_runner": auto_runner,
            }
            diagnostics.record_module_event(
                "runtime_worker_registration",
                "registered",
                error=(
                    f"research_isolated={research_isolated};"
                    + ";".join(versions)
                    + ";state_provider_cycle_contracts_before_runner"
                    + ";entry_time_guard_before_runner"
                    + ";final_run_cycle_observer_installed"
                    + ";auto_runner_started_after_composition"
                ),
            )
            return dict(_LAST)
        except Exception as exc:
            _LAST = {
                "status": "error",
                "overall": "warn",
                "version": VERSION,
                "failed_local": _now(),
                "research_isolated": research_isolated,
                "error": f"{type(exc).__name__}: {exc}",
            }
            diagnostics.record_exception(
                exc,
                source="runtime_worker_registration.register",
                module="app",
            )
            return dict(_LAST)


def status() -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "runtime_worker_registration_status",
        "version": VERSION,
        "registered_core_count": len(_REGISTERED_CORE_IDS),
        "last": dict(_LAST),
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "starts_existing_auto_runner": True,
            "adds_new_runner_type": False,
            "synchronizes_diagnostic_state_only": True,
            "defers_first_cycle_until_composition": True,
            "final_run_cycle_observer_owner": "run_report_guard",
            "cycle_completion_owner_below_observer": "cycle_completion_contract",
            "entry_time_guard_installed_before_runner": True,
        },
    }
