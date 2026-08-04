"""Explicit idempotent registration for the paper-trading web worker.

This module consolidates the former Gunicorn ``post_worker_init`` registration
block. It is called after the legacy Flask application has finished importing.
It does not change signal formulas, thresholds, sizing, risk limits, order
placement, live authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import threading
from typing import Any, Dict

import runtime_diagnostics as diagnostics

VERSION = "runtime-worker-registration-2026-08-04-v3-auto-runner-state-sync"
_LOCK = threading.RLock()
_REGISTERED_CORE_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _start_auto_runner(core: Any) -> Dict[str, Any]:
    """Start the existing app-owned loop and synchronize its diagnostic state."""
    ensure = getattr(core, "ensure_auto_thread", None)
    if not callable(ensure):
        return {
            "status": "error",
            "started": False,
            "reason": "ensure_auto_thread_missing",
        }
    ensure()
    portfolio = getattr(core, "portfolio", {})
    auto = portfolio.get("auto_runner", {}) if isinstance(portfolio, dict) else {}
    global_started = bool(getattr(core, "AUTO_THREAD_STARTED", False))
    reported_before_sync = bool(auto.get("thread_started")) if isinstance(auto, dict) else False

    # Older persisted state can retain thread_started=false even when the app's
    # authoritative process-global owner is already active. Synchronize only
    # this diagnostic field; no thread, strategy, risk, or execution behavior
    # is changed here.
    diagnostic_state_synchronized = False
    if global_started and isinstance(auto, dict) and not reported_before_sync:
        auto["thread_started"] = True
        auto["thread_start_owner"] = "runtime_worker_registration"
        auto["thread_state_synchronized_local"] = _now()
        diagnostic_state_synchronized = True

    reported = bool(auto.get("thread_started")) if isinstance(auto, dict) else False
    started = bool(reported or global_started)
    return {
        "status": "ok" if started else "error",
        "started": started,
        "reported_thread_started": reported,
        "reported_before_sync": reported_before_sync,
        "global_thread_started": global_started,
        "diagnostic_state_synchronized": diagnostic_state_synchronized,
        "enabled": auto.get("enabled") if isinstance(auto, dict) else None,
        "interval_seconds": auto.get("interval_seconds") if isinstance(auto, dict) else None,
        "owner": "app.ensure_auto_thread",
        "ordering": "after_runtime_composition",
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
            import run_report_guard
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
            import paper_regime_adaptive_policy
            import performance_audit_lab
            import performance_audit_lab_v2
            import performance_audit_composition_guard

            if research_isolated:
                performance_audit_lab.AUTO_BACKTEST = False
                performance_audit_lab_v2.AUTO_BACKTEST = False
                performance_audit_lab_v2.ENABLED = False

            run_report_guard.apply(core)
            run_report_guard.register_routes(core.app, core)
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

            auto_runner = _start_auto_runner(core)
            if auto_runner.get("status") != "ok":
                raise RuntimeError(
                    "auto runner failed to start after runtime composition: "
                    + str(auto_runner.get("reason") or auto_runner)
                )

            versions = [
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
            ]
            _REGISTERED_CORE_IDS.add(id(core))
            _LAST = {
                "status": "ok",
                "overall": "pass",
                "version": VERSION,
                "registered_local": _now(),
                "research_isolated": research_isolated,
                "component_versions": versions,
                "auto_runner": auto_runner,
            }
            diagnostics.record_module_event(
                "runtime_worker_registration",
                "registered",
                error=(
                    f"research_isolated={research_isolated};"
                    + ";".join(versions)
                    + ";auto_historical_research_disabled"
                    + ";auto_runner_started_after_composition"
                    + ";auto_runner_diagnostic_state_synchronized"
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
        },
    }
