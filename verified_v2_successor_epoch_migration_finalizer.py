"""Final startup consistency gate for the Issue #82 v2->v3 successor cutover.

Production evidence on 2026-08-25 proved that the bounded successor migration can
complete successfully and then be followed by a stale v2 state restore during
later startup registration. The immutable ledger remained unchanged and the
completed migration marker remained durable, but the active in-memory/on-disk
accounting epoch no longer matched that marker.

This finalizer runs last in the data-integrity startup bridge. It does nothing
when v3 is already active. It may retry the already-authorized cutover only for
one exact interrupted-completion shape: the durable completed v3 marker exists,
the active epoch has reverted specifically to verified v2, the consolidated
11-signature recovery gate is still fully ready, and the active accounting window
still contains only the exact proven TEM duplicate issue. The existing cutover
then re-archives the current verified state and re-verifies that canonical ledger
bytes are unchanged.

Status reads are strictly observational. Only startup composition calls apply().
No historical ledger row is edited/deleted/relabelled. No halt or day peak is
cleared or rewritten, and no strategy, sizing, threshold, live, ML, or order
authority is changed.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "verified-v2-successor-epoch-finalizer-2026-08-25-v2-readonly-status"
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _epoch_id(migration: Any, core: Any) -> str:
    pf = migration._portfolio(core)
    epoch = migration._d(pf.get("paper_accounting_epoch"))
    return str(epoch.get("id") or pf.get("accounting_epoch_id") or "")


def _active_result(migration: Any, core: Any, *, retried: bool) -> Dict[str, Any]:
    pf = migration._portfolio(core)
    epoch = migration._d(pf.get("paper_accounting_epoch"))
    marker = migration._marker()
    return {
        "status": "validation_hold",
        "overall": "pass",
        "version": VERSION,
        "active_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "completed_marker_present": marker.get("status") == "completed",
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)),
        "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
        "validation_hold": bool(epoch.get("validation_hold", False)),
        "state_trade_rows": len(migration._l(pf.get("trades"))),
        "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged", False)),
        "interrupted_completion_retry_performed": retried,
    }


def _observed_status(migration: Any, core: Any = None) -> Dict[str, Any]:
    if core is None:
        return dict(_LAST) if _LAST else {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "runtime_missing",
        }

    active_epoch = _epoch_id(migration, core)
    marker = migration._marker()
    pf = migration._portfolio(core)
    epoch = migration._d(pf.get("paper_accounting_epoch"))
    if active_epoch == migration.TARGET_EPOCH_ID:
        return {
            "status": "validation_hold",
            "overall": "pass",
            "version": VERSION,
            "active_epoch_id": active_epoch,
            "prior_epoch_id": migration.OLD_EPOCH_ID,
            "completed_marker_present": marker.get("status") == "completed",
            "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)),
            "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
            "validation_hold": bool(epoch.get("validation_hold", False)),
            "state_trade_rows": len(migration._l(pf.get("trades"))),
            "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged", False)),
            "interrupted_completion_retry_performed": bool(_LAST.get("interrupted_completion_retry_performed", False)),
        }

    return {
        "status": _LAST.get("status", "blocked"),
        "overall": _LAST.get("overall", "warn"),
        "version": VERSION,
        "reason": _LAST.get("reason", "successor_finalizer_not_active"),
        "active_epoch_id": active_epoch,
        "marker_status": marker.get("status"),
        "marker_target_epoch_id": marker.get("target_epoch_id"),
        "completed_marker_present": marker.get("status") == "completed",
        "interrupted_completion_retry_performed": bool(_LAST.get("interrupted_completion_retry_performed", False)),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    try:
        import verified_v2_successor_epoch_migration as migration
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not migration._paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}

    active_epoch = _epoch_id(migration, core)
    if active_epoch == migration.TARGET_EPOCH_ID:
        _LAST = _active_result(migration, core, retried=False)
        return dict(_LAST)

    marker = migration._marker()
    exact_interrupted_completion = bool(
        marker.get("status") == "completed"
        and str(marker.get("target_epoch_id") or "") == migration.TARGET_EPOCH_ID
        and str(marker.get("prior_epoch_id") or "") == migration.OLD_EPOCH_ID
        and marker.get("canonical_ledger_unchanged") is True
        and active_epoch == migration.OLD_EPOCH_ID
    )
    if not exact_interrupted_completion:
        _LAST = {
            "status": "blocked",
            "overall": "warn",
            "version": VERSION,
            "reason": "successor_finalizer_not_applicable",
            "active_epoch_id": active_epoch,
            "marker_status": marker.get("status"),
            "marker_target_epoch_id": marker.get("target_epoch_id"),
            "interrupted_completion_retry_performed": False,
        }
        return dict(_LAST)

    gate, gate_ready = migration._gate_evidence(core)
    accounting, accounting_ready = migration._active_accounting_evidence(core)
    pf = migration._portfolio(core)
    positions = migration._verified_positions(pf)
    state_snapshot_ready = bool(
        migration._f(pf.get("cash"))
        and migration._f(pf.get("equity"))
        and (not migration._d(pf.get("positions")) or positions)
    )
    if not gate_ready or not accounting_ready or not state_snapshot_ready:
        _LAST = {
            "status": "blocked",
            "overall": "fail",
            "version": VERSION,
            "reason": "interrupted_successor_retry_preconditions_not_met",
            "active_epoch_id": active_epoch,
            "preconditions": {
                "completed_marker_exact": True,
                "active_epoch_reverted_exactly_to_verified_v2": True,
                "consolidated_recovery_gate_ready": gate_ready,
                "active_accounting_only_known_tem_issue": accounting_ready,
                "current_state_snapshot_sane": state_snapshot_ready,
            },
            "gate_diagnosis": gate.get("diagnosis"),
            "known_invalid_execution_count": gate.get("known_invalid_execution_count"),
            "accounting_coverage_issue_count": accounting.get("coverage_issue_count"),
            "accounting_economic_issue_count": accounting.get("economic_issue_count"),
            "interrupted_completion_retry_performed": False,
        }
        return dict(_LAST)

    try:
        retry = migration._cutover(core, gate, accounting)
    except Exception as exc:
        _LAST = {
            "status": "error",
            "overall": "fail",
            "version": VERSION,
            "reason": "interrupted_successor_retry_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "interrupted_completion_retry_performed": True,
        }
        return dict(_LAST)

    if _epoch_id(migration, core) != migration.TARGET_EPOCH_ID:
        _LAST = {
            "status": "error",
            "overall": "fail",
            "version": VERSION,
            "reason": "retry_returned_without_successor_epoch_active",
            "retry": retry,
            "interrupted_completion_retry_performed": True,
        }
        return dict(_LAST)

    _LAST = _active_result(migration, core, retried=True)
    _LAST["retry_completed_local"] = retry.get("completed_local")
    return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    try:
        import verified_v2_successor_epoch_migration as migration
        result = _observed_status(migration, core)
    except Exception as exc:
        result = {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}
    return {
        **result,
        "type": "verified_v2_successor_epoch_migration_finalizer_status",
        "status_reads_are_observational": True,
        "authority": {
            "paper_only": True,
            "retries_only_exact_completed_v3_marker_with_verified_v2_reversion": True,
            "preserves_current_cash_equity_positions_and_risk": True,
            "archives_evidence_before_retry": True,
            "status_reads_write_state": False,
            "edits_or_deletes_canonical_rows": False,
            "rotates_or_truncates_canonical_ledger": False,
            "rewrites_current_day_peak": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    # Startup composition is allowed to call apply(). The HTTP view below is not.
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        path = "/paper/verified-v2-successor-epoch-finalizer-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(path, "verified_v2_successor_epoch_finalizer_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
