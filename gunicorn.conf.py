"""Gunicorn configuration and bounded Railway lifecycle diagnostics."""
from __future__ import annotations

import os

import runtime_diagnostics as diagnostics

timeout = 120
workers = 1


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _isolate_heavy_research() -> bool:
    """Keep historical research out of the single production web worker."""
    if _truthy(os.environ.get("WEB_WORKER_ALLOW_HEAVY_RESEARCH")):
        return False
    os.environ["PERFORMANCE_AUDIT_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_ENABLED"] = "false"
    return True


RESEARCH_ISOLATED = _isolate_heavy_research()
DEFERRED_BOOTSTRAP = _truthy(os.environ.get("DEFERRED_WSGI_BOOTSTRAP"))


def on_starting(server):
    diagnostics.record_module_event(
        "gunicorn",
        "on_starting",
        error=(
            f"deferred_bootstrap={DEFERRED_BOOTSTRAP};"
            f"research_isolated={RESEARCH_ISOLATED}"
        ),
    )


def when_ready(server):
    diagnostics.record_module_event("gunicorn", "ready")


def post_fork(server, worker):
    diagnostics.record_module_event("gunicorn.worker", "forked")


def post_worker_init(worker):
    """Avoid importing the legacy app twice under the deferred dispatcher."""
    if DEFERRED_BOOTSTRAP:
        diagnostics.record_module_event(
            "gunicorn.worker",
            "deferred_registration_owned_by_bootstrap_wsgi",
            error=f"research_isolated={RESEARCH_ISOLATED}",
        )
        return

    try:
        import app as core
        import runtime_worker_registration

        result = runtime_worker_registration.register(
            core,
            research_isolated=RESEARCH_ISOLATED,
        )
        if result.get("status") != "ok":
            raise RuntimeError(
                "runtime registration failed: "
                + str(result.get("error") or result.get("reason"))
            )
    except Exception as exc:
        diagnostics.record_exception(
            exc,
            source="gunicorn.post_worker_init",
            module="app",
        )


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
        error=(
            f"pid={getattr(worker, 'pid', None)} "
            f"exitcode={getattr(worker, 'exitcode', None)}"
        ),
    )


def on_exit(server):
    diagnostics.record_module_event("gunicorn", "exited")
