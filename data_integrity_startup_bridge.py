"""Deterministic startup bridge for data-integrity runtime modules.

Imported by the WSGI entry point. This module applies bounded integrity and
observability modules and registers their status routes. The paper-accounting
guard is allowed to reconcile paper state from the execution ledger. The one-time
clean-accounting-epoch module is the explicitly authorized 2026-08-10 migration
after historical journal recovery was proven incomplete.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "data-integrity-startup-bridge-2026-08-21-v32-sls-recovery-proof"
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
    "clean_epoch_successor_compatibility",
    "clean_accounting_epoch",
    "paper_bidirectional_accounting_guard",
    "paper_execution_timestamp_semantics",
    # Small marker/archive forensic probe. It deliberately runs before the
    # one-shot recovery module and does not import/call recovery implementations.
    "verified_snapshot_provenance_status",
    # Backup/snapshot provenance probe. Its apply() is constant-time and never
    # scans backups during startup; scanning occurs only on its explicit route.
    "verified_snapshot_backup_provenance_status",
    # Trade-journal/canonical-ledger provenance probe. Its apply() is also
    # constant-time; journal/ledger reads occur only on its explicit route.
    "verified_snapshot_journal_ledger_provenance_status",
    # Current-day risk-peak provenance probe. Its apply() is constant-time and
    # reads in-process history/reports only when its explicit route is requested.
    "day_peak_provenance_status",
    # Exact SLS bad-execution counterfactual. Startup apply() is constant-time;
    # the canonical ledger is read only when the explicit proof route is called.
    "sls_bad_execution_recovery_proof",
    # Patch the exact one-shot recovery's journal rotation before the recovery
    # runs. The migration already owns the journal lock, so it must not call the
    # journal mirror recursively from inside that critical section.
    "verified_snapshot_epoch_recovery_lock_safety",
    # Exact-signature one-time recovery for the proven 2026-08-12 bad-tick
    # incident. It archives the contaminated epoch and starts a verified snapshot
    # epoch under a validation hold; it is not a generic loss reset.
    "verified_snapshot_epoch_recovery",
    # Final accounting adapter so the new epoch can begin from verified cash plus
    # the restored open LRCX lot and all future executions remain canonical.
    "verified_snapshot_accounting_baseline",
    # Issue #82 fresh-day gate: never initialize a new risk day from a
    # non-finite/non-positive persisted valuation. This guard is prospective and
    # never rewrites an already-initialized current day.
    "fresh_risk_day_baseline_guard",
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
