"""Gunicorn configuration and persistent Railway diagnostics hooks."""
from __future__ import annotations

import runtime_diagnostics as diagnostics

timeout = 120
workers = 1


def on_starting(server):
    diagnostics.record_module_event("gunicorn", "on_starting")


def when_ready(server):
    diagnostics.record_module_event("gunicorn", "ready")


def post_fork(server, worker):
    diagnostics.record_module_event("gunicorn.worker", "forked")


def post_worker_init(worker):
    try:
        import app as core
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
        import performance_audit_lab

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
        performance_audit_lab.apply(core)
        performance_audit_lab.register_routes(core.app, core)
        diagnostics.register_routes(core.app, core)
        diagnostics.record_module_event(
            "gunicorn.worker",
            "diagnostics_risk_regime_bear_recovery_stack_xray_opening_surge_score_breakout_scanner_runtime_neutral_starter_late_neutral_underdeployment_and_performance_audit_registered",
            error=(
                f"{performance_risk_activation_guard.VERSION};"
                f"{regime_integrity_underdeployment.VERSION};"
                f"{regime_integrity_cache_guard.VERSION};"
                f"{bear_soft_pause_short_recovery.VERSION};"
                f"{bear_recovery_stack_contract.VERSION};"
                f"{entry_pipeline_xray_bear_ownership_guard.VERSION};"
                f"{opening_surge_participation.VERSION};"
                f"{opening_surge_score_calibration.VERSION};"
                f"{breakout_scanner_ownership_guard.VERSION};"
                f"{scanner_runtime_contract.VERSION};"
                f"{neutral_momentum_starter_extension.VERSION};"
                f"{neutral_late_session_participation.VERSION};"
                f"{paper_underdeployment_repair.VERSION};"
                f"{performance_audit_lab.VERSION}"
            ),
        )
    except Exception as exc:
        diagnostics.record_exception(exc, source="gunicorn.post_worker_init", module="app")


def worker_abort(worker):
    diagnostics.record_exception(
        RuntimeError("gunicorn worker aborted"),
        source="gunicorn.worker_abort",
        module="gunicorn",
        context={"pid": getattr(worker, "pid", None)},
    )


def worker_exit(server, worker):
    diagnostics.record_module_event(
        "gunicorn.worker",
        "exited",
        error=f"pid={getattr(worker, 'pid', None)} exitcode={getattr(worker, 'exitcode', None)}",
    )


def on_exit(server):
    diagnostics.record_module_event("gunicorn", "exited")
