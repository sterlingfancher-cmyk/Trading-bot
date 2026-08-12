"""Deterministic startup bridge for data-integrity runtime modules.

Imported by the WSGI entry point. This module applies bounded integrity and
observability modules and registers their status routes. The paper-accounting
guard is allowed to reconcile paper state from the execution ledger. The one-time
clean-accounting-epoch module is the explicitly authorized 2026-08-10 migration
after historical journal recovery was proven incomplete.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "data-integrity-startup-bridge-2026-08-12-v20-absolute-daily-halt-lifecycle"
MODULES = (
    # Registered first so Flask executes its after_request handler last.
    "final_daily_audit_compactor",
    # Reporting-only fallback for a scanner section that omits latest-cycle
    # entries_count even though auto_runner.last_result.entries is available.
    "daily_audit_entry_count_bridge",
    # Reporting-only integrity detail so one compact audit identifies the exact
    # persisted row/reason when accounting coverage fails.
    "daily_audit_accounting_issue_bridge",
    # Correctness-critical bootstrap. It installs canonical execution routing
    # plus final bidirectional/timestamp semantics before any reconciler runs.
    "stable_paper_accounting_bootstrap",
    # Stable Core execution truth: durable append-only hash-chained events.
    "canonical_execution_ledger",
    "market_surge_canonical_execution_bridge",
    "orla_hygiene_overlay",
    "paper_ledger_matched_exit_guard",
    "paper_trade_action_semantics_recovery",
    # Reconciliation now runs only after the bootstrap above has installed the
    # final clean-epoch event semantics.
    "paper_accounting_integrity_guard",
    "paper_accounting_readonly_status",
    "paper_ledger_economic_integrity",
    # Historical recovery evidence is evaluated before the one-time cutover.
    "paper_journal_forensic_recovery",
    # Disable the unnecessary nested journal mirror while the cutover owns locks.
    "clean_accounting_epoch_lock_safety",
    "clean_accounting_epoch",
    "paper_bidirectional_accounting_guard",
    "paper_execution_timestamp_semantics",
    # The absolute 3% daily-loss ceiling remains unchanged. This guard only lets
    # its stale persisted reason use the normal managed-halt recovery lifecycle
    # after the current metric has recovered below the ceiling.
    "absolute_daily_halt_lifecycle_guard",
    # A validation hold is an administrative execution block, not a loss event.
    "administrative_halt_classification_guard",
    # Re-verifies the deployed zero-trade baseline and clears only that exact
    # administrative hold. Any other risk halt remains untouched.
    "clean_epoch_validation_release",
    # All research/path layers run only after the accounting epoch is established.
    "intratrade_path_capture",
    "mae_mfe_integration",
    "daily_data_integrity_audit_overlay",
    "paper_accounting_audit_bridge",
    "post_recovery_evidence_epoch_guard",
    "provider_request_accounting_overlay",
    "daily_audit_response_reconciliation",
    "multi_asset_shadow_ranker",
)


def apply(core: Any = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for name in MODULES:
        try:
            module = __import__(name)
            fn = getattr(module, "apply", None)
            if callable(fn):
                try:
                    results[name] = fn(core)
                except TypeError:
                    results[name] = fn()
            else:
                results[name] = {"status": "no_apply"}
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "version": VERSION, "modules": results}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for name in MODULES:
        try:
            module = __import__(name)
            fn = getattr(module, "register_routes", None)
            if callable(fn):
                try:
                    results[name] = fn(flask_app, core)
                except TypeError:
                    results[name] = fn(flask_app)
            else:
                results[name] = {"status": "no_routes"}
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "version": VERSION, "modules": results}
