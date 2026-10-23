import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import journal_truth
import ml_pre3a_shadow_validation as ml_validation


def _snow_rows():
    return [
        {"action": "entry", "symbol": "SNOW", "side": "short", "time": 1.0, "price": 310.80, "shares": 3.323},
        {"action": "exit", "symbol": "SNOW", "side": "short", "time": 2.0, "price": 528.61, "shares": 3.323, "pnl_dollars": -723.82},
    ]


class Issue313SuspectOutcomeExclusionTests(unittest.TestCase):
    def test_suspect_exit_is_excluded_without_mutating_source_rows(self):
        rows = _snow_rows()
        before = copy.deepcopy(rows)

        eligible, excluded = journal_truth.partition_performance_exit_rows(rows)

        self.assertEqual(eligible, [])
        self.assertEqual(rows, before)
        self.assertIs(excluded[0]["row"], rows[1])
        integrity = excluded[0]["integrity"]
        self.assertEqual(integrity["reason"], "price_to_entry_outside_verification_envelope")
        self.assertEqual(round(integrity["price_to_entry_ratio"], 4), 1.7008)
        self.assertIs(integrity["canonical_row_preserved"], True)

    def test_plausible_exit_remains_performance_eligible(self):
        rows = [
            {"action": "entry", "symbol": "SNOW", "side": "short", "time": 1.0, "price": 310.80},
            {"action": "exit", "symbol": "SNOW", "side": "short", "time": 2.0, "price": 320.00, "pnl_dollars": -30.57},
        ]

        eligible, excluded = journal_truth.partition_performance_exit_rows(rows)

        self.assertEqual(eligible, [rows[1]])
        self.assertEqual(excluded, [])

    def test_journal_summary_preserves_accounting_but_marks_evidence_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"trades": _snow_rows(), "performance": {"realized_pnl_total": -723.82}}))
            with mock.patch.object(journal_truth, "STATE_FILE", str(state_path)):
                summary = journal_truth.execution_summary({"trades": []})

        self.assertEqual(summary["losses_count"], 1)
        self.assertEqual(summary["state_realized_pnl_total"], -723.82)
        self.assertEqual(summary["performance_evidence_status"], "inconclusive")
        self.assertEqual(summary["performance_eligible_exits_count"], 0)
        self.assertEqual(summary["performance_excluded_exits_count"], 1)
        self.assertIs(summary["performance_outcome_integrity_policy"]["immutable_source_rows_rewritten"], False)

    def test_ml_validation_cannot_qualify_suspect_outcome(self):
        state = {
            "trades": _snow_rows(),
            "ml_phase2": {
                "dataset": [{
                    "row_id": "snow-outcome",
                    "date": "2026-10-16",
                    "symbol": "SNOW",
                    "decision": "accepted",
                    "future_outcome_pending": False,
                    "future_win": False,
                    "future_pnl_dollars": -723.82,
                }]
            },
        }

        payload = ml_validation.payload(state)

        integrity_gate = next(g for g in payload["gates"] if g["name"] == "price_integrity_outcomes")
        self.assertIs(integrity_gate["passed"], False)
        self.assertIs(payload["phase3a_ready"], False)
        self.assertEqual(payload["execution_summary"]["raw_exit_outcomes"], 1)
        self.assertEqual(payload["execution_summary"]["observed_exit_outcomes"], 0)
        self.assertEqual(payload["execution_summary"]["excluded_exit_outcomes"], 1)
        self.assertIs(payload["scorecards"]["outcome_integrity_blocked"], True)
        self.assertIs(payload["scorecards"]["by_symbol"][0]["usable_for_weighting"], False)


if __name__ == "__main__":
    unittest.main()
