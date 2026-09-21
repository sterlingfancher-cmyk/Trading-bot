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
                    "reachable_count": 12,
                    "total_count": 12,
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
