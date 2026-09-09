import unittest
from unittest.mock import patch

import performance_audit_lab_v2 as lab


class HoldCandidateValidationTests(unittest.TestCase):
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
