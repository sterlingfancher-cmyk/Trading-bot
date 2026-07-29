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

        run_report_guard.apply(core)
        run_report_guard.register_routes(core.app, core)
        regime_integrity_underdeployment.start_watchdog(core)
        regime_integrity_underdeployment.register_routes(core.app, core)
        regime_integrity_cache_guard.start_watchdog(core)
        performance_risk_activation_guard.start_watchdog(core)
        performance_risk_activation_guard.register_routes(core.app, core)
        diagnostics.register_routes(core.app, core)
        diagnostics.record_module_event(
            "gunicorn.worker",
            "diagnostics_risk_and_regime_integrity_registered",
            error=(
                f"{performance_risk_activation_guard.VERSION};"
                f"{regime_integrity_underdeployment.VERSION};"
                f"{regime_integrity_cache_guard.VERSION}"
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
