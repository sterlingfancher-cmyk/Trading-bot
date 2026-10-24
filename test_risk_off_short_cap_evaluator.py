import copy
import unittest

from risk_off_short_cap_evaluator import evaluate_risk_off_short_cap


EPOCH = "stable-paper-v5"


def lifecycle(path, session, entry_time, pnl, *, partition="research", eligible=True, costs=True):
    return {
        "execution_path_id": path,
        "accounting_epoch_id": EPOCH,
        "session_date": session,
        "entry_time": entry_time,
        "side": "short",
        "entry_market_mode": "risk_off",
        "net_pnl_after_costs": pnl,
        "gross_entry_notional": 1000.0,
        "partition": partition,
        "outcome_complete": True,
        "integrity_eligible": eligible,
        "integrity_exclusion_reason": None if eligible else "suspect_price",
        "cost_coverage_complete": costs,
    }


def coverage(session, *, complete=True):
    return {
        "accounting_epoch_id": EPOCH,
        "session_date": session,
        "complete_entry_universe": complete,
        "complete_exit_outcomes": complete,
        "cost_coverage_complete": complete,
    }


class RiskOffShortCapEvaluatorTests(unittest.TestCase):
    def evaluate(self, rows, sessions, **kwargs):
        return evaluate_risk_off_short_cap(
            lifecycles=rows,
            session_coverage=sessions,
            accounting_epoch_id=EPOCH,
            **kwargs,
        )

    def test_cap_admits_first_chronological_lifecycle_only(self):
        rows = [
            lifecycle("SECOND", "2026-10-22", 2, -75.68),
            lifecycle("FIRST", "2026-10-22", 1, 18.72),
            lifecycle("THIRD", "2026-10-22", 3, -33.10),
        ]
        original = copy.deepcopy(rows)
        result = self.evaluate(rows, [coverage("2026-10-22")])
        self.assertEqual(result["candidate_admitted_path_ids"], ["FIRST"])
        self.assertEqual(result["candidate_skipped_path_ids"], ["SECOND", "THIRD"])
        self.assertEqual(result["baseline"]["net_pnl_after_costs"], -90.06)
        self.assertEqual(result["candidate"]["net_pnl_after_costs"], 18.72)
        self.assertEqual(result["verdict"], "insufficient_evidence")
        self.assertEqual(rows, original)
        self.assertFalse(result["guardrails"]["source_rows_mutated"])

    def test_suspect_outcome_is_preserved_as_exclusion_not_candidate_gain(self):
        rows = [lifecycle("SNOW-SUSPECT", "2026-10-16", 1, -723.82, eligible=False)]
        result = self.evaluate(rows, [coverage("2026-10-16")])
        self.assertEqual(result["baseline"]["completed_lifecycles"], 0)
        self.assertEqual(result["exclusions"][0]["canonical_net_pnl_after_costs"], -723.82)
        self.assertIn("suspect_price", result["exclusions"][0]["reasons"])
        self.assertTrue(result["exclusions"][0]["canonical_outcome_preserved"])

    def test_missing_session_or_cost_coverage_fails_closed(self):
        rows = [lifecycle("A", "2026-10-22", 1, -1.0, costs=False)]
        result = self.evaluate(rows, [coverage("2026-10-22", complete=False)])
        reasons = result["exclusions"][0]["reasons"]
        self.assertIn("missing_fee_or_slippage_coverage", reasons)
        self.assertIn("session_coverage:complete_entry_universe", reasons)
        self.assertEqual(result["verdict"], "insufficient_evidence")

    def test_cross_epoch_and_non_target_rows_do_not_contaminate_cohort(self):
        cross = lifecycle("OLD", "2026-10-21", 1, 500.0)
        cross["accounting_epoch_id"] = "prior-epoch"
        long_row = lifecycle("LONG", "2026-10-22", 1, 100.0)
        long_row["side"] = "long"
        neutral = lifecycle("NEUTRAL", "2026-10-22", 2, 100.0)
        neutral["entry_market_mode"] = "neutral"
        result = self.evaluate([cross, long_row, neutral], [coverage("2026-10-22")])
        self.assertEqual(result["coverage"]["eligible_lifecycles"], 0)
        all_reasons = {reason for item in result["exclusions"] for reason in item["reasons"]}
        self.assertTrue({"cross_epoch", "not_short", "not_risk_off_at_entry"}.issubset(all_reasons))

    def test_research_and_holdout_must_both_confirm_when_sample_gates_pass(self):
        rows = []
        sessions = []
        for index in range(20):
            day = f"2026-09-{index + 1:02d}"
            partition = "holdout" if index >= 15 else "research"
            rows.extend([
                lifecycle(f"{day}-FIRST", day, 1, 2.0, partition=partition),
                lifecycle(f"{day}-SECOND", day, 2, -1.0, partition=partition),
            ])
            sessions.append(coverage(day))
        result = self.evaluate(rows, sessions)
        self.assertEqual(result["verdict"], "candidate_improves_static_replay")
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["promotion_ready"])

    def test_only_cap_one_is_accepted(self):
        with self.assertRaisesRegex(ValueError, "exactly one variable"):
            self.evaluate([], [], cap_per_session=2)


if __name__ == "__main__":
    unittest.main()
