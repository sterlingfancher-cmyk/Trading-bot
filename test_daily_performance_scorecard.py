import copy
import unittest

from daily_performance_scorecard import build_session_scorecard, upsert_scorecard


EPOCH = "successor-epoch"


def row(action, path, execution_id, pnl=None, side="short", session="2026-10-22"):
    payload = {
        "accounting_epoch_id": EPOCH,
        "session_date": session,
        "action": action,
        "execution_path_id": path,
        "execution_id": execution_id,
        "symbol": path.split("|")[0],
        "side": side,
        "price": 10.0,
        "time": len(execution_id),
    }
    if pnl is not None:
        payload["pnl_dollars"] = pnl
    return payload


class DailyPerformanceScorecardTests(unittest.TestCase):
    def build(self, rows, excluded=(), expected=None, snapshot=None):
        if snapshot is None:
            snapshot = {
                "canonical_daily_pnl": 0.0,
                "equity": 10000.0,
                "unrealized_pnl": 0.0,
                "gross_exposure": 0.0,
                "fee_slippage_coverage": "not_recorded_by_paper_provider",
            }
        return build_session_scorecard(
            session_date="2026-10-22",
            observed_at="2026-10-23T14:01:50-05:00",
            accounting_epoch_id=EPOCH,
            journal_rows=rows,
            provenance={"source": "/paper/journal-truth-status", "digest": "abc"},
            excluded_execution_path_ids=excluded,
            account_snapshot=snapshot,
            expected_execution_count=expected,
        )

    def test_partial_exit_is_part_of_one_completed_lifecycle(self):
        path = "MOD|short|1|10.0"
        result = self.build([
            row("entry", path, "e"),
            row("partial_exit", path, "p", 3.0),
            row("exit", path, "x", 7.0),
        ], expected=3)
        self.assertEqual(result["canonical_reporting"]["completed_matched_trades"], 1)
        self.assertEqual(result["canonical_reporting"]["wins"], 1)
        self.assertEqual(result["canonical_reporting"]["realized_pnl"], 10.0)
        self.assertEqual(result["event_counts"]["partial_exits"], 1)
        self.assertEqual(
            result["canonical_reporting"]["completed_trade_lifecycles"][0]["execution_ids"],
            ["e", "p", "x"],
        )

    def test_suspect_lifecycle_remains_canonical_but_is_research_excluded(self):
        suspect = "SNOW|short|1|310.8"
        valid = "TTMI|short|2|71.945"
        result = self.build([
            row("entry", suspect, "se"), row("exit", suspect, "sx", -723.82),
            row("entry", valid, "ve"), row("exit", valid, "vx", -33.10),
        ], excluded=[suspect])
        self.assertEqual(result["canonical_reporting"]["realized_pnl"], -756.92)
        self.assertEqual(result["eligible_research_metrics"]["realized_pnl"], -33.10)
        self.assertEqual(len(result["research_exclusions"]), 1)
        self.assertEqual(result["loss_driver_classification"]["proven"][0]["category"], "bad_data_or_execution")

    def test_does_not_mutate_rows_or_infer_pnl_from_equity(self):
        rows = [row("entry", "A|long|1|10", "a", side="long")]
        before = copy.deepcopy(rows)
        result = self.build(rows, snapshot={"equity": 12000})
        self.assertEqual(rows, before)
        self.assertIsNone(result["canonical_reporting"]["canonical_daily_pnl"])
        self.assertTrue(result["guardrails"]["balance_change_used_as_pnl"] is False)
        self.assertFalse(result["session_completeness"]["complete"])
        self.assertFalse(result["session_completeness"]["execution_lifecycle_complete"])
        self.assertIn("canonical_daily_pnl", result["session_completeness"]["missing_fields"])
        self.assertEqual(result["session_completeness"]["open_execution_path_ids"], ["A|long|1|10"])
        self.assertEqual(result["session_completeness"]["unmatched_execution_path_ids"], [])

    def test_upsert_retains_prior_observations_and_exposes_missing_sessions(self):
        first = self.build([row("entry", "A|long|1|10", "a", side="long"), row("exit", "A|long|1|10", "b", 2, side="long")])
        first["session_date"] = "2026-10-20"
        replacement = copy.deepcopy(first)
        replacement["eligible_research_metrics"]["realized_pnl"] = 3.0
        complete_snapshot = {
            "canonical_daily_pnl": -1,
            "equity": 9999,
            "unrealized_pnl": 0,
            "gross_exposure": 0,
            "fees": 0,
            "slippage": 0,
            "fee_slippage_coverage": "complete",
        }
        current = self.build(
            [row("entry", "B|short|1|10", "c"), row("exit", "B|short|1|10", "d", -1)],
            expected=2,
            snapshot=complete_snapshot,
        )
        first["session_completeness"]["complete"] = True
        replacement["session_completeness"]["complete"] = True
        checkpoint = upsert_scorecard({}, first, ["2026-10-20", "2026-10-21", "2026-10-22"])
        checkpoint = upsert_scorecard(checkpoint, replacement, ["2026-10-20", "2026-10-21", "2026-10-22"])
        checkpoint = upsert_scorecard(checkpoint, current, ["2026-10-20", "2026-10-21", "2026-10-22"])
        self.assertEqual(len(checkpoint["observations"]), 2)
        self.assertEqual(checkpoint["observations"][0]["eligible_research_metrics"]["realized_pnl"], 3.0)
        self.assertEqual(checkpoint["missing_sessions"], ["2026-10-21"])
        self.assertEqual(checkpoint["rolling_5_session"]["available_comparable_sessions"], 2)
        self.assertTrue(checkpoint["rolling_20_session"]["insufficient_for_full_window"])

    def test_cross_epoch_observation_is_not_in_rolling_sample(self):
        current = self.build(
            [row("entry", "B|short|1|10", "c"), row("exit", "B|short|1|10", "d", -1)],
            expected=2,
            snapshot={
                "canonical_daily_pnl": -1,
                "equity": 9999,
                "unrealized_pnl": 0,
                "gross_exposure": 0,
                "fees": 0,
                "slippage": 0,
                "fee_slippage_coverage": "complete",
            },
        )
        other = copy.deepcopy(current)
        other["session_date"] = "2026-10-21"
        other["accounting_epoch_id"] = "prior-epoch"
        checkpoint = upsert_scorecard({"observations": [other]}, current, ["2026-10-21", "2026-10-22"])
        self.assertEqual(checkpoint["rolling_5_session"]["available_comparable_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
