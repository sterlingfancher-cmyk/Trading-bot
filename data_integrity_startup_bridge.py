"""Deterministic startup bridge for data-integrity runtime modules.

Imported by the WSGI entry point. This module applies bounded integrity and
observability modules and registers their status routes. The paper-accounting
guard is allowed to reconcile paper state from the execution ledger. The one-time
clean-accounting-epoch module is the explicitly authorized 2026-08-10 migration
after historical journal recovery was proven incomplete.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "data-integrity-startup-bridge-2026-08-12-v24-verified-snapshot-recovery"
MODULES = (
    "final_daily_audit_compactor",
    "daily_audit_entry_count_bridge",
    "daily_audit_accounting_issue_bridge",
    "canonical_execution_ledger",
    "market_surge_canonical_execution_bridge",
    "market_surge_queue_canonical_execution_bridge",
    "paper_exit_price_integrity_guard",
    "orla_hygiene_overlay",
    "paper_ledger_matched_exit_guard",
    "paper_trade_action_semantics_recovery",
    "stable_paper_accounting_bootstrap",
    "paper_accounting_integrity_guard",
    "paper_accounting_readonly_status",
    "paper_ledger_economic_integrity",
    "paper_journal_forensic_recovery",
    "clean_accounting_epoch_lock_safety",
    "clean_accounting_epoch",
    "paper_bidirectional_accounting_guard",
    "paper_execution_timestamp_semantics",
    # Exact-signature one-time recovery for the proven 2026-08-12 bad-tick
    # incident. It archives the contaminated epoch and starts a verified snapshot
    # epoch under a validation hold; it is not a generic loss reset.
    "verified_snapshot_epoch_recovery",
    # Final accounting adapter so the new epoch can begin from verified cash plus
    # the restored open LRCX lot and all future executions remain canonical.
    "verified_snapshot_accounting_baseline",
    "absolute_daily_halt_lifecycle_guard",
    "administrative_halt_classification_guard",
    "clean_epoch_validation_release",
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
