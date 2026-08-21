from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from change_safety_audit import CORE_TESTS
from system_sentinel import diagnose, report

ROOT = Path(__file__).resolve().parent


class SystemSentinelTests(unittest.TestCase):
    def test_normal_runtime_is_quiet(self) -> None:
        snapshot = {
            "valuation": {"status": "ok", "equity": 12000.0, "risk_baseline_eligible": True},
            "accounting": {"status": "ok", "coverage_complete": True, "economic_issue_count": 0, "coverage_issue_count": 0},
            "execution_ledger": {"chain_valid": True, "row_count": 3},
            "risk": {"day_start_equity": 12000.0, "day_peak_equity": 12100.0, "halted": False},
            "startup": {"status": "ready"},
            "configuration": {"violations": []},
            "architecture": {"new_critical": [], "ownership_violations": []},
            "runner": {"active_error": False},
            "market_data": {"status": "pass", "accounting_complete_at_snapshot": True, "in_flight_or_unclassified_requests": 0},
        }
        payload = report(snapshot)
        self.assertEqual(payload["status"], "quiet")
        self.assertEqual(payload["incident_count"], 0)

    def test_seeded_faults_are_classified(self) -> None:
        snapshot = {
            "valuation": {"status": "fail", "equity": -1.0, "risk_baseline_eligible": False},
            "accounting": {"status": "partial", "coverage_complete": False, "economic_issue_count": 1, "coverage_issue_count": 1},
            "execution_ledger": {"chain_valid": False, "row_count": 4},
            "risk": {"day_start_equity": -1.0, "day_peak_equity": 100.0, "halted": True},
            "startup": {"status": "error", "error": "boom"},
            "configuration": {"violations": ["STATE_FILE drift"]},
            "architecture": {"new_critical": ["save_state owner"], "ownership_violations": []},
            "runner": {"active_error": True, "last_error": "dictionary changed size"},
            "market_data": {"status": "fail", "accounting_complete_at_snapshot": False, "in_flight_or_unclassified_requests": 1},
        }
        rows = diagnose(snapshot)
        reasons = {row.reason_code for row in rows}
        self.assertEqual(reasons, {
            "invalid_protected_valuation", "accounting_integrity_failure", "execution_chain_invalid",
            "invalid_risk_baseline", "startup_failure", "configuration_drift",
            "architecture_ownership_regression", "runner_active_error", "market_data_incomplete",
        })

    def test_mandatory_core_tests_are_never_skipped(self) -> None:
        rows = diagnose({"runner": {"active_error": True, "last_error": "x"}})
        self.assertEqual(len(rows), 1)
        selected = set(rows[0].selected_tests)
        self.assertTrue(set(CORE_TESTS).issubset(selected))

    def test_high_severity_cross_boundary_faults_require_full_audit(self) -> None:
        rows = diagnose({"execution_ledger": {"chain_valid": False}})
        self.assertTrue(rows[0].full_audit_required)

    def test_incident_id_and_test_selection_are_deterministic(self) -> None:
        snapshot = {"runner": {"active_error": True, "last_error": "repeatable", "last_attempt": "t"}}
        first = diagnose(snapshot)[0]
        second = diagnose(snapshot)[0]
        self.assertEqual(first.incident_id, second.incident_id)
        self.assertEqual(first.selected_tests, second.selected_tests)

    def test_contract_matches_read_only_policy(self) -> None:
        contract = json.loads((ROOT / "system_sentinel_contract.json").read_text())
        policy = contract["policy"]
        self.assertEqual(contract["authority"], "advisory_only")
        self.assertTrue(policy["mandatory_core_tests_never_skipped"])
        self.assertFalse(policy["auto_merges"])
        self.assertFalse(policy["writes_production_state"])
        self.assertFalse(policy["clears_halts"])
        self.assertFalse(contract["self_healing"]["enabled"])

    def test_module_has_no_runtime_or_authoritative_mutation_calls(self) -> None:
        path = ROOT / "system_sentinel.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        forbidden_imports = {"app", "state_io_hardening", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {
            "save_state", "load_state", "atomic_json_write", "enter_position", "exit_position",
            "submit_order", "place_order", "execute_order", "clear_halt", "update_ref", "merge_pull_request",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                self.assertNotIn(name, forbidden_calls)


if __name__ == "__main__":
    unittest.main()
