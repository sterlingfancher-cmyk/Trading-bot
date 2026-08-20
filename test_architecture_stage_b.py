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
from trading.state import PositionSnapshot
from trading.valuation import (
    DeterministicValuationService,
    ProtectedMarkSnapshot,
    ValuationInvariantError,
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


class StablePaperCoreStageBValuationTests(unittest.TestCase):
    def test_long_and_short_valuation_matches_bidirectional_margin_model(self) -> None:
        positions = (
            PositionSnapshot("LONG", "long", 10.0, 100.0, 1.0),
            PositionSnapshot("SHORT", "short", 5.0, 200.0, 1.0),
        )
        marks = (
            ProtectedMarkSnapshot("LONG", 110.0, "test", True, True),
            ProtectedMarkSnapshot("SHORT", 180.0, "test", True, True),
        )
        snapshot = DeterministicValuationService.value(
            cash=8000.0,
            positions=positions,
            marks=marks,
        )

        self.assertEqual(snapshot.accounting_model, "bidirectional_margin_v1")
        self.assertAlmostEqual(snapshot.total_cost_basis, 2000.0)
        self.assertAlmostEqual(snapshot.total_unrealized_pnl, 200.0)
        self.assertAlmostEqual(snapshot.total_position_value, 2200.0)
        self.assertAlmostEqual(snapshot.equity, 10200.0)
        self.assertAlmostEqual(snapshot.gross_market_exposure, 2000.0)
        self.assertAlmostEqual(snapshot.net_market_exposure, 200.0)
        self.assertTrue(snapshot.risk_baseline_eligible)

    def test_invalid_protected_marks_fail_closed(self) -> None:
        with self.assertRaises(ValuationInvariantError):
            ProtectedMarkSnapshot("BAD", 0.0, "test", True, True)
        with self.assertRaises(ValuationInvariantError):
            ProtectedMarkSnapshot("STALE", 100.0, "test", False, True)
        with self.assertRaises(ValuationInvariantError):
            ProtectedMarkSnapshot("OUTLIER", 100.0, "test", True, False)

    def test_protected_mark_coverage_must_exactly_match_positions(self) -> None:
        position = PositionSnapshot("ONLY", "long", 1.0, 100.0, 1.0)
        with self.assertRaises(ValuationInvariantError):
            DeterministicValuationService.value(
                cash=900.0,
                positions=(position,),
                marks=(),
            )
        with self.assertRaises(ValuationInvariantError):
            DeterministicValuationService.value(
                cash=900.0,
                positions=(position,),
                marks=(
                    ProtectedMarkSnapshot("ONLY", 100.0, "test", True, True),
                    ProtectedMarkSnapshot("EXTRA", 100.0, "test", True, True),
                ),
            )

    def test_non_positive_equity_cannot_become_risk_baseline(self) -> None:
        position = PositionSnapshot("SHORT", "short", 10.0, 100.0, 1.0)
        with self.assertRaises(ValuationInvariantError):
            DeterministicValuationService.value(
                cash=0.0,
                positions=(position,),
                marks=(
                    ProtectedMarkSnapshot("SHORT", 250.0, "test", True, True),
                ),
            )

    def test_stage_b_contract_is_shadow_only_and_requires_issue_82(self) -> None:
        contract = json.loads(
            (ROOT / "stable_paper_core_v3_stage_b_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["authority"], "shadow_only")
        self.assertEqual(contract["accounting_model"], "bidirectional_margin_v1")
        self.assertFalse(contract["promotion"]["automatic"])
        self.assertTrue(
            contract["promotion"][
                "requires_issue_82_acceptance_before_authoritative_cutover"
            ]
        )

    def test_stage_b_module_has_no_runtime_state_provider_or_order_authority(self) -> None:
        path = ROOT / "trading" / "valuation.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "alpaca_trade_api",
            "yfinance",
            "requests",
            "httpx",
        }
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
            "load_state",
            "download_prices",
            "get_risk_controls",
            "update_daily_risk_controls",
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

        descriptor = DeterministicValuationService.descriptor()
        self.assertEqual(descriptor["authority"], "shadow_only")
        self.assertFalse(descriptor["fetches_market_data"])
        self.assertFalse(descriptor["reads_state_file"])
        self.assertFalse(descriptor["writes_state_file"])
        self.assertFalse(descriptor["mutates_risk"])
        self.assertFalse(descriptor["places_orders"])


if __name__ == "__main__":
    unittest.main()
