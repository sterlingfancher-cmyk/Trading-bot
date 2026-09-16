import copy
import unittest
from unittest import mock

import paper_accounting_integrity_guard as accounting
import paper_accounting_readonly_status as readonly_status
import paper_bidirectional_accounting_guard as bidirectional


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


def _issue222_v5_core():
    core = FakeCore(epoch_id=accounting.ISSUE222_V5_EPOCH_ID)
    core.portfolio.update({
        "cash": 13429.130485,
        "equity": 13429.13,
        "paper_accounting_epoch": {
            "id": accounting.ISSUE222_V5_EPOCH_ID,
            "version": accounting.ISSUE222_V5_VERSION,
            "decision_id": accounting.ISSUE222_DECISION_ID,
            "prior_epoch_id": accounting.ISSUE222_V4_EPOCH_ID,
            "historical_recovery_decision": accounting.ISSUE222_HISTORICAL_DECISION,
            "historical_evidence_archived": True,
            "forensic_archive_dir": "/app/data/forensic_archives/issue222-exact",
            "validation_hold": True,
            "validation_release_status": "blocked",
            "validation_released": False,
            "zero_trade_baseline": True,
            "baseline_type": "verified_flat_snapshot_unresolved_prior_projection",
            "prior_epoch_discrepancy_status": "unresolved_non_promotable",
            "prior_epoch_economics_promotable": False,
            "fabricated_exit_rows": 0,
            "verified_snapshot_baseline": {
                "verified": True,
                "version": accounting.ISSUE222_V5_VERSION,
                "cash": 13429.130485,
                "equity": 13429.13,
                "realized_today": 48.63,
                "realized_total": -514.18,
                "positions": {},
                "source": "independently_clean_flat_v4_state_with_unresolved_canonical_projection_archived",
                "fabricated_exit_rows": 0,
            },
        },
        "issue222_verified_flat_successor": {
            "status": "validation_hold",
            "prior_epoch_id": accounting.ISSUE222_V4_EPOCH_ID,
            "target_epoch_id": accounting.ISSUE222_V5_EPOCH_ID,
            "unresolved_prior_discrepancy": True,
            "prior_epoch_economics_promotable": False,
            "fabricated_exit_rows": 0,
            "risk_halt_cleared": False,
            "canonical_history_rewritten": False,
        },
        "positions": {},
        "trades": [],
        "performance": {"open_positions": {}, "unrealized_pnl": 0.0},
        "risk_controls": {
            "halted": True,
            "halt_reason": accounting.ISSUE222_HALT_REASON,
            "cooldowns": {},
        },
    })
    return core


