from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from trading.risk import RiskInvariantError, RiskLimits, ShadowRiskEngine
from trading.state import RiskStateSnapshot
from trading.valuation import DeterministicValuationService, ValuationInvariantError

ROOT = Path(__file__).resolve().parent


def valuation(equity: float):
    return DeterministicValuationService.value(
        cash=equity,
        positions=(),
        marks=(),
    )


class StablePaperCoreStageCRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = RiskLimits(
            max_daily_loss_fraction=0.03,
            max_intraday_drawdown_fraction=0.025,
            hard_realized_loss_fraction=0.025,
        )

    def test_contract_is_shadow_only(self) -> None:
        contract = json.loads(
            (ROOT / "stable_paper_core_v3_stage_c_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["authority"], "shadow_only")
        self.assertFalse(contract["configuration_policy"]["reads_environment"])
        self.assertTrue(
            contract["configuration_policy"]["thresholds_supplied_explicitly"]
        )

    def test_fresh_day_uses_protected_valuation_and_clears_prior_day_halt(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10200.0,
            daily_loss_fraction=0.03,
            intraday_drawdown_fraction=0.04,
            halted=True,
            halt_reason="prior-day halt",
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-21",
            valuation=valuation(10150.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertTrue(result.fresh_day)
        self.assertEqual(result.state.day_start_equity, 10150.0)
        self.assertEqual(result.state.day_peak_equity, 10150.0)
        self.assertFalse(result.state.halted)
        self.assertEqual(result.state.halt_reason, "")
        self.assertEqual(result.state.daily_loss_fraction, 0.0)
        self.assertEqual(result.state.intraday_drawdown_fraction, 0.0)

    def test_same_day_peak_is_monotonic(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10500.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(10300.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertFalse(result.fresh_day)
        self.assertEqual(result.state.day_start_equity, 10000.0)
        self.assertEqual(result.state.day_peak_equity, 10500.0)
        self.assertAlmostEqual(
            result.state.intraday_drawdown_fraction,
            (10500.0 - 10300.0) / 10500.0,
        )
        self.assertFalse(result.state.halted)

    def test_daily_loss_halt_matches_three_percent_limit(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10000.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(9700.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertTrue(result.daily_loss_triggered)
        self.assertTrue(result.state.halted)
        self.assertEqual(result.state.halt_reason, "daily loss limit hit (3.0%)")

    def test_intraday_drawdown_halt_uses_same_day_peak(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10500.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(10200.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertTrue(result.intraday_drawdown_triggered)
        self.assertTrue(result.state.halted)
        self.assertEqual(
            result.state.halt_reason, "intraday drawdown limit hit (2.5%)"
        )

    def test_realized_hard_loss_halt_matches_current_policy(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10000.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(10000.0),
            realized_today=-250.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertTrue(result.realized_loss_triggered)
        self.assertTrue(result.state.halted)
        self.assertEqual(
            result.state.halt_reason,
            "self-defense hard realized loss hit (2.50%)",
        )

    def test_same_day_halt_remains_latched_when_metrics_recover(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10000.0,
            daily_loss_fraction=0.03,
            intraday_drawdown_fraction=0.03,
            halted=True,
            halt_reason="daily loss limit hit (3.0%)",
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(10000.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        self.assertTrue(result.state.halted)
        self.assertEqual(result.state.halt_reason, previous.halt_reason)
        self.assertFalse(result.daily_loss_triggered)
        self.assertFalse(result.intraday_drawdown_triggered)
        self.assertFalse(result.realized_loss_triggered)

    def test_invalid_non_positive_valuation_cannot_seed_risk(self) -> None:
        with self.assertRaises(ValuationInvariantError):
            valuation(-26064.31)

    def test_limits_require_explicit_fraction_units(self) -> None:
        with self.assertRaises(RiskInvariantError):
            RiskLimits(3.0, 0.025, 0.025)
        with self.assertRaises(RiskInvariantError):
            RiskLimits(0.03, 2.5, 0.025)

    def test_legacy_percentage_point_parity_comparator(self) -> None:
        previous = RiskStateSnapshot(
            date="2026-08-20",
            day_start_equity=10000.0,
            day_peak_equity=10000.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        )
        result = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation(9700.0),
            realized_today=0.0,
            limits=self.limits,
            previous=previous,
        )
        parity = ShadowRiskEngine.compare_legacy(
            evaluation=result,
            legacy={
                "day_start_equity": 10000.0,
                "day_peak_equity": 10000.0,
                "daily_loss_pct": 3.0,
                "intraday_drawdown_pct": 3.0,
                "halted": True,
                "halt_reason": "daily loss limit hit (3.0%)",
            },
            tolerance=1e-12,
        )
        self.assertEqual(parity["overall"], "pass")
        self.assertTrue(all(parity["checks"].values()))

    def test_shadow_module_has_no_runtime_or_order_authority(self) -> None:
        path = ROOT / "trading" / "risk.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "os",
            "yfinance",
            "alpaca_trade_api",
        }
        forbidden_calls = {
            "save_state",
            "load_state",
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "register_routes",
            "start_watchdog",
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
