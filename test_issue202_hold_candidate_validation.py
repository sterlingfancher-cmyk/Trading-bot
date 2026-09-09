import unittest
from unittest.mock import patch

import performance_audit_lab_v2 as lab
import performance_audit_v2_async_route as resumable


class HoldCandidateValidationTests(unittest.TestCase):
    def test_resumable_ablation_binds_validation_to_frozen_candidate(self):
        frozen_map = {"neutral": {"max_hold_days": 10}}
        dynamic_best_map = {"neutral": {"max_positions": 2}}
        variants = {
            "max_positions_2": dynamic_best_map,
            lab.hold_shadow.CANDIDATE_ID: frozen_map,
        }
        rows = {
            "max_positions_2": {"variant": "max_positions_2", "objective": 9.0},
            lab.hold_shadow.CANDIDATE_ID: {
                "variant": lab.hold_shadow.CANDIDATE_ID,
                "objective": 1.0,
            },
        }
        core = type("Core", (), {"portfolio": {}})()
        with patch.object(lab, "_universe", return_value=["SPY"] * 10), patch.object(
            lab.base, "_download", return_value=({"SPY": object()}, {"status": "ok"})
        ), patch.object(
            lab.base,
            "_feature_frames",
            return_value={f"SYM{index}": object() for index in range(10)},
        ), patch.object(
            lab, "_add_liquidity_features"
        ), patch.object(
            lab.base, "_calendar", return_value=list(range(315))
        ), patch.object(
            lab, "_ablation_maps", return_value=variants
        ), patch.object(
            resumable, "_ablation_row", side_effect=lambda name, *args: rows[name]
        ), patch.object(
            resumable, "_heartbeat"
        ), patch.object(
            lab, "_simulate_next_open", return_value={"metrics": {"status": "ok"}}
        ) as simulate, patch.object(
            lab,
            "_candidate_validation",
            return_value={"status": "complete", "sensitivity": {"status": "complete"}},
        ) as validate:
            result = resumable._run_resumable_ablation(
                core,
                "5y",
                45,
                {"profiles": {"adaptive_balanced": {"full_sample": {}}}},
            )

        self.assertEqual(result["best_variant"]["variant"], "max_positions_2")
        self.assertEqual(result["current_full_sample_best_variant"], "max_positions_2")
        self.assertEqual(result["selected_candidate"], "hold_10d")
        self.assertEqual(result["selection_frozen_date"], "2026-09-09")
        self.assertIs(result["selected_candidate_validation"], result["best_variant_validation"])
        self.assertIs(validate.call_args.args[2], frozen_map)
        self.assertNotEqual(validate.call_args.args[2], dynamic_best_map)
        self.assertEqual(validate.call_args.kwargs["baseline_simulation"], {"metrics": {"status": "ok"}})
        simulate.assert_called_once()

    def test_resumable_ablation_fails_closed_when_frozen_candidate_is_missing(self):
        core = type("Core", (), {"portfolio": {}})()
        with patch.object(lab, "_universe", return_value=["SPY"] * 10), patch.object(
            lab.base, "_download", return_value=({"SPY": object()}, {"status": "ok"})
        ), patch.object(
            lab.base,
            "_feature_frames",
            return_value={f"SYM{index}": object() for index in range(10)},
        ), patch.object(
            lab, "_add_liquidity_features"
        ), patch.object(
            lab.base, "_calendar", return_value=list(range(315))
        ), patch.object(
            lab, "_ablation_maps", return_value={"max_positions_2": {"neutral": {}}}
        ), patch.object(
            resumable,
            "_ablation_row",
            return_value={"variant": "max_positions_2", "objective": 9.0},
        ), patch.object(resumable, "_heartbeat"):
            result = resumable._run_resumable_ablation(
                core,
                "5y",
                45,
                {"profiles": {"adaptive_balanced": {"full_sample": {}}}},
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "frozen_candidate_map_missing")
        self.assertFalse(result["automatic_promotion"])

    def test_candidate_validation_is_historical_and_never_promotes(self):
        simulation = {"metrics": {"status": "ok", "total_return_pct": 12.0}}
        with patch.object(lab, "_simulate_next_open", return_value=simulation), patch.object(
            lab, "_execution_diagnostics", return_value={"status": "complete"}
        ), patch.object(
            lab, "_sensitivity_report", return_value={"status": "complete"}
        ), patch.object(
            lab, "_calendar_years", return_value={"2026": {"status": "ok"}}
        ), patch.object(
            lab, "_regime_report", return_value={"risk_on": {"status": "ok"}}
        ), patch.object(
            lab,
            "_walk_forward",
            return_value={"status": "complete", "formal_walk_forward_passed": True},
        ) as walk_forward:
            result = lab._candidate_validation({}, [], {"neutral": {}})

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["candidate_id"], "hold_10d")
        self.assertTrue(result["candidate_selected_on_full_sample"])
        self.assertFalse(result["untouched_holdout_after_selection"])
        self.assertTrue(result["requires_forward_shadow_confirmation"])
        self.assertFalse(result["automatic_promotion"])
        self.assertIn("forward_shadow", result)
        walk_forward.assert_called_once_with({}, {"neutral": {}}, [], optimize=False)

    def test_missing_candidate_validation_fails_closed(self):
        result = {
            "profiles": {
                name: {
                    "execution_diagnostics": {
                        "status": "complete", "capacity": {"status": "complete"}
                    },
                    "sensitivity": {
                        "cost_scenarios": [{}] * len(lab.COST_SENSITIVITY_BPS),
                        "delay_scenarios": [{}] * len(lab.DELAY_SENSITIVITY_SESSIONS),
                    },
                }
                for name in (
                    "current_proxy", "balanced_static", "permissive", "adaptive_balanced"
                )
            },
            "ablation": {
                "status": "ok",
                "best_variant": {"execution_diagnostics": {"status": "complete"}},
                "best_variant_sensitivity": {"status": "complete"},
            },
        }
        verdict = lab._validation_verdict(result)
        self.assertFalse(verdict["candidate_historical_validation_complete"])
        self.assertIn("ablation.best_variant_validation", verdict["missing_or_incomplete"])


if __name__ == "__main__":
    unittest.main()
