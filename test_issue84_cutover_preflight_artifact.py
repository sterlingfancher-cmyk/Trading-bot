from __future__ import annotations

import ast
import unittest
from pathlib import Path

import test_architecture_stage_f_canary as stage_f_test
from build_cutover_preflight_artifact import build_artifacts
from trading.canary import (
    CanaryInvariantError,
    CutoverDecisionReviewContract,
    CutoverPreflightEvidenceBundle,
)

ROOT = Path(__file__).resolve().parent
COMMIT = "b73e8891889f1210ab357984b2e563d96fbc4f6d"
BASE_URL = "https://web-production-e1796.up.railway.app"


class Issue84CutoverPreflightArtifactTests(unittest.TestCase):
    def _snapshot(self):
        audit, status, day = (
            stage_f_test.StablePaperCoreStageFCanaryTests()._v5_runtime_evidence()
        )
        audit = {**audit, "generated_local": "2026-09-21 10:15:00 CDT"}
        raw = {
            name: {"status": "ok", "payload": {}}
            for name in (
                "bootstrap_status",
                "root",
                "paper_status",
                "self_check",
                "fresh_day_check",
                "daily_audit",
                "system_sentinel",
                "governed_v5_restart",
                "verified_v2_recovery_gate",
                "v1_status",
                "v2_status",
                "v2_ablation",
                "v2_regime",
            )
        }
        raw["daily_audit"]["payload"] = audit
        raw["paper_status"]["payload"] = status
        raw["fresh_day_check"]["payload"] = day
        raw["system_sentinel"]["payload"] = {
            "overall": "pass",
            "status": "quiet",
            "incident_count": 0,
            "collection_errors": {},
            "generated_commit_sha": COMMIT,
        }
        return {
            "read_only": True,
            "base_url": BASE_URL,
            "status": "pass",
            "summary": {
                "connectivity": {
                    "reachable_count": 13,
                    "total_count": 13,
                    "classification_failed_endpoints": [],
                    "application_ready": True,
                }
            },
            "raw": raw,
        }

    def test_complete_settled_snapshot_emits_pending_fail_closed_artifacts(self):
        bundle_row, decision_row = build_artifacts(
            runtime_snapshot=self._snapshot(),
            deployed_commit_sha=COMMIT,
            splendid_deployment_settled=True,
            projection_revision=1,
        )
        bundle = CutoverPreflightEvidenceBundle.from_dict(
            {
                key: value
                for key, value in bundle_row.items()
                if key
                not in {
                    "artifact_version",
                    "artifact_kind",
                    "production_authority",
                    "projection_revision_is_shadow_only",
                }
            }
        )
        decision = CutoverDecisionReviewContract.from_evidence_bundle(bundle)

        self.assertEqual(decision_row["decision_sha256"], decision.decision_sha256)
        self.assertEqual(decision_row["review_status"], "pending_review")
        self.assertFalse(decision_row["cutover_review_completed"])
        self.assertFalse(decision_row["activation_performed"])
        self.assertFalse(decision_row["production_authority"])
        self.assertFalse(bundle_row["production_authority"])
        self.assertTrue(bundle_row["projection_revision_is_shadow_only"])
        self.assertEqual(decision_row["state"], "blocked")
        self.assertIn("future_canary_evidence", decision_row["blockers"])
        self.assertIn("validation_hold_released", decision_row["blockers"])
        self.assertIn(
            "risk_halt_released_by_governed_evidence", decision_row["blockers"]
        )
        canary_evidence = bundle_row["evidence"]["canary_evidence"]
        for blocker in (
            "issue_82_forward_session_pass",
            "stage_b_valuation_parity",
            "stage_c_risk_parity",
            "stage_d_restart_parity",
            "stage_e_accounting_parity",
            "repository_validation_green",
            "architecture_debt_gate_green",
            "refactor_startup_audit_green",
        ):
            self.assertFalse(canary_evidence[blocker])

    def _released_snapshot(self):
        snapshot = self._snapshot()
        audit = snapshot["raw"]["daily_audit"]["payload"]
        audit["overall"] = "pass"
        audit["generated_local"] = "2026-09-29 08:21:34 CDT"
        audit["accounting_epoch"].update(
            {
                "validation_hold": False,
                "validation_released": True,
            }
        )
        audit["execution_ledger"]["ledger_sha256"] = (
            "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
        )
        audit["accounting_integrity"]["parsed_trade_rows"] = 0
        audit["risk"].update({"halted": False, "halt_reason": None})
        snapshot["raw"]["fresh_day_check"]["payload"].update(
            {"halted": False, "halt_reason": None}
        )
        snapshot["raw"]["governed_v5_restart"]["payload"] = {
            "version": "governed-v5-paper-restart-2026-09-25-v1",
            "decision_id": "issue84-governed-paper-restart-2026-09-25",
            "review_reference": "issue-84-comment-5802294002",
            "epoch_id": "stable-paper-v5-20260914-issue222-flat-successor01",
            "status": "active",
            "overall": "pass",
            "paper_execution_enabled": True,
            "validation_hold": False,
            "risk_halted": False,
            "post_start_forward_observations_required": True,
            "preappend_abort_recovery": {
                "status": "recovered",
                "overall": "pass",
                "canonical_row_count": 88,
                "canonical_ledger_sha256": (
                    "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
                ),
                "version": "governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor",
                "recovery_mode": "pr282_failed_recovery_successor",
                "incident_evidence_reference": "issue-84-comment-5897148822",
                "historical_discrepancy_preserved": True,
                "historical_discrepancy_rewritten": False,
                "checks": {"all_exact": True},
            },
        }
        return snapshot

    def test_released_runtime_emits_post_start_acceptance_not_preflight(self):
        evidence, result = build_artifacts(
            runtime_snapshot=self._released_snapshot(),
            deployed_commit_sha=COMMIT,
            splendid_deployment_settled=True,
        )

        self.assertEqual(
            evidence["artifact_kind"],
            "governed_restart_post_start_acceptance_evidence",
        )
        self.assertTrue(all(evidence["checks"].values()))
        self.assertFalse(evidence["production_authority"])
        self.assertEqual(result["state"], "active_pending_forward_observations")
        self.assertTrue(result["activation_observed"])
        self.assertFalse(result["activation_performed_by_builder"])
        self.assertEqual(result["blockers"], ["post_start_forward_observations"])

    def test_released_runtime_accepts_reconciled_forward_entries(self):
        snapshot = self._released_snapshot()
        audit = snapshot["raw"]["daily_audit"]["payload"]
        audit["execution_ledger"].update(
            {
                "row_count": 92,
                "ledger_sha256": "c" * 64,
                "current_epoch_rows": 4,
                "state_current_epoch_rows": 4,
            }
        )
        audit["accounting_integrity"]["reconstructed_open_positions"] = [
            "AMD",
            "ANET",
            "LITE",
            "QQQ",
        ]
        audit["accounting_integrity"]["parsed_trade_rows"] = 4
        audit["account"].update(
            {
                "cash": 9884.47,
                "equity": 13443.10,
                "positions": ["QQQ", "ANET", "AMD", "LITE"],
            }
        )
        snapshot["raw"]["paper_status"]["payload"]["positions"] = {
            symbol: {"side": "long"}
            for symbol in ("AMD", "ANET", "LITE", "QQQ")
        }
        governed = snapshot["raw"]["governed_v5_restart"]["payload"]
        governed["preappend_abort_recovery"].update(
            {
                "canonical_row_count": 88,
                "canonical_ledger_sha256": (
                    "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
                ),
            }
        )
        governed["last_execution_receipt"] = {
            "canonical_last_execution_id": "execution-4",
            "canonical_row_count": 92,
            "intent_id": "intent-4",
            "operation": "entry",
        }

        evidence, result = build_artifacts(
            runtime_snapshot=snapshot,
            deployed_commit_sha=COMMIT,
            splendid_deployment_settled=True,
        )

        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["ledger_row_count"], 92)
        self.assertEqual(evidence["current_epoch_rows"], 4)
        self.assertEqual(evidence["prestart_ledger_row_count"], 88)
        self.assertEqual(result["state"], "active_pending_forward_observations")

    def test_released_runtime_rejects_forward_ledger_or_accounting_drift(self):
        for mutate in ("row_delta", "state_rows", "positions", "receipt"):
            with self.subTest(mutate=mutate):
                snapshot = self._released_snapshot()
                audit = snapshot["raw"]["daily_audit"]["payload"]
                audit["execution_ledger"].update(
                    {
                        "row_count": 89,
                        "ledger_sha256": "c" * 64,
                        "current_epoch_rows": 1,
                        "state_current_epoch_rows": 1,
                    }
                )
                audit["accounting_integrity"]["reconstructed_open_positions"] = [
                    "AMD"
                ]
                audit["accounting_integrity"]["parsed_trade_rows"] = 1
                audit["account"].update(
                    {"cash": 12000.0, "equity": 13400.0, "positions": ["AMD"]}
                )
                snapshot["raw"]["paper_status"]["payload"]["positions"] = {
                    "AMD": {"side": "long"}
                }
                governed = snapshot["raw"]["governed_v5_restart"]["payload"]
                governed["preappend_abort_recovery"].update(
                    {
                        "canonical_row_count": 88,
                        "canonical_ledger_sha256": (
                            "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
                        ),
                    }
                )
                governed["last_execution_receipt"] = {
                    "canonical_last_execution_id": "execution-1",
                    "canonical_row_count": 89,
                    "intent_id": "intent-1",
                    "operation": "entry",
                }
                if mutate == "row_delta":
                    audit["execution_ledger"]["row_count"] = 90
                elif mutate == "state_rows":
                    audit["execution_ledger"]["state_current_epoch_rows"] = 0
                elif mutate == "positions":
                    audit["accounting_integrity"]["reconstructed_open_positions"] = []
                else:
                    governed["last_execution_receipt"]["canonical_row_count"] = 88

                with self.assertRaises(CanaryInvariantError):
                    build_artifacts(
                        runtime_snapshot=snapshot,
                        deployed_commit_sha=COMMIT,
                        splendid_deployment_settled=True,
                    )

    def test_released_runtime_fails_closed_on_governance_or_ledger_drift(self):
        for mutate in ("decision", "ledger"):
            with self.subTest(mutate=mutate):
                snapshot = self._released_snapshot()
                if mutate == "decision":
                    governed = snapshot["raw"]["governed_v5_restart"]["payload"]
                    governed["decision_id"] = "unreviewed"
                else:
                    snapshot["raw"]["daily_audit"]["payload"][
                        "execution_ledger"
                    ]["chain_valid"] = False
                with self.assertRaises(CanaryInvariantError):
                    build_artifacts(
                        runtime_snapshot=snapshot,
                        deployed_commit_sha=COMMIT,
                        splendid_deployment_settled=True,
                    )

    def test_released_runtime_fails_closed_on_recovery_receipt_drift(self):
        for mutate in ("mode", "reference", "check"):
            with self.subTest(mutate=mutate):
                snapshot = self._released_snapshot()
                recovery = snapshot["raw"]["governed_v5_restart"]["payload"][
                    "preappend_abort_recovery"
                ]
                if mutate == "mode":
                    recovery["recovery_mode"] = "different"
                elif mutate == "reference":
                    recovery["incident_evidence_reference"] = "different"
                else:
                    recovery["checks"]["all_exact"] = False
                with self.assertRaises(CanaryInvariantError):
                    build_artifacts(
                        runtime_snapshot=snapshot,
                        deployed_commit_sha=COMMIT,
                        splendid_deployment_settled=True,
                    )

    def test_incomplete_or_wrong_commit_snapshot_is_rejected(self):
        incomplete = self._snapshot()
        incomplete["summary"]["connectivity"]["reachable_count"] = 2
        with self.assertRaises(CanaryInvariantError):
            build_artifacts(
                runtime_snapshot=incomplete,
                deployed_commit_sha=COMMIT,
                splendid_deployment_settled=True,
            )

        wrong_commit = self._snapshot()
        wrong_commit["raw"]["system_sentinel"]["payload"][
            "generated_commit_sha"
        ] = "a" * 40
        with self.assertRaises(CanaryInvariantError):
            build_artifacts(
                runtime_snapshot=wrong_commit,
                deployed_commit_sha=COMMIT,
                splendid_deployment_settled=True,
            )

    def test_unsettled_or_invalid_revision_is_rejected(self):
        with self.assertRaises(CanaryInvariantError):
            build_artifacts(
                runtime_snapshot=self._snapshot(),
                deployed_commit_sha=COMMIT,
                splendid_deployment_settled=False,
            )
        for revision in (True, 0, "1"):
            with self.subTest(revision=revision), self.assertRaises(
                CanaryInvariantError
            ):
                build_artifacts(
                    runtime_snapshot=self._snapshot(),
                    deployed_commit_sha=COMMIT,
                    splendid_deployment_settled=True,
                    projection_revision=revision,
                )

    def test_builder_has_no_network_application_or_production_state_access(self):
        path = ROOT / "build_cutover_preflight_artifact.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "urllib",
            "requests",
            "alpaca_trade_api",
            "yfinance",
            "flask",
        }
        forbidden_calls = {
            "urlopen",
            "submit_order",
            "place_order",
            "enter_position",
            "exit_position",
            "register_routes",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(
                    (node.module or "").split(".", 1)[0], forbidden_imports
                )
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                self.assertNotIn(name, forbidden_calls)

    def test_ci_capture_retry_is_bounded_for_slow_deferred_startup(self):
        workflow = (ROOT / ".github" / "workflows" / "refactor-audit.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("for attempt in 1 2 3 4 5 6 7 8; do", workflow)
        self.assertIn('if [ "$attempt" -lt 8 ]; then', workflow)
        self.assertIn("sleep 45", workflow)
        self.assertNotIn("while true", workflow)


if __name__ == "__main__":
    unittest.main()
