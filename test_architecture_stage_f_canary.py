from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from test_issue126_successor_accounting_reconcile_boundary import (
    Issue126SuccessorAccountingBoundaryTests,
)
from test_issue126_successor_compatibility import Issue126SuccessorCompatibilityTests
from test_verified_v3_successor_epoch_migration import Issue126V3V4SuccessorMigrationTests
from trading.canary import (
    CanaryEvidence,
    CanaryInvariantError,
    CanaryReadinessPlanner,
)
from trading.accounting import (
    BaselineSnapshot,
    CanonicalAccountingProjector,
    ExecutionSnapshot,
)
from trading.risk import RiskLimits, ShadowRiskEngine
from trading.state import CanonicalStateSnapshot
from trading.state_store import CanonicalStateStore
from trading.valuation import DeterministicValuationService, ProtectedMarkSnapshot

ROOT = Path(__file__).resolve().parent


class StablePaperCoreStageFCanaryTests(unittest.TestCase):
    def _all_green(self) -> CanaryEvidence:
        return CanaryEvidence(
            issue_82_fresh_risk_day_pass=True,
            issue_82_forward_session_pass=True,
            clean_active_accounting_audit=True,
            canonical_ledger_chain_valid=True,
            protected_valuation_sane=True,
            stage_b_valuation_parity=True,
            stage_c_risk_parity=True,
            stage_d_restart_parity=True,
            stage_e_accounting_parity=True,
            single_revision_snapshot_binding=True,
            repository_validation_green=True,
            architecture_debt_gate_green=True,
            refactor_startup_audit_green=True,
        )

    def test_contract_remains_shadow_only(self) -> None:
        contract = json.loads((ROOT / "stable_paper_core_v3_stage_f_contract.json").read_text())
        self.assertEqual(contract["authority"], "shadow_only")
        constraints = contract["constraints"]
        self.assertFalse(constraints["runtime_registration"])
        self.assertFalse(constraints["production_state_writes"])
        self.assertFalse(constraints["order_authority"])
        self.assertTrue(constraints["rollback_switch_required"])
        self.assertTrue(constraints["rollback_default_armed"])
        self.assertTrue(constraints["single_revision_snapshot_binding_required"])

    def test_current_issue_82_missing_proof_blocks_canary(self) -> None:
        evidence = CanaryEvidence(
            issue_82_fresh_risk_day_pass=False,
            issue_82_forward_session_pass=False,
            clean_active_accounting_audit=False,
            canonical_ledger_chain_valid=True,
            protected_valuation_sane=True,
            stage_b_valuation_parity=True,
            stage_c_risk_parity=True,
            stage_d_restart_parity=True,
            stage_e_accounting_parity=False,
            single_revision_snapshot_binding=False,
            repository_validation_green=True,
            architecture_debt_gate_green=True,
            refactor_startup_audit_green=True,
        )
        plan = CanaryReadinessPlanner.plan(evidence=evidence, requested_fraction=0.01)
        self.assertFalse(plan.eligible_for_future_canary)
        self.assertIn("issue_82_fresh_risk_day_pass", plan.blockers)
        self.assertIn("issue_82_forward_session_pass", plan.blockers)
        self.assertIn("clean_active_accounting_audit", plan.blockers)
        self.assertIn("stage_e_accounting_parity", plan.blockers)
        self.assertIn("single_revision_snapshot_binding", plan.blockers)
        self.assertTrue(plan.rollback_default_armed)
        self.assertFalse(plan.production_state_writes)
        self.assertFalse(plan.order_authority)

    def test_all_required_evidence_only_marks_future_eligibility(self) -> None:
        plan = CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.01)
        self.assertTrue(plan.eligible_for_future_canary)
        self.assertEqual(plan.blockers, ())
        self.assertFalse(plan.runtime_registration)
        self.assertFalse(plan.production_state_writes)
        self.assertFalse(plan.order_authority)
        self.assertFalse(plan.risk_mutation_authority)

    def test_canary_fraction_is_bounded(self) -> None:
        with self.assertRaises(CanaryInvariantError):
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.0)
        with self.assertRaises(CanaryInvariantError):
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.051)
        self.assertEqual(
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.05).requested_fraction,
            0.05,
        )

    def test_one_immutable_revision_binds_accounting_valuation_and_risk(self) -> None:
        accounting = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(cash=10000.0),
            executions=(
                ExecutionSnapshot(
                    1,
                    "QQQ",
                    "entry",
                    "long",
                    2,
                    100,
                    "2026-08-20 10:00",
                    "entry-1",
                ),
            ),
            marks={"QQQ": 105.0},
            today="2026-08-20",
        )
        marks = (
            ProtectedMarkSnapshot(
                "QQQ",
                105.0,
                "test-protected-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-08-20 10:01",
            ),
        )
        valuation = DeterministicValuationService.value(
            cash=accounting.portfolio.cash,
            positions=accounting.portfolio.positions,
            marks=marks,
        )
        risk = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation,
            realized_today=accounting.portfolio.realized_today,
            limits=RiskLimits(0.03, 0.03, 0.03),
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=accounting.portfolio,
                risk=risk.state,
                execution_ledger_rows=accounting.execution_rows,
                execution_chain_valid=True,
            ),
            revision=7,
            created_at="2026-08-20 10:02",
        )

        proof = CanaryReadinessPlanner.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
        )
        self.assertTrue(proof.verified)
        self.assertEqual(proof.blockers, ())
        self.assertEqual(proof.revision, 7)
        self.assertEqual(proof.payload_sha256, envelope.payload_sha256)
        self.assertTrue(proof.rollback_default_armed)
        self.assertFalse(proof.production_state_writes)
        self.assertFalse(proof.risk_mutation_authority)
        self.assertFalse(proof.order_authority)

    def test_snapshot_binding_fails_closed_on_ledger_revision_drift(self) -> None:
        accounting = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(cash=10000.0),
            executions=(),
        )
        valuation = DeterministicValuationService.value(
            cash=accounting.portfolio.cash,
            positions=(),
            marks=(),
        )
        risk = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation,
            realized_today=0.0,
            limits=RiskLimits(0.03, 0.03, 0.03),
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=accounting.portfolio,
                risk=risk.state,
                execution_ledger_rows=1,
                execution_chain_valid=True,
            ),
            revision=8,
            created_at="2026-08-20 10:02",
        )

        proof = CanaryReadinessPlanner.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
        )
        self.assertFalse(proof.verified)
        self.assertEqual(proof.blockers, ("ledger_projection_row_count",))

    def test_module_has_no_runtime_or_write_authority(self) -> None:
        path = ROOT / "trading" / "canary.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        forbidden_imports = {
            "app",
            "state_io_hardening",
            "alpaca_trade_api",
            "yfinance",
            "flask",
            "os",
            "threading",
        }
        forbidden_calls = {
            "save_state",
            "load_state",
            "submit_order",
            "place_order",
            "enter_position",
            "exit_position",
            "install",
            "apply",
            "register_routes",
            "open",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                self.assertNotIn(name, forbidden_calls)


if __name__ == "__main__":
    unittest.main()
