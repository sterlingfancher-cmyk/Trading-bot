from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from test_issue126_successor_accounting_reconcile_boundary import (
    Issue126SuccessorAccountingBoundaryTests,
)
from trading.canary import (
    CanaryEvidence,
    CanaryInvariantError,
    CanaryReadinessPlanner,
)

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
