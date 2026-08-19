from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from trading.state import (
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    PositionSnapshot,
    RiskStateSnapshot,
    StateStore,
)

ROOT = Path(__file__).resolve().parent


class StablePaperCoreStageATests(unittest.TestCase):
    def test_contract_is_shadow_only(self) -> None:
        contract = json.loads((ROOT / "stable_paper_core_v3_contract.json").read_text(encoding="utf-8"))
        policy = contract["policy"]
        self.assertTrue(policy["shadow_only"])
        self.assertFalse(policy["authoritative_runtime_source"])
        self.assertFalse(policy["places_orders"])
        self.assertFalse(policy["reads_state_file"])
        self.assertFalse(policy["writes_state_file"])
        self.assertTrue(policy["requires_parity_before_authoritative_cutover"])

    def test_models_are_frozen(self) -> None:
        portfolio = PortfolioSnapshot(
            cash=9000.0,
            equity=10000.0,
            realized_total=0.0,
            realized_today=0.0,
            unrealized_pnl=0.0,
            positions=(),
        )
        with self.assertRaises(FrozenInstanceError):
            portfolio.equity = 1.0  # type: ignore[misc]

    def test_invalid_protected_equity_is_rejected(self) -> None:
        for equity in (0.0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                PortfolioSnapshot(
                    cash=10000.0,
                    equity=equity,
                    realized_total=0.0,
                    realized_today=0.0,
                    unrealized_pnl=0.0,
                    positions=(),
                )

    def test_invalid_risk_baseline_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RiskStateSnapshot(
                date="2026-08-19",
                day_start_equity=-26064.31,
                day_peak_equity=0.01,
                daily_loss_fraction=0.0,
                intraday_drawdown_fraction=0.0,
                halted=True,
                halt_reason="daily loss limit hit (3.0%)",
            )

    def test_duplicate_position_symbols_are_rejected(self) -> None:
        first = PositionSnapshot("QQQ", "long", 1.0, 500.0, 505.0)
        second = PositionSnapshot("qqq", "long", 2.0, 500.0, 505.0)
        with self.assertRaises(ValueError):
            PortfolioSnapshot(
                cash=9000.0,
                equity=10000.0,
                realized_total=0.0,
                realized_today=0.0,
                unrealized_pnl=0.0,
                positions=(first, second),
            )

    def test_state_store_is_descriptor_only(self) -> None:
        descriptor = StateStore.descriptor()
        self.assertEqual(descriptor["authority"], "shadow_only")
        self.assertFalse(descriptor["write_enabled"])
        self.assertFalse(descriptor["reads_state_file"])
        self.assertFalse(descriptor["writes_state_file"])

    def test_canonical_snapshot_is_shadow_only(self) -> None:
        portfolio = PortfolioSnapshot(9000.0, 10000.0, 0.0, 0.0, 0.0, ())
        risk = RiskStateSnapshot("2026-08-19", 10000.0, 10000.0, 0.0, 0.0, False, "")
        snapshot = CanonicalStateSnapshot(portfolio, risk, 0, True)
        self.assertEqual(snapshot.authority, "shadow_only")
        self.assertTrue(snapshot.execution_chain_valid)

    def test_module_has_no_runtime_provider_order_or_persistence_authority(self) -> None:
        path = ROOT / "trading" / "state.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {"app", "alpaca_trade_api", "yfinance", "requests"}
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
            "open",
            "replace",
            "unlink",
            "remove",
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
