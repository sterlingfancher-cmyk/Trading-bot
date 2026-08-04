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

VERSION = "runtime-worker-registration-2026-08-03-v1"
_LOCK = threading.RLock()
_REGISTERED_CORE_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
            return {
                "status": "ok",
                "overall": "pass",
                "version": VERSION,
                "already_registered": True,
                "research_isolated": research_isolated,
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
            }
            diagnostics.record_module_event(
                "runtime_worker_registration",
                "registered",
                error=(
                    f"research_isolated={research_isolated};"
                    + ";".join(versions)
                    + ";auto_historical_research_disabled"
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
        },
    }
