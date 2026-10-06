#!/usr/bin/env python3
"""Build a read-only Stage F review artifact from one settled runtime capture.

The input collector performs GET requests only. This builder uses a temporary
StateStore sandbox to prove rollback lineage and writes review artifacts only;
it never imports the trading application or touches production state.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

from trading.canary import (
    AUTHORITATIVE_RUNTIME_URL,
    CanaryEvidence,
    CanaryInvariantError,
    CanaryReadinessPlanner,
    CutoverDecisionReviewContract,
    CutoverPreflightEvidenceBundle,
)
from trading.state_store import CanonicalStateStore
from governed_v5_restart_contract import (
    ACTIVATION_DECISION_ID,
    ACTIVATION_REVIEW_REFERENCE,
    TARGET_EPOCH_ID,
    VERSION as GOVERNED_RESTART_VERSION,
)

VERSION = "cutover-preflight-ci-artifact-2026-10-06-v3-forward-execution"
EXPECTED_PRESTART_LEDGER_ROWS = 88
EXPECTED_PRESTART_LEDGER_SHA256 = (
    "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
)
EXPECTED_RUNTIME_ENDPOINT_COUNT = 13
EXPECTED_ABORT_RECOVERY_VERSION = (
    "governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor"
)
EXPECTED_ABORT_RECOVERY_MODE = "pr282_failed_recovery_successor"
EXPECTED_INCIDENT_EVIDENCE_REFERENCE = "issue-84-comment-5897148822"


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if value is None:
        raise CanaryInvariantError(f"{name} is required")
    if not isinstance(value, Mapping):
        raise CanaryInvariantError(f"{name} must be a mapping")
    return value


def _runtime_payload(snapshot: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    raw = _mapping(snapshot.get("raw"), name="runtime_snapshot.raw")
    row = _mapping(raw.get(name), name=f"runtime_snapshot.raw.{name}")
    if row.get("status") != "ok":
        raise CanaryInvariantError(f"runtime endpoint unavailable: {name}")
    return _mapping(row.get("payload"), name=f"runtime_snapshot.raw.{name}.payload")


def _require_settled_snapshot(
    snapshot: Mapping[str, Any], *, deployed_commit_sha: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if snapshot.get("read_only") is not True:
        raise CanaryInvariantError("runtime snapshot must be explicitly read-only")
    if str(snapshot.get("base_url") or "").rstrip("/") != AUTHORITATIVE_RUNTIME_URL:
        raise CanaryInvariantError("runtime snapshot source is not authoritative")
    summary = _mapping(snapshot.get("summary"), name="runtime_snapshot.summary")
    connectivity = _mapping(
        summary.get("connectivity"), name="runtime_snapshot.summary.connectivity"
    )
    if (
        connectivity.get("reachable_count") != connectivity.get("total_count")
        or connectivity.get("total_count") != EXPECTED_RUNTIME_ENDPOINT_COUNT
        or connectivity.get("classification_failed_endpoints") != []
        or connectivity.get("application_ready") is not True
    ):
        raise CanaryInvariantError("runtime snapshot is incomplete or unsettled")

    daily_audit = _runtime_payload(snapshot, "daily_audit")
    paper_status = _runtime_payload(snapshot, "paper_status")
    fresh_day = _runtime_payload(snapshot, "fresh_day_check")
    sentinel = _runtime_payload(snapshot, "system_sentinel")
    exact_commit = str(deployed_commit_sha or "").lower().strip()
    if (
        sentinel.get("overall") != "pass"
        or sentinel.get("status") != "quiet"
        or sentinel.get("incident_count") != 0
        or sentinel.get("collection_errors") not in ({}, None)
        or str(sentinel.get("generated_commit_sha") or "").lower().strip()
        != exact_commit
    ):
        raise CanaryInvariantError("sentinel did not prove the exact settled commit")
    return daily_audit, paper_status, fresh_day


def _canary_evidence(
    daily_audit: Mapping[str, Any], fresh_day: Mapping[str, Any]
) -> CanaryEvidence:
    accounting = _mapping(
        daily_audit.get("accounting_integrity"), name="daily_audit.accounting_integrity"
    )
    ledger = _mapping(
        daily_audit.get("execution_ledger"), name="daily_audit.execution_ledger"
    )
    account = _mapping(daily_audit.get("account"), name="daily_audit.account")
    clean_accounting = bool(
        accounting.get("status") in ("ok", "pass")
        and accounting.get("coverage_complete") is True
        and accounting.get("coverage_issue_count") == 0
        and accounting.get("economic_issue_count") == 0
    )
    protected_valuation = bool(
        account.get("positions") in ({}, [], ())
        and float(account.get("cash") or 0.0) > 0.0
        and float(account.get("equity") or 0.0) > 0.0
    )
    return CanaryEvidence(
        issue_82_fresh_risk_day_pass=fresh_day.get("baseline_status") == "pass",
        issue_82_forward_session_pass=False,
        clean_active_accounting_audit=clean_accounting,
        canonical_ledger_chain_valid=ledger.get("chain_valid") is True,
        protected_valuation_sane=protected_valuation,
        stage_b_valuation_parity=False,
        stage_c_risk_parity=False,
        stage_d_restart_parity=False,
        stage_e_accounting_parity=False,
        single_revision_snapshot_binding=True,
        repository_validation_green=False,
        architecture_debt_gate_green=False,
        refactor_startup_audit_green=False,
    )


def _artifact_sha256(row: Mapping[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _governed_restart_status(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    return _runtime_payload(snapshot, "governed_v5_restart")


def _position_symbols(value: Any, *, name: str) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        symbols = value.keys()
    elif isinstance(value, (list, tuple, set)):
        symbols = value
    else:
        raise CanaryInvariantError(f"{name} must identify open-position symbols")
    return {str(symbol) for symbol in symbols}


def _build_post_start_acceptance(
    *,
    runtime_snapshot: Mapping[str, Any],
    daily_audit: Mapping[str, Any],
    paper_status: Mapping[str, Any],
    fresh_day: Mapping[str, Any],
    deployed_commit_sha: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    epoch = _mapping(daily_audit.get("accounting_epoch"), name="accounting_epoch")
    ledger = _mapping(daily_audit.get("execution_ledger"), name="execution_ledger")
    accounting = _mapping(
        daily_audit.get("accounting_integrity"), name="accounting_integrity"
    )
    account = _mapping(daily_audit.get("account"), name="account")
    risk = _mapping(daily_audit.get("risk"), name="risk")
    governed = _governed_restart_status(runtime_snapshot)
    recovery = _mapping(
        governed.get("preappend_abort_recovery"),
        name="governed_v5_restart.preappend_abort_recovery",
    )
    current_epoch_rows = ledger.get("current_epoch_rows")
    ledger_rows = ledger.get("row_count")
    accounting_symbols = _position_symbols(
        accounting.get("reconstructed_open_positions"),
        name="accounting_integrity.reconstructed_open_positions",
    )
    account_symbols = _position_symbols(
        account.get("positions"), name="account.positions"
    )
    paper_symbols = _position_symbols(
        paper_status.get("positions"), name="paper_status.positions"
    )
    last_execution_receipt = governed.get("last_execution_receipt")
    if last_execution_receipt is not None:
        last_execution_receipt = _mapping(
            last_execution_receipt,
            name="governed_v5_restart.last_execution_receipt",
        )

    checks = {
        "daily_audit_pass": daily_audit.get("overall") == "pass",
        "exact_epoch": epoch.get("epoch_id") == TARGET_EPOCH_ID,
        "validation_hold_released": (
            epoch.get("validation_hold") is False
            and epoch.get("validation_released") is True
        ),
        "prior_evidence_preserved": (
            epoch.get("historical_evidence_archived") is True
            and epoch.get("zero_trade_baseline") is True
        ),
        "canonical_ledger_forward_progress_valid": (
            isinstance(ledger_rows, int)
            and not isinstance(ledger_rows, bool)
            and isinstance(current_epoch_rows, int)
            and not isinstance(current_epoch_rows, bool)
            and ledger_rows >= EXPECTED_PRESTART_LEDGER_ROWS
            and current_epoch_rows >= 0
            and ledger_rows - EXPECTED_PRESTART_LEDGER_ROWS == current_epoch_rows
            and isinstance(ledger.get("ledger_sha256"), str)
            and len(ledger.get("ledger_sha256")) == 64
            and ledger.get("current_epoch_id") == TARGET_EPOCH_ID
            and ledger.get("state_current_epoch_rows") == current_epoch_rows
            and ledger.get("chain_valid") is True
            and ledger.get("state_projection_parity") is True
            and ledger.get("missing_from_state_count") == 0
            and ledger.get("missing_from_ledger_count") == 0
        ),
        "prestart_ledger_baseline_preserved": (
            recovery.get("canonical_row_count") == EXPECTED_PRESTART_LEDGER_ROWS
            and recovery.get("canonical_ledger_sha256")
            == EXPECTED_PRESTART_LEDGER_SHA256
        ),
        "accounting_clean_and_reconciled": (
            accounting.get("status") in ("ok", "pass")
            and accounting.get("coverage_complete") is True
            and accounting.get("coverage_issue_count") == 0
            and accounting.get("economic_issue_count") == 0
            and accounting.get("parsed_trade_rows") == current_epoch_rows
            and accounting_symbols == account_symbols == paper_symbols
            and float(account.get("cash") or 0.0) > 0.0
            and float(account.get("equity") or 0.0) > 0.0
        ),
        "latest_execution_receipt_matches_ledger": (
            (current_epoch_rows == 0 and last_execution_receipt is None)
            or (
                current_epoch_rows > 0
                and last_execution_receipt is not None
                and last_execution_receipt.get("canonical_row_count") == ledger_rows
                and bool(last_execution_receipt.get("canonical_last_execution_id"))
                and bool(last_execution_receipt.get("intent_id"))
                and last_execution_receipt.get("operation") in ("entry", "exit")
            )
        ),
        "risk_halt_released": (
            risk.get("halted") is False
            and fresh_day.get("halted") is False
        ),
        "governed_restart_active": (
            governed.get("version") == GOVERNED_RESTART_VERSION
            and governed.get("decision_id") == ACTIVATION_DECISION_ID
            and governed.get("review_reference") == ACTIVATION_REVIEW_REFERENCE
            and governed.get("epoch_id") == TARGET_EPOCH_ID
            and governed.get("status") == "active"
            and governed.get("overall") == "pass"
            and governed.get("paper_execution_enabled") is True
            and governed.get("validation_hold") is False
            and governed.get("risk_halted") is False
            and governed.get("post_start_forward_observations_required") is True
        ),
        "exact_preappend_abort_recovery": (
            recovery.get("status") == "recovered"
            and recovery.get("overall") == "pass"
            and recovery.get("version") == EXPECTED_ABORT_RECOVERY_VERSION
            and recovery.get("recovery_mode") == EXPECTED_ABORT_RECOVERY_MODE
            and recovery.get("incident_evidence_reference")
            == EXPECTED_INCIDENT_EVIDENCE_REFERENCE
            and recovery.get("historical_discrepancy_preserved") is True
            and recovery.get("historical_discrepancy_rewritten") is False
            and all(_mapping(recovery.get("checks"), name="recovery.checks").values())
        ),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    if failures:
        raise CanaryInvariantError(
            "governed restart post-start evidence blocked: " + ", ".join(failures)
        )

    evidence = {
        "artifact_version": VERSION,
        "artifact_kind": "governed_restart_post_start_acceptance_evidence",
        "production_authority": False,
        "read_only": True,
        "deployed_commit_sha": str(deployed_commit_sha),
        "source_url": AUTHORITATIVE_RUNTIME_URL,
        "captured_at": str(daily_audit.get("generated_local") or ""),
        "epoch_id": TARGET_EPOCH_ID,
        "prestart_ledger_row_count": EXPECTED_PRESTART_LEDGER_ROWS,
        "prestart_ledger_sha256": EXPECTED_PRESTART_LEDGER_SHA256,
        "ledger_row_count": ledger_rows,
        "ledger_sha256": str(ledger.get("ledger_sha256") or ""),
        "current_epoch_rows": current_epoch_rows,
        "checks": checks,
        "governed_status": dict(governed),
    }
    evidence = {**evidence, "acceptance_sha256": _artifact_sha256(evidence)}
    result = {
        "artifact_version": VERSION,
        "artifact_kind": "governed_restart_post_start_acceptance_result",
        "production_authority": False,
        "activation_performed_by_builder": False,
        "activation_observed": True,
        "state": "active_pending_forward_observations",
        "review_status": "post_start_baseline_observed",
        "post_start_forward_observations_required": True,
        "blockers": ["post_start_forward_observations"],
        "evidence_sha256": evidence["acceptance_sha256"],
    }
    result = {**result, "decision_sha256": _artifact_sha256(result)}
    return evidence, result


def build_artifacts(
    *,
    runtime_snapshot: Mapping[str, Any],
    deployed_commit_sha: str,
    splendid_deployment_settled: bool,
    projection_revision: int = 1,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if splendid_deployment_settled is not True:
        raise CanaryInvariantError("Splendid deployment must be explicitly settled")
    if (
        isinstance(projection_revision, bool)
        or not isinstance(projection_revision, int)
        or projection_revision <= 0
    ):
        raise CanaryInvariantError("projection revision must be a positive integer")
    daily_audit, paper_status, fresh_day = _require_settled_snapshot(
        runtime_snapshot, deployed_commit_sha=deployed_commit_sha
    )
    epoch = _mapping(daily_audit.get("accounting_epoch"), name="accounting_epoch")
    if epoch.get("validation_hold") is False:
        return _build_post_start_acceptance(
            runtime_snapshot=runtime_snapshot,
            daily_audit=daily_audit,
            paper_status=paper_status,
            fresh_day=fresh_day,
            deployed_commit_sha=deployed_commit_sha,
        )
    ledger = _mapping(
        daily_audit.get("execution_ledger"), name="daily_audit.execution_ledger"
    )
    captured_at = str(daily_audit.get("generated_local") or "").strip()
    binding = CanaryReadinessPlanner.bind_verified_flat_v5_runtime_evidence(
        daily_audit=daily_audit,
        paper_status=paper_status,
        fresh_day=fresh_day,
        ledger_sha256=str(ledger.get("ledger_sha256") or ""),
        revision=projection_revision,
        captured_at=captured_at,
        source_url=AUTHORITATIVE_RUNTIME_URL,
    )

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "canonical-state.json"
        archive_path = Path(tmp) / "rollback-baseline.json"
        store = CanonicalStateStore(state_path, sandbox_io_enabled=True)
        store.commit_sandbox(binding.envelope)
        baseline = binding.envelope.snapshot()
        canary = replace(
            baseline,
            portfolio=replace(
                baseline.portfolio,
                cash=baseline.portfolio.cash - 1.0,
                equity=baseline.portfolio.equity - 1.0,
            ),
        )
        receipt = store.run_rollback_drill_sandbox(
            archive_path,
            canary_envelope=store.prepare(
                snapshot=canary,
                revision=projection_revision + 1,
                created_at=f"{captured_at} sandbox-canary",
            ),
            restored_created_at=f"{captured_at} sandbox-restore",
        )

    bundle = CutoverPreflightEvidenceBundle.build(
        daily_audit=daily_audit,
        paper_status=paper_status,
        fresh_day=fresh_day,
        ledger_sha256=str(ledger.get("ledger_sha256") or ""),
        revision=projection_revision,
        captured_at=captured_at,
        source_url=AUTHORITATIVE_RUNTIME_URL,
        canary_evidence=_canary_evidence(daily_audit, fresh_day),
        requested_fraction=0.01,
        rollback_receipt=receipt,
        deployed_commit_sha=deployed_commit_sha,
        sentinel_commit_sha=deployed_commit_sha,
        splendid_deployment_settled=True,
    )
    decision = CutoverDecisionReviewContract.from_evidence_bundle(bundle)
    bundle_row = {
        "artifact_version": VERSION,
        "artifact_kind": "cutover_preflight_evidence_bundle",
        "production_authority": False,
        "projection_revision_is_shadow_only": True,
        **dict(bundle.to_dict()),
    }
    decision_row = {
        "artifact_version": VERSION,
        "artifact_kind": "cutover_decision_review_contract",
        "production_authority": False,
        **dict(decision.to_dict()),
    }
    return bundle_row, decision_row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-snapshot", required=True)
    parser.add_argument("--deployed-commit", required=True)
    parser.add_argument("--splendid-deployment-settled", action="store_true")
    parser.add_argument("--projection-revision", type=int, default=1)
    parser.add_argument("--bundle-output", required=True)
    parser.add_argument("--decision-output", required=True)
    args = parser.parse_args()

    snapshot = json.loads(Path(args.runtime_snapshot).read_text(encoding="utf-8"))
    bundle, decision = build_artifacts(
        runtime_snapshot=_mapping(snapshot, name="runtime_snapshot"),
        deployed_commit_sha=args.deployed_commit,
        splendid_deployment_settled=args.splendid_deployment_settled,
        projection_revision=args.projection_revision,
    )
    Path(args.bundle_output).write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.decision_output).write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "bundle_sha256": bundle.get("bundle_sha256")
                or bundle.get("acceptance_sha256"),
                "decision_sha256": decision["decision_sha256"],
                "state": decision["state"],
                "blockers": decision["blockers"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
