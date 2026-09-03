from __future__ import annotations

import copy
import unittest

from shadow_ai_outcome_memory import (
    DERIVATION_VERSION,
    OutcomeMemoryConfig,
    build_counterfactual_scorecards,
    build_outcome_memory,
    find_comparable_outcomes,
)


def _outcome(execution_id: str = "entry-1", **overrides):
    row = {
        "canonical_execution_id": execution_id,
        "canonical_source_ids": [execution_id, f"exit-{execution_id}"],
        "canonical_evidence_status": "valid",
        "path_source_id": f"path-{execution_id}",
        "path_integrity_status": "valid",
        "path_training_eligible": True,
        "symbol": "CRWD",
        "side": "long",
        "strategy": "breakout",
        "setup_family": "continuation",
        "regime": "risk_on",
        "sector": "technology",
        "bucket": "growth",
        "volatility_state": "normal",
        "signal_characteristics": ["relative_volume", "new_high"],
        "session_phase": "morning",
        "calendar_segment": "2026-09",
        "exit_reason": "trailing_stop",
        "realized_return_pct": 2.5,
        "mfe_pct": 4.0,
        "mae_pct": -0.8,
        "entry_notional_usd": 1000.0,
        "holding_period_seconds": 7200,
    }
    row.update(overrides)
    return row


def _review(candidate: str = "CRWD:long:a", decision: str = "reject", cost=0.25):
    return {
        "join_eligible": True,
        "cycle_id": "cycle-1",
        "candidate_id": candidate,
        "input_fingerprint": "fingerprint-1",
        "rules_decision": "enter",
        "result": {
            "decision": decision,
            "confidence": 0.8,
            "telemetry": {"cost_usd_exact": cost},
        },
    }


def _binding(candidate: str = "CRWD:long:a", execution_id: str = "entry-1"):
    return {
        "cycle_id": "cycle-1",
        "candidate_id": candidate,
        "input_fingerprint": "fingerprint-1",
        "canonical_execution_id": execution_id,
    }


