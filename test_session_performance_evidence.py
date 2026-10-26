import copy
import hashlib
import json
import unittest

from session_performance_evidence import build_session_evidence


EPOCH = "successor-v1"
DAY = "2026-10-23"


def ledger_rows(events):
    rows = []
    previous = ""
    for index, event in enumerate(events, start=1):
        body = {
            "execution_id": f"e{index}",
            "ledger_version": "test",
            "recorded_local": f"{DAY} 1{index}:00:00",
            "accounting_epoch_id": EPOCH,
            **event,
        }
        digest = hashlib.sha256((previous + "|" + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
        rows.append({**body, "previous_event_hash": previous, "event_hash": digest})
        previous = digest
    return rows


def journal_rows(ledger):
    return [
        {
            **row,
            "journal_source": "/app/data/state.json:trades",
            "session_date": DAY,
        }
        for row in ledger
    ]


def events(path="MOD|short|1|100"):
    return [
        {"action": "entry", "symbol": "MOD", "side": "short", "price": 100, "shares": 2, "execution_path_id": path},
        {"action": "partial_exit", "symbol": "MOD", "side": "short", "price": 98, "shares": 1, "execution_path_id": path, "pnl_dollars": 2},
        {"action": "exit", "symbol": "MOD", "side": "short", "price": 95, "shares": 1, "execution_path_id": path, "pnl_dollars": 5, "exit_reason": "structure"},
    ]


def close(epoch=EPOCH, observed="2026-10-23T16:01:00-05:00"):
    return {"observed_at": observed, "accounting_epoch_id": epoch, "equity": 10007, "unrealized_pnl": 0, "gross_exposure": 0}


class SessionPerformanceEvidenceTests(unittest.TestCase):
    def build(self, ledger, journal=None, observations=None, costs=None, suspect=()):
        return build_session_evidence(
            session_date=DAY,
            accounting_epoch_id=EPOCH,
            canonical_rows=ledger,
            journal_rows=journal if journal is not None else journal_rows(ledger),
            account_observations=observations if observations is not None else [close()],
            explicit_costs=costs,
            suspect_execution_path_ids=suspect,
            provenance={"artifact_run_id": 123, "digest": "abc"},
        )

    def test_exact_gross_lifecycle_and_costs_preserve_partial_exit_as_one_trade(self):
        ledger = ledger_rows(events())
        costs = {f"e{i}": {"fees": 0.10, "slippage": 0.05} for i in range(1, 4)}
        result = self.build(ledger, costs=costs)
        self.assertEqual(len(result["completed_lifecycles"]), 1)
        self.assertEqual(result["completed_lifecycles"][0]["partial_exit_count"], 1)
        self.assertEqual(result["gross_realized_pnl"], 7.0)
        self.assertEqual(result["net_pnl_after_costs"], 6.55)
        self.assertEqual(result["admission_order"]["scope"], "executed_admission_order_only")
        self.assertFalse(result["admission_order"]["complete_entry_universe"])
        self.assertFalse(result["research_eligibility"]["eligible"])

    def test_missing_costs_fail_closed_without_zero_assumption(self):
        result = self.build(ledger_rows(events()))
        self.assertFalse(result["cost_coverage_complete"])
        self.assertIsNone(result["net_pnl_after_costs"])
        self.assertTrue(any("costs_missing" in item for item in result["errors"]))
        self.assertFalse(result["guardrails"]["missing_costs_treated_as_zero"])

    def test_off_window_and_cross_epoch_close_are_rejected(self):
        ledger = ledger_rows(events())
        result = self.build(ledger, observations=[close(observed="2026-10-23T15:40:00-05:00"), close(epoch="prior")])
        self.assertIsNone(result["session_close"])
        self.assertIn("session_close_observation_missing", result["errors"])

    def test_duplicate_or_supplemental_journal_matches_fail_exact_join(self):
        ledger = ledger_rows(events())
        journal = journal_rows(ledger)
        journal.append({**journal[0], "journal_source": "function_hook:run_cycle:return"})
        result = self.build(ledger, journal=journal)
        self.assertTrue(any("journal_match_count:2" in item for item in result["errors"]))
        journal = journal_rows(ledger)
        journal[0]["journal_source"] = "function_hook:run_cycle:return"
        result = self.build(ledger, journal=journal)
        self.assertTrue(any("journal_source_not_state_primary" in item for item in result["errors"]))

    def test_hash_duplicate_epoch_mismatch_and_incomplete_lifecycle_fail_closed(self):
        ledger = ledger_rows(events())
        bad = copy.deepcopy(ledger)
        bad[1]["event_hash"] = "tampered"
        result = self.build(bad)
        self.assertFalse(result["canonical_chain"]["valid"])
        self.assertTrue(any("event_hash_mismatch" in item for item in result["errors"]))

        duplicate = copy.deepcopy(ledger)
        duplicate[1]["execution_id"] = duplicate[0]["execution_id"]
        result = self.build(duplicate)
        self.assertTrue(any("duplicate_execution_id" in item for item in result["errors"]))

        prior = copy.deepcopy(ledger)
        for row in prior:
            row["accounting_epoch_id"] = "prior"
        result = self.build(prior, journal=journal_rows(prior))
        self.assertEqual(result["execution_rows"], [])

        open_ledger = ledger_rows(events()[:2])
        result = self.build(open_ledger)
        self.assertTrue(any("incomplete_or_ambiguous_lifecycle" in item for item in result["errors"]))

    def test_suspect_path_remains_reported_but_research_excluded(self):
        path = "MOD|short|1|100"
        ledger = ledger_rows(events(path))
        result = self.build(ledger, suspect=[path])
        self.assertEqual(result["gross_realized_pnl"], 7.0)
        self.assertIsNone(result["eligible_gross_realized_pnl"])
        self.assertEqual(result["research_exclusions"][0]["execution_path_id"], path)
        self.assertFalse(result["guardrails"]["suspect_rows_deleted"])

    def test_inputs_are_not_mutated_and_daily_pnl_is_never_inferred(self):
        ledger = ledger_rows(events())
        journal = journal_rows(ledger)
        observations = [close()]
        before = copy.deepcopy((ledger, journal, observations))
        result = self.build(ledger, journal=journal, observations=observations)
        self.assertEqual((ledger, journal, observations), before)
        self.assertIsNone(result["canonical_daily_pnl"])
        self.assertFalse(result["guardrails"]["balance_change_used_as_pnl"])


if __name__ == "__main__":
    unittest.main()
