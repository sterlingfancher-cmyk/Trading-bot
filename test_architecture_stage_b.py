from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from shadow_decision_models import (
    CycleDecision,
    DecisionEffect,
    MarketSnapshot,
    PolicyDecision,
    RiskSnapshot,
    Side,
    SignalSnapshot,
)
from typed_configuration_models import ConfigUnit, normalize_value

ROOT = Path(__file__).resolve().parent


class TypedConfigurationModelTests(unittest.TestCase):
    def test_unit_normalization(self) -> None:
        self.assertEqual(normalize_value("0.025", ConfigUnit.FRACTION), 0.025)
        self.assertEqual(normalize_value(1.5, ConfigUnit.PERCENT_POINTS), 0.015)
        self.assertEqual(normalize_value("false", ConfigUnit.BOOLEAN), False)
        self.assertEqual(normalize_value("300", ConfigUnit.SECONDS), 300.0)

    def test_baseline_is_non_authoritative(self) -> None:
        baseline = json.loads((ROOT / "typed_configuration_baseline.json").read_text())
        self.assertTrue(baseline["policy"]["read_only"])
        self.assertFalse(baseline["policy"]["authoritative"])
        self.assertFalse(baseline["policy"]["effective_value_changes_allowed"])


class ShadowDecisionModelTests(unittest.TestCase):
    def test_models_are_frozen_and_shadow_only(self) -> None:
        signal = SignalSnapshot("DELL", Side.LONG, 0.02, 0.025, 100.0)
        with self.assertRaises(FrozenInstanceError):
            signal.score = 0.5  # type: ignore[misc]

        cycle = CycleDecision(
            cycle_id="test",
            generated_local="2026-08-03 22:00:00 CDT",
            market=MarketSnapshot("neutral", 50.0, False),
            risk=RiskSnapshot(False, False, 0.0, 0.0, 0.0, 0.0),
            positions=(),
            candidates=(),
            selected_symbols=(),
        )
        self.assertEqual(cycle.authority, "shadow_only")
        self.assertEqual(cycle.to_dict()["cycle_id"], "test")

    def test_policy_effect_vocabulary(self) -> None:
        decision = PolicyDecision(
            policy_id="risk",
            effect=DecisionEffect.SIZE_REDUCTION,
            reason_code="volatility_high",
            size_multiplier=0.25,
        )
        self.assertFalse(decision.terminal)
        self.assertEqual(decision.size_multiplier, 0.25)

    def test_shadow_module_has_no_runtime_or_order_authority(self) -> None:
        path = ROOT / "shadow_decision_models.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        forbidden_imports = {"app", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                self.assertNotIn(name, forbidden_calls)


if __name__ == "__main__":
    unittest.main()