class Issue126SuccessorAccountingBoundaryTests(unittest.TestCase):
    def test_read_only_status_preserves_successor_and_discrepancy_contract(self):
        core = _issue222_v5_core()
        original_status_payload = accounting.status_payload
        try:
            readonly_status.apply(core)
            status = accounting.status_payload(core)
        finally:
            accounting.status_payload = original_status_payload

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(status["overall"], "pass")
        self.assertTrue(status["successor_accounting_read_only"])
        self.assertTrue(status["successor_validation_hold_read_only"])
        self.assertFalse(status["automatic_repair_suppressed"])
        self.assertEqual(status["discrepancy_count_before_repair"], 0)
        self.assertEqual(status["discrepancy_count_remaining"], 0)

    def test_exact_issue222_v5_zero_trade_baseline_is_complete_read_only_evidence(self):
        core = _issue222_v5_core()

        status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(status["overall"], "pass")
        self.assertTrue(status["coverage_complete"])
        self.assertFalse(status["repaired"])
        self.assertTrue(status["successor_accounting_read_only"])
        self.assertEqual(status["discrepancy_count_remaining"], 0)
        self.assertEqual(
            status["reconstructed"]["coverage_basis"],
            "verified_flat_successor_zero_trade_baseline",
        )
        self.assertEqual(status["reconstructed"]["parsed_trade_rows"], 0)
        self.assertFalse(status["reconstructed"]["prior_epoch_economics_promotable"])
        self.assertEqual(status["reconstructed"]["fabricated_exit_rows"], 0)

    def test_runtime_bidirectional_owner_preserves_exact_issue222_v5_baseline(self):
        core = _issue222_v5_core()

        rebuilt = bidirectional.analyze_ledger(core.portfolio, core)

        self.assertEqual(rebuilt["status"], "ok")
        self.assertTrue(rebuilt["coverage_complete"])
        self.assertEqual(rebuilt["coverage_issue_count"], 0)
        self.assertEqual(rebuilt["economic_issue_count"], 0)
        self.assertEqual(rebuilt["accounting_model"], "bidirectional_margin_v1")
        self.assertEqual(
            rebuilt["coverage_basis"],
            "verified_flat_successor_zero_trade_baseline",
        )

    def test_runtime_bidirectional_owner_keeps_drift_unavailable(self):
        core = _issue222_v5_core()
        core.portfolio["risk_controls"].update({"halted": False})

        rebuilt = bidirectional.analyze_ledger(core.portfolio, core)

        self.assertEqual(rebuilt["status"], "unavailable")
        self.assertFalse(rebuilt["coverage_complete"])

    def test_issue222_v5_zero_trade_baseline_drift_remains_unavailable(self):
        mutations = (
            ("epoch validation hold", lambda pf: pf["paper_accounting_epoch"].__setitem__("validation_hold", False)),
            ("snapshot cash", lambda pf: pf["paper_accounting_epoch"]["verified_snapshot_baseline"].__setitem__("cash", 13000.0)),
            ("prior promotable", lambda pf: pf["paper_accounting_epoch"].__setitem__("prior_epoch_economics_promotable", True)),
            ("fabricated exit", lambda pf: pf["paper_accounting_epoch"].__setitem__("fabricated_exit_rows", 1)),
            ("halt released", lambda pf: pf["risk_controls"].__setitem__("halted", False)),
            ("position present", lambda pf: pf.__setitem__("positions", {"ACHR": {"shares": 1}})),
            ("trades malformed", lambda pf: pf.__setitem__("trades", {})),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                core = _issue222_v5_core()
                mutate(core.portfolio)
                rebuilt = accounting.reconstruct_from_ledger(core.portfolio, core)
                self.assertEqual(rebuilt["status"], "unavailable")
                self.assertEqual(rebuilt["reason"], "trade_ledger_empty")
                self.assertFalse(rebuilt["coverage_complete"])

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

    def test_released_v3_successor_remains_read_only(self):
        core = FakeCore(epoch_id="stable-paper-v3-20260825-successor01", validation_hold=False)
        before = copy.deepcopy(core.portfolio)

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=PRE_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(core.portfolio["cash"], before["cash"])
        self.assertEqual(core.portfolio["positions"], before["positions"])
        self.assertFalse(status["repaired"])
        self.assertTrue(status["successor_accounting_read_only"])
        self.assertTrue(status["successor_validation_hold_read_only"])
        self.assertTrue(status["automatic_repair_suppressed"])

    def test_released_v4_successor_remains_read_only(self):
        core = FakeCore(epoch_id="stable-paper-v4-20260826-successor01", validation_hold=False)
        before = copy.deepcopy(core.portfolio)

        with mock.patch.object(accounting, "reconstruct_from_ledger", return_value=PRE_EXIT_RECONSTRUCTION):
            status = accounting.reconcile(core, persist=True)

        self.assertEqual(core.save_calls, 0)
        self.assertEqual(core.portfolio["cash"], before["cash"])
        self.assertEqual(core.portfolio["positions"], before["positions"])
        self.assertFalse(status["repaired"])
        self.assertTrue(status["successor_accounting_read_only"])
        self.assertTrue(status["automatic_repair_suppressed"])
        self.assertEqual(status["overall"], "warn")


if __name__ == "__main__":
    unittest.main()
