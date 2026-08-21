from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from trading.accounting import (
    AccountingInvariantError,
    BaselineSnapshot,
    CanonicalAccountingProjector,
    ExecutionSnapshot,
)
from trading.state import AccountingEpochSnapshot, PositionSnapshot

ROOT = Path(__file__).resolve().parent


class StablePaperCoreStageEAccountingTests(unittest.TestCase):
    def _baseline(self) -> BaselineSnapshot:
        return BaselineSnapshot(
            cash=10000.0,
            positions=(),
            accounting_epoch=AccountingEpochSnapshot(
                epoch_id="stable-paper-v3-test",
                baseline_type="verified_snapshot",
                historical_evidence_archived=True,
                validation_hold=False,
            ),
        )

    def test_contract_remains_shadow_only(self) -> None:
        contract = json.loads((ROOT / "stable_paper_core_v3_stage_e_contract.json").read_text())
        self.assertEqual(contract["authority"], "shadow_only")
        self.assertTrue(contract["constraints"]["unmatched_exit_rejected"])
        self.assertFalse(contract["constraints"]["historical_ledger_rewrite"])

    def test_long_round_trip_realized_pnl(self) -> None:
        rows = (
            ExecutionSnapshot(1, "QQQ", "entry", "long", 2, 100, "2026-08-20 10:00", "e1"),
            ExecutionSnapshot(2, "QQQ", "exit", "long", 2, 110, "2026-08-20 11:00", "e2"),
        )
        out = CanonicalAccountingProjector.project(baseline=self._baseline(), executions=rows, today="2026-08-20")
        self.assertEqual(out.portfolio.cash, 10020.0)
        self.assertEqual(out.portfolio.equity, 10020.0)
        self.assertEqual(out.portfolio.realized_total, 20.0)
        self.assertEqual(out.portfolio.realized_today, 20.0)
        self.assertEqual(out.portfolio.positions, ())

    def test_short_round_trip_realized_pnl(self) -> None:
        rows = (
            ExecutionSnapshot(1, "AMD", "entry", "short", 2, 100, "2026-08-20 10:00", "e1"),
            ExecutionSnapshot(2, "AMD", "exit", "short", 2, 90, "2026-08-20 11:00", "e2"),
        )
        out = CanonicalAccountingProjector.project(baseline=self._baseline(), executions=rows, today="2026-08-20")
        self.assertEqual(out.portfolio.cash, 10020.0)
        self.assertEqual(out.portfolio.realized_total, 20.0)

    def test_partial_exit_preserves_remaining_position(self) -> None:
        rows = (
            ExecutionSnapshot(1, "MSFT", "entry", "long", 4, 100, "2026-08-20 10:00", "e1"),
            ExecutionSnapshot(2, "MSFT", "exit", "long", 1, 110, "2026-08-20 11:00", "e2"),
        )
        out = CanonicalAccountingProjector.project(baseline=self._baseline(), executions=rows, marks={"MSFT": 105}, today="2026-08-20")
        self.assertEqual(len(out.portfolio.positions), 1)
        self.assertEqual(out.portfolio.positions[0].quantity, 3)
        self.assertEqual(out.portfolio.realized_total, 10.0)
        self.assertEqual(out.portfolio.unrealized_pnl, 15.0)
        self.assertEqual(out.portfolio.equity, 10025.0)

    def test_unmatched_exit_fails_closed(self) -> None:
        with self.assertRaises(AccountingInvariantError):
            CanonicalAccountingProjector.project(
                baseline=self._baseline(),
                executions=(ExecutionSnapshot(1, "QQQ", "exit", "long", 1, 100, "2026-08-20", "e1"),),
            )

    def test_duplicate_execution_id_fails_closed(self) -> None:
        rows = (
            ExecutionSnapshot(1, "QQQ", "entry", "long", 1, 100, "2026-08-20", "dup"),
            ExecutionSnapshot(2, "QQQ", "exit", "long", 1, 100, "2026-08-20", "dup"),
        )
        with self.assertRaises(AccountingInvariantError):
            CanonicalAccountingProjector.project(baseline=self._baseline(), executions=rows)

    def test_out_of_order_sequence_fails_closed(self) -> None:
        rows = (
            ExecutionSnapshot(2, "QQQ", "entry", "long", 1, 100, "2026-08-20", "e2"),
            ExecutionSnapshot(1, "QQQ", "exit", "long", 1, 100, "2026-08-20", "e1"),
        )
        with self.assertRaises(AccountingInvariantError):
            CanonicalAccountingProjector.project(baseline=self._baseline(), executions=rows)

    def test_existing_baseline_position_projects_without_rewriting_history(self) -> None:
        baseline = BaselineSnapshot(
            cash=9000,
            positions=(PositionSnapshot("QQQ", "long", 2, 500, 500),),
            realized_total=50,
            accounting_epoch=self._baseline().accounting_epoch,
        )
        out = CanonicalAccountingProjector.project(baseline=baseline, executions=(), marks={"QQQ": 510})
        self.assertEqual(out.portfolio.cash, 9000)
        self.assertEqual(out.portfolio.unrealized_pnl, 20)
        self.assertEqual(out.portfolio.equity, 10020)
        self.assertEqual(out.portfolio.accounting_epoch.epoch_id, "stable-paper-v3-test")

    def test_module_has_no_runtime_or_write_authority(self) -> None:
        path = ROOT / "trading" / "accounting.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        forbidden_imports = {"app", "state_io_hardening", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {"save_state", "load_state", "submit_order", "place_order", "enter_position", "exit_position", "install", "apply", "register_routes"}
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
