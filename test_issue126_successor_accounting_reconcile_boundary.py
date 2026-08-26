import copy
import unittest
from unittest import mock

import paper_accounting_integrity_guard as accounting


class FakeCore:
    def __init__(self, *, epoch_id, validation_hold=True):
        self.save_calls = 0
        self.portfolio = {
            "cash": 1059.27,
            "equity": 1059.27,
            "accounting_epoch_id": epoch_id,
            "paper_accounting_epoch": {
                "id": epoch_id,
                "epoch_id": epoch_id,
                "validation_hold": validation_hold,
            },
            "positions": {},
            "performance": {},
            "risk_controls": {"halted": False, "halt_reason": "", "cooldowns": {}},
            "trades": [],
        }

    def local_ts_text(self):
        return "2026-08-26 08:35:12 CDT"

    def save_state(self, state=None):
        self.save_calls += 1


PRE_EXIT_RECONSTRUCTION = {
    "status": "ok",
    "coverage_complete": True,
    "cash": 1000.0,
    "equity": 1059.27,
    "market_value": 59.27,
    "realized_total": 0.0,
    "realized_today": 0.0,
    "unrealized_pnl": 0.0,
    "open_positions": {
        "SLS": {
            "qty": 4.353086829,
            "entry_price": 14.335,
            "last_price": 13.62,
            "market_value": 59.27,
            "cost_basis": 62.397,
            "unrealized_pnl": -3.127,
            "unrealized_pnl_pct": -5.01,
        }
    },
}

POST_EXIT_RECONSTRUCTION = {
    "status": "ok",
    "coverage_complete": True,
    "cash": 1059.27,
    "equity": 1059.27,
    "market_value": 0.0,
    "realized_total": -3.127,
    "realized_today": -3.127,
    "unrealized_pnl": 0.0,
    "open_positions": {},
}


class Issue126SuccessorAccountingBoundaryTests(unittest.TestCase):
    def test_v3_validation_hold_does_not_resurrect_position_during_full_exit_window(self):
        core = FakeCore(epoch_id="stable-paper-v3-20260825-successor01")
        before = copy.deepcopy(core.portfolio)

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=PRE_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(core.portfolio["cash"], before["cash"])
        self.assertEqual(core.portfolio["positions"], {})
        self.assertFalse(status["repaired"])
        self.assertTrue(status["successor_validation_hold_read_only"])
        self.assertTrue(status["automatic_repair_suppressed"])
        self.assertEqual(status["overall"], "warn")
        self.assertGreater(status["discrepancy_count_remaining"], 0)

    def test_same_v3_state_passes_after_canonical_exit_is_visible(self):
        core = FakeCore(epoch_id="stable-paper-v3-20260825-successor01")

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=POST_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(core.portfolio["positions"], {})
        self.assertEqual(status["overall"], "pass")
        self.assertEqual(status["discrepancy_count_remaining"], 0)
        self.assertTrue(status["successor_validation_hold_read_only"])
        self.assertFalse(status["automatic_repair_suppressed"])

    def test_verified_v2_legacy_repair_semantics_are_preserved(self):
        core = FakeCore(epoch_id="stable-paper-v2-20260812-verified01")

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=PRE_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 1)
        self.assertTrue(status["repaired"])
        self.assertFalse(status["successor_validation_hold_read_only"])
        self.assertIn("SLS", core.portfolio["positions"])
        self.assertAlmostEqual(core.portfolio["positions"]["SLS"]["shares"], 4.353087)
        self.assertAlmostEqual(core.portfolio["cash"], 1000.0)

    def test_v3_without_validation_hold_retains_existing_repair_behavior(self):
        core = FakeCore(epoch_id="stable-paper-v3-20260825-successor01", validation_hold=False)

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=PRE_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=False)

        self.assertTrue(status["repaired"])
        self.assertFalse(status["successor_validation_hold_read_only"])
        self.assertIn("SLS", core.portfolio["positions"])


if __name__ == "__main__":
    unittest.main()
