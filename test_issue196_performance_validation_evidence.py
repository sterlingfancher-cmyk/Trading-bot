import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import performance_audit_lab_v2 as lab


def _policy():
    return {
        "score_floor": 0.0,
        "min_confirmations": 0,
        "min_volume_ratio": 0.0,
        "min_relative_strength": -1.0,
        "require_ma50": False,
        "max_positions": 1,
        "target_allocation": 0.20,
        "max_exposure": 0.20,
        "stop_loss": 0.01,
        "max_hold_days": 5,
        "rebalance_days": 1,
        "allowed_symbols": None,
    }


class PerformanceValidationEvidenceTests(unittest.TestCase):
    def test_execution_diagnostics_cover_turnover_capacity_and_concentration(self):
        sim = {
            "dates": list(pd.date_range("2026-01-01", periods=252, freq="B")),
            "equity_curve": [10_000.0] * 252,
            "assumptions": {"transaction_cost_bps_per_side": 8.0},
            "trades": [
                {
                    "action": "entry", "symbol": "NVDA", "gross_notional": 2_000.0,
                    "fee": 1.6, "adv_participation_pct": 0.01,
                },
                {
                    "action": "exit", "symbol": "NVDA", "gross_notional": 2_100.0,
                    "fee": 1.68, "pnl": 96.72,
                },
                {
                    "action": "entry", "symbol": "XLE", "gross_notional": 1_500.0,
                    "fee": 1.2, "adv_participation_pct": 0.02,
                },
                {
                    "action": "exit", "symbol": "XLE", "gross_notional": 1_450.0,
                    "fee": 1.16, "pnl": -52.36,
                },
            ],
        }
        result = lab._execution_diagnostics(sim)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["gross_traded_notional"], 7050.0)
        self.assertEqual(result["annualized_turnover_x"], 0.705)
        self.assertEqual(result["capacity"]["entries_with_adv"], 2)
        self.assertEqual(result["capacity"]["stress"][-1]["entries_over_limit"], 1)
        self.assertEqual(
            result["concentration"]["symbol"]["top_contributor"], "NVDA"
        )
        self.assertEqual(
            result["concentration"]["sector_group"]["top_contributor"],
            "semiconductors",
        )

    def test_sensitivity_has_bounded_cost_and_delayed_open_scenarios(self):
        baseline = {"metrics": {"status": "ok", "total_return_pct": 1.0}}

        def simulated(*args, **kwargs):
            return {
                "metrics": {
                    "status": "ok",
                    "total_return_pct": 10.0 - float(kwargs.get("transaction_cost_bps", 8.0)),
                    "trades": 10,
                }
            }

        with patch.object(lab, "_simulate_next_open", side_effect=simulated):
            result = lab._sensitivity_report({}, [], {}, baseline)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            [row["transaction_cost_bps_per_side"] for row in result["cost_scenarios"]],
            list(lab.COST_SENSITIVITY_BPS),
        )
        self.assertEqual(
            [row["execution_delay_sessions"] for row in result["delay_scenarios"]],
            list(lab.DELAY_SENSITIVITY_SESSIONS),
        )

    def test_validation_verdict_fails_closed_until_every_field_exists(self):
        self.assertFalse(lab._validation_verdict({})["candidate_selection_evidence_complete"])
        profile = {
            "execution_diagnostics": {
                "status": "complete", "capacity": {"status": "complete"}
            },
            "sensitivity": {
                "cost_scenarios": [{}] * len(lab.COST_SENSITIVITY_BPS),
                "delay_scenarios": [{}] * len(lab.DELAY_SENSITIVITY_SESSIONS),
            },
        }
        result = {
            "profiles": {
                "current_proxy": profile,
                "balanced_static": profile,
                "permissive": profile,
                "adaptive_balanced": profile,
            },
            "ablation": {
                "status": "ok",
                "best_variant": {"execution_diagnostics": {"status": "complete"}},
                "best_variant_sensitivity": {"status": "complete"},
            },
        }
        verdict = lab._validation_verdict(result)
        self.assertEqual(verdict["status"], "complete")
        self.assertTrue(verdict["candidate_selection_evidence_complete"])
        self.assertFalse(verdict["automatic_strategy_promotion"])

    def test_delayed_execution_uses_later_open_without_refreshing_signal(self):
        dates = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
        frame = pd.DataFrame(
            [
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                 "score": 0.03, "atr_pct": 0.01, "adv20_dollars": 1_000_000.0},
                {"Open": 110.0, "High": 111.0, "Low": 109.0, "Close": 110.0,
                 "score": -1.0, "atr_pct": 0.50, "adv20_dollars": 1_000_000.0},
                {"Open": 120.0, "High": 121.0, "Low": 119.0, "Close": 120.0,
                 "score": -1.0, "atr_pct": 0.50, "adv20_dollars": 1_000_000.0},
            ],
            index=dates,
        )
        with patch.object(lab, "np", np), patch.object(
            lab.base, "np", np
        ), patch.object(lab, "_regime", return_value="neutral"), patch.object(
            lab, "_eligible", side_effect=lambda row, policy: row["score"] > 0
        ):
            result = lab._simulate_next_open(
                {"ALPHA": frame}, {"neutral": _policy()}, list(dates),
                execution_delay_sessions=2,
            )
        entry = next(row for row in result["trades"] if row["action"] == "entry")
        self.assertEqual(entry["date"], "2026-01-07")
        self.assertEqual(entry["price"], 120.0)
        self.assertEqual(entry["signal_atr_pct"], 0.01)
        self.assertEqual(entry["execution_delay_sessions"], 2)


if __name__ == "__main__":
    unittest.main()
