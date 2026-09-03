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
        "target_allocation": 0.10,
        "max_exposure": 0.20,
        "stop_loss": 0.01,
        "max_hold_days": 10,
        "rebalance_days": 1,
        "allowed_symbols": None,
    }


def _features(signal_atr, execution_atr, execution_low):
    dates = pd.to_datetime(["2026-01-05", "2026-01-06"])
    frame = pd.DataFrame(
        [
            {
                "Open": 100.0,
                "High": 101.0,
                "Low": 99.0,
                "Close": 100.0,
                "score": 0.02,
                "atr_pct": signal_atr,
            },
            {
                "Open": 100.0,
                "High": 140.0,
                "Low": execution_low,
                "Close": 100.0,
                "score": 0.02,
                "atr_pct": execution_atr,
            },
        ],
        index=dates,
    )
    return {"TEST": frame}, list(dates)


class PerformanceAtrIntegrityTests(unittest.TestCase):
    def _run(self, signal_atr, execution_atr, execution_low):
        features, dates = _features(signal_atr, execution_atr, execution_low)
        regime_map = {"neutral": _policy()}
        with patch.object(lab, "np", np), patch.object(
            lab.base, "np", np
        ), patch.object(lab, "_regime", return_value="neutral"), patch.object(
            lab, "_eligible", return_value=True
        ):
            return lab._simulate_next_open(features, regime_map, dates)

    def test_execution_session_atr_cannot_widen_initial_stop(self):
        result = self._run(signal_atr=0.01, execution_atr=0.50, execution_low=98.0)

        entry = next(row for row in result["trades"] if row["action"] == "entry")
        exit_row = next(row for row in result["trades"] if row["action"] == "exit")
        self.assertEqual(entry["signal_atr_pct"], 0.01)
        self.assertEqual(entry["initial_stop_pct"], 0.0125)
        self.assertEqual(exit_row["reason"], "stop_loss")
        self.assertEqual(exit_row["price"], 98.75)

    def test_signal_session_atr_controls_initial_stop(self):
        result = self._run(signal_atr=0.03, execution_atr=0.01, execution_low=97.0)

        entry = next(row for row in result["trades"] if row["action"] == "entry")
        exit_row = next(row for row in result["trades"] if row["action"] == "exit")
        self.assertEqual(entry["signal_atr_pct"], 0.03)
        self.assertEqual(entry["initial_stop_pct"], 0.0375)
        self.assertEqual(exit_row["reason"], "end_of_test")

    def test_missing_signal_atr_fails_closed_to_policy_stop(self):
        result = self._run(signal_atr=float("nan"), execution_atr=0.50, execution_low=98.5)

        entry = next(row for row in result["trades"] if row["action"] == "entry")
        exit_row = next(row for row in result["trades"] if row["action"] == "exit")
        self.assertEqual(entry["signal_atr_pct"], 0.01)
        self.assertEqual(entry["initial_stop_pct"], 0.0125)
        self.assertEqual(exit_row["reason"], "stop_loss")


if __name__ == "__main__":
    unittest.main()
