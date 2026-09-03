from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = Path(".github/workflows/daily-operational-audit.yml")


class DailyOperationalAuditWorkflowTests(unittest.TestCase):
    def test_cycle_contract_version_is_derived_from_runtime_source(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("import cycle_completion_contract as contract", text)
        self.assertIn("print(contract.VERSION)", text)
        self.assertIn("import cycle_completion_contract as cycle_contract", text)
        self.assertIn('assert cycle.get("version") == cycle_contract.VERSION, cycle', text)

    def test_obsolete_cycle_contract_literal_is_not_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("cycle-completion-contract-2026-08-04-v2-rebind-safe", text)

    def test_workflow_runs_this_regression(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("test_daily_operational_audit_workflow.py"), 2)


if __name__ == "__main__":
    unittest.main()
