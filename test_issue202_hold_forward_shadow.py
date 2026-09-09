import json
import unittest
from pathlib import Path

import hold_period_forward_shadow as shadow


def _simulation(rows):
    return {"trades": rows}


def _lifecycle(symbol, entry_date, exit_date, exit_price, *, regime="neutral", reason="max_hold"):
    return [
        {
            "action": "entry",
            "symbol": symbol,
            "date": entry_date,
            "price": 100.0,
            "allocation": 1000.0,
            "regime": regime,
        },
        {
            "action": "exit",
            "symbol": symbol,
            "date": exit_date,
            "price": exit_price,
            "pnl": (exit_price - 100.0) * 10.0,
            "reason": reason,
            "entry_regime": regime,
        },
    ]


class HoldPeriodForwardShadowTests(unittest.TestCase):
    def test_contract_is_frozen_before_forward_observation(self):
        contract = json.loads(Path("hold_period_forward_shadow_contract.json").read_text())
        self.assertEqual(contract["version"], shadow.VERSION)
        self.assertEqual(contract["candidate_id"], "hold_10d")
        self.assertEqual(contract["freeze_date"], "2026-09-09")
        self.assertTrue(contract["candidate_frozen_before_observation"])
        self.assertEqual(contract["criteria"], shadow.CRITERIA)
        self.assertFalse(contract["criteria"]["automatic_promotion"])
        self.assertFalse(contract["authority"]["changes_runtime_exits"])

    def test_exact_post_freeze_lifecycles_are_compared(self):
        baseline = _simulation(_lifecycle("MU", "2026-09-09", "2026-09-16", 102.0))
        candidate = _simulation(_lifecycle("MU", "2026-09-09", "2026-09-18", 106.0))
        report = shadow.build_report(
            baseline,
            candidate,
            ["2026-09-09", "2026-09-10", "2026-09-18"],
            stress_baseline_simulation=baseline,
            stress_candidate_simulation=candidate,
        )
        self.assertEqual(report["exact_matched_completed_lifecycles"], 1)
        self.assertEqual(report["exit_divergences"], 1)
        self.assertEqual(report["mean_return_delta_pct"], 4.0)
        self.assertEqual(report["by_regime"]["neutral"]["observations"], 1)
        self.assertFalse(report["all_criteria_met"])
        self.assertFalse(report["automatic_promotion"])

    def test_pre_freeze_rows_never_enter_forward_sample(self):
        rows = _lifecycle("MU", "2026-09-08", "2026-09-16", 102.0)
        report = shadow.build_report(_simulation(rows), _simulation(rows), ["2026-09-09"])
        self.assertEqual(report["exact_matched_completed_lifecycles"], 0)
        self.assertEqual(report["status"], "collecting")

    def test_ambiguous_entries_fail_closed(self):
        baseline_rows = _lifecycle("MU", "2026-09-09", "2026-09-16", 102.0)
        candidate_rows = _lifecycle("MU", "2026-09-09", "2026-09-18", 106.0)
        candidate_rows += _lifecycle("MU", "2026-09-09", "2026-09-19", 107.0)
        report = shadow.build_report(
            _simulation(baseline_rows),
            _simulation(candidate_rows),
            ["2026-09-09", "2026-09-18"],
        )
        self.assertEqual(report["exact_matched_completed_lifecycles"], 0)
        self.assertEqual(report["status"], "inconclusive")
        self.assertFalse(report["integrity"]["eligible"])
        self.assertTrue(report["integrity"]["errors"])

    def test_unmatched_entries_are_disclosed_without_becoming_false_pairs(self):
        baseline_rows = _lifecycle("MU", "2026-09-09", "2026-09-16", 102.0)
        candidate_rows = _lifecycle("NVDA", "2026-09-09", "2026-09-18", 106.0)
        report = shadow.build_report(
            _simulation(baseline_rows),
            _simulation(candidate_rows),
            ["2026-09-09", "2026-09-18"],
        )
        self.assertEqual(report["exact_matched_completed_lifecycles"], 0)
        self.assertEqual(report["coverage"]["unmatched_completed_entries"], 2)
        self.assertEqual(report["status"], "collecting")
        self.assertFalse(report["all_criteria_met"])

    def test_runtime_and_trading_authority_are_explicitly_absent(self):
        report = shadow.build_report({}, {}, [])
        authority = report["authority"]
        self.assertTrue(authority["isolated_research_only"])
        self.assertTrue(authority["read_only_comparator"])
        self.assertFalse(authority["writes_production_state"])
        self.assertFalse(authority["changes_runtime_exits"])
        self.assertFalse(authority["places_or_cancels_orders"])
        self.assertFalse(report["automatic_promotion"])


if __name__ == "__main__":
    unittest.main()