class ShadowAIOutcomeMemoryTests(unittest.TestCase):
    def test_memory_is_read_only_bounded_and_rebuildable(self):
        rows = [_outcome()]
        before = copy.deepcopy(rows)
        first = build_outcome_memory(rows)
        second = build_outcome_memory(copy.deepcopy(rows))
        self.assertEqual(rows, before)
        self.assertEqual(first, second)
        self.assertEqual(first["accepted_count"], 1)
        self.assertEqual(first["records"][0]["derivation_version"], DERIVATION_VERSION)
        self.assertTrue(first["authority"]["canonical_sources_read_only"])
        self.assertFalse(first["authority"]["execution_input"])

    def test_memory_fails_closed_on_invalid_evidence(self):
        cases = [
            ({"canonical_execution_id": ""}, "missing_required_fields"),
            ({"canonical_source_ids": ["exit-entry-1"]}, "canonical_source_ids_do_not_include_primary"),
            ({"canonical_evidence_status": "unknown"}, "canonical_evidence_not_valid"),
            ({"path_integrity_status": "quarantined"}, "path_evidence_not_eligible"),
            ({"path_training_eligible": False}, "path_evidence_not_eligible"),
            ({"realized_return_pct": float("nan")}, "invalid_realized_return_pct"),
            ({"mfe_pct": -0.1}, "invalid_mfe_pct"),
            ({"mae_pct": 0.1}, "invalid_mae_pct"),
            ({"entry_notional_usd": 0}, "invalid_entry_notional_usd"),
            ({"holding_period_seconds": -1}, "invalid_holding_period_seconds"),
        ]
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                payload = build_outcome_memory([_outcome(**overrides)])
                self.assertEqual(payload["accepted_count"], 0)
                self.assertEqual(payload["excluded_count"], 1)
                self.assertIn(reason, payload["exclusions"][0]["reason"])

    def test_duplicate_identical_row_is_deduplicated(self):
        row = _outcome()
        payload = build_outcome_memory([row, copy.deepcopy(row)])
        self.assertEqual(payload["accepted_count"], 1)
        self.assertEqual(payload["excluded_count"], 0)

    def test_duplicate_contradictory_execution_id_is_fully_excluded(self):
        payload = build_outcome_memory([_outcome(), _outcome(realized_return_pct=-2.0)])
        self.assertEqual(payload["accepted_count"], 0)
        self.assertEqual(
            payload["exclusions"][0]["reason"],
            "contradictory_rows_for_canonical_execution_id",
        )

    def test_memory_retention_is_bounded(self):
        rows = [_outcome(f"entry-{index}") for index in range(3)]
        payload = build_outcome_memory(rows, OutcomeMemoryConfig(max_records=2))
        self.assertEqual(payload["accepted_count"], 2)
        self.assertEqual(payload["truncated_count"], 1)

    def test_comparables_require_side_and_rank_deterministically(self):
        rows = [
            _outcome("entry-z", strategy="mean_reversion", signal_characteristics=["oversold"]),
            _outcome("entry-a"),
            _outcome("entry-short", side="short"),
        ]
        context = {
            "side": "long",
            "strategy": "breakout",
            "setup_family": "continuation",
            "regime": "risk_on",
            "sector": "TECHNOLOGY",
            "bucket": "growth",
            "volatility_state": "normal",
            "session_phase": "morning",
            "signal_characteristics": ["relative_volume", "new_high"],
        }
        memory = build_outcome_memory(rows)
        comparables = find_comparable_outcomes(memory, context)
        self.assertEqual(
            [row["canonical_execution_id"] for row in comparables],
            ["entry-a", "entry-z"],
        )
        self.assertEqual(comparables[0]["comparison_score"], 1.0)
        self.assertEqual(find_comparable_outcomes(memory, {"side": "unknown"}), ())

    def test_scorecard_exact_join_subtracts_inference_cost(self):
        payload = build_counterfactual_scorecards(
            build_outcome_memory([_outcome()]), [_review()], [_binding()]
        )
        aggregate = payload["aggregate"]
        self.assertEqual(payload["joined_count"], 1)
        self.assertEqual(aggregate["rules_realized_pnl_usd"], 25.0)
        self.assertEqual(aggregate["ai_counterfactual_pnl_usd"], 0.0)
        self.assertEqual(aggregate["incremental_pnl_before_cost_usd"], -25.0)
        self.assertEqual(aggregate["incremental_pnl_net_cost_usd"], -25.25)
        self.assertEqual(aggregate["conclusion"], "inconclusive")
        self.assertFalse(aggregate["automatic_promotion"])

    def test_agreement_preserves_rules_result_but_cost_is_incrementally_negative(self):
        payload = build_counterfactual_scorecards(
            build_outcome_memory([_outcome(realized_return_pct=-1.0)]),
            [_review(decision="agree", cost=0.1)],
            [_binding()],
        )
        aggregate = payload["aggregate"]
        self.assertEqual(aggregate["rules_realized_pnl_usd"], -10.0)
        self.assertEqual(aggregate["ai_counterfactual_pnl_usd"], -10.0)
        self.assertEqual(aggregate["incremental_pnl_net_cost_usd"], -0.1)
        self.assertIn("agree", payload["segments"]["agreement_state"])

    def test_scorecard_fails_closed_without_exact_join(self):
        cases = [
            ([_review()], [], "missing_or_contradictory_execution_binding"),
            ([_review()], [_binding(), _binding(execution_id="entry-2")], "missing_or_contradictory_execution_binding"),
            ([{**_review(), "join_eligible": False}], [_binding()], "review_not_join_eligible"),
            ([_review()], [_binding(execution_id="missing")], "canonical_outcome_missing"),
            ([{**_review(), "rules_decision": "reject"}], [_binding()], "nonexecuted_rules_decision"),
            ([_review(), _review()], [_binding()], "duplicate_review_identity"),
        ]
        memory = build_outcome_memory([_outcome()])
        for reviews, bindings, reason in cases:
            with self.subTest(reason=reason):
                payload = build_counterfactual_scorecards(memory, reviews, bindings)
                self.assertEqual(payload["joined_count"], 0)
                self.assertEqual(payload["exclusions"][0]["reason"], reason)

    def test_scorecard_revalidates_memory_and_rejects_untrusted_payload(self):
        payload = build_counterfactual_scorecards(
            {"version": "forged", "records": [_outcome()]},
            [_review()],
            [_binding()],
        )
        self.assertEqual(payload["joined_count"], 0)
        self.assertEqual(payload["exclusions"][0]["reason"], "memory_version_untrusted")

    def test_missing_exact_cost_keeps_net_metrics_inconclusive(self):
        payload = build_counterfactual_scorecards(
            build_outcome_memory([_outcome()]),
            [_review(cost=None)],
            [_binding()],
            OutcomeMemoryConfig(min_scorecard_samples=2),
        )
        aggregate = payload["aggregate"]
        self.assertFalse(aggregate["exact_cost_coverage_complete"])
        self.assertIsNone(aggregate["inference_cost_usd"])
        self.assertIsNone(aggregate["incremental_pnl_net_cost_usd"])
        self.assertEqual(aggregate["conclusion"], "inconclusive")

    def test_sufficient_diverse_sample_remains_observational_only(self):
        outcomes, reviews, bindings = [], [], []
        for index in range(4):
            execution_id = f"entry-{index}"
            candidate = f"candidate-{index}"
            outcomes.append(_outcome(execution_id, symbol=f"SYM{index}"))
            review = _review(candidate, decision="reject", cost=0.01)
            review["cycle_id"] = f"cycle-{index}"
            review["input_fingerprint"] = f"fingerprint-{index}"
            binding = _binding(candidate, execution_id)
            binding["cycle_id"] = f"cycle-{index}"
            binding["input_fingerprint"] = f"fingerprint-{index}"
            reviews.append(review)
            bindings.append(binding)
        payload = build_counterfactual_scorecards(
            build_outcome_memory(outcomes),
            reviews,
            bindings,
            OutcomeMemoryConfig(min_scorecard_samples=4, max_symbol_concentration=0.5),
        )
        self.assertEqual(payload["aggregate"]["conclusion"], "observational_only")
        self.assertFalse(payload["authority"]["automatic_promotion"])
        self.assertFalse(payload["authority"]["changes_rule_decisions"])

    def test_config_and_limit_bounds_fail_closed(self):
        with self.assertRaises(ValueError):
            OutcomeMemoryConfig(max_records=0)
        with self.assertRaises(ValueError):
            find_comparable_outcomes(build_outcome_memory([]), {"side": "long"}, limit=0)


if __name__ == "__main__":
    unittest.main()
