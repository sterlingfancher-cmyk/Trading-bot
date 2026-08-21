from __future__ import annotations

import unittest

from change_safety_audit import classify_paths, evaluate_gate, planned_regressions


class ChangeSafetyAuditTests(unittest.TestCase):
    def test_seeded_breaking_regression_is_blocked(self) -> None:
        decision = evaluate_gate(
            expected_head="abc123",
            actual_head="abc123",
            paths=("trading/risk.py", "app.py"),
            component_results={
                "targeted_regressions": "success",
                "repository_validation": "success",
                "architecture_contract": "success",
                "typed_configuration": "success",
                "architecture_debt": "failure",
                "startup_smoke": "success",
            },
            new_critical=1,
        )
        self.assertEqual(decision.status, "fail")
        self.assertTrue(any("architecture_debt" in row for row in decision.failures))
        self.assertTrue(any("new_critical=1" in row for row in decision.failures))

    def test_safe_change_passes_when_all_evidence_is_exact_and_green(self) -> None:
        decision = evaluate_gate(
            expected_head="def456",
            actual_head="def456",
            paths=("docs/architecture_notes.md",),
            component_results={
                "targeted_regressions": "success",
                "repository_validation": "success",
                "architecture_contract": "success",
                "typed_configuration": "success",
                "architecture_debt": "success",
                "startup_smoke": "success",
            },
            new_critical=0,
        )
        self.assertEqual(decision.status, "pass")
        self.assertEqual(decision.failures, ())

    def test_stale_audit_head_fails_closed(self) -> None:
        decision = evaluate_gate(
            expected_head="new-head",
            actual_head="old-head",
            paths=("trading/state_store.py",),
            component_results={"startup_smoke": "success"},
            new_critical=0,
        )
        self.assertEqual(decision.status, "fail")
        self.assertFalse(decision.exact_head_match)

    def test_authority_boundary_classification(self) -> None:
        categories, boundaries = classify_paths(
            (
                "app.py",
                "trading/state_store.py",
                "trading/valuation.py",
                "trading/accounting.py",
                "trading/risk.py",
            )
        )
        self.assertIn("runtime_composition", categories)
        for boundary in ("startup_runtime", "state", "valuation", "accounting", "risk"):
            self.assertIn(boundary, boundaries)

    def test_verified_snapshot_provenance_change_selects_focused_regressions(self) -> None:
        for path in (
            "verified_snapshot_provenance_status.py",
            "verified_snapshot_backup_provenance_status.py",
            "verified_snapshot_journal_ledger_provenance_status.py",
        ):
            categories, boundaries = classify_paths((path,))
            tests = planned_regressions((path,))

            self.assertIn("state_persistence", categories)
            self.assertIn("state", boundaries)
            self.assertIn("accounting", boundaries)
            self.assertIn("test_verified_snapshot_provenance_status.py", tests)
            self.assertIn("test_verified_snapshot_backup_provenance_status.py", tests)
            self.assertIn(
                "test_verified_snapshot_journal_ledger_provenance_status.py", tests
            )
            for core_test in (
                "test_architecture_stage_b.py",
                "test_architecture_stage_c.py",
                "test_architecture_stage_d_state_store.py",
                "test_architecture_stage_e_accounting.py",
                "test_architecture_stage_f_canary.py",
            ):
                self.assertIn(core_test, tests)


if __name__ == "__main__":
    unittest.main()
