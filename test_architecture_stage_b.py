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

ROOT = Path(__file__).resolve().parent


class CanonicalTypedConfigurationTests(unittest.TestCase):
    def test_contract_is_read_only_and_non_authoritative(self) -> None:
        contract = json.loads(
            (ROOT / "typed_configuration_contract.json").read_text(encoding="utf-8")
        )
        policy = contract["policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["authoritative_runtime_source"])
        self.assertFalse(policy["allow_new_observations"])
        self.assertTrue(policy["behavior_changes_require_backtest_and_forward_test"])

    def test_contract_declares_explicit_risk_units(self) -> None:
        contract = json.loads(
            (ROOT / "typed_configuration_contract.json").read_text(encoding="utf-8")
        )
        environment = contract["environment_contracts"]
        parameters = contract["parameter_unit_contracts"]
        self.assertEqual(environment["MAX_DAILY_LOSS_PCT"]["unit"], "fraction")
        self.assertEqual(
            environment["MAX_INTRADAY_DRAWDOWN_PCT"]["unit"], "fraction"
        )
        surge = parameters["MAX_INTRADAY_DRAWDOWN_PCT"]["observations"]
        self.assertIn("percentage_points", {row["unit"] for row in surge})

    def test_snapshot_validator_has_no_runtime_or_order_authority(self) -> None:
        path = ROOT / "typed_configuration_snapshot.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {"app", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {"app", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
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
