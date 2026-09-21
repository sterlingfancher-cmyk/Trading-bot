#!/usr/bin/env python3
"""Build a read-only Stage F review artifact from one settled runtime capture.

The input collector performs GET requests only. This builder uses a temporary
StateStore sandbox to prove rollback lineage and writes review artifacts only;
it never imports the trading application or touches production state.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
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

VERSION = "cutover-preflight-ci-artifact-2026-09-21-v1"


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
        or connectivity.get("total_count") != 12
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
                "bundle_sha256": bundle["bundle_sha256"],
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
