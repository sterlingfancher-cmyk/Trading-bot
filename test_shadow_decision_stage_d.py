from __future__ import annotations

import ast
import json
import unittest
from dataclasses import replace
from pathlib import Path

from shadow_decision_comparison import DivergenceType, compare_cycles
from shadow_decision_models import (
    CandidateDecision,
    CycleDecision,
    MarketSnapshot,
    PolicyDecision,
    PositionSnapshot,
    RiskSnapshot,
    Side,
    SignalSnapshot,
    DecisionEffect,
)

ROOT = Path(__file__).resolve().parent


def _candidate(
    *,
    allowed: bool = True,
    score: float = 0.02,
    size: float = 1.0,
    terminal_reason: str = "",
) -> CandidateDecision:
    signal = SignalSnapshot(
        symbol="DELL",
        side=Side.LONG,
        score=0.02,
        rank_score=0.025,
        price=100.0,
        sector="technology",
        strategy_bucket="momentum",
        confirmations=("trend", "volume"),
    )
    policy = PolicyDecision(
        policy_id="example",
        effect=DecisionEffect.ALLOW if allowed else DecisionEffect.HARD_BLOCK,
        reason_code=terminal_reason or "allowed",
        terminal=not allowed,
    )
    return CandidateDecision(
        signal=signal,
        policies=(policy,),
        final_score=score,
        final_size_multiplier=size,
        allowed=allowed,
        terminal_reason=terminal_reason,
    )


def _cycle(
    *,
    cycle_id: str = "cycle-1",
    candidate: CandidateDecision | None = None,
    selected: tuple[str, ...] = ("DELL",),
) -> CycleDecision:
    return CycleDecision(
        cycle_id=cycle_id,
        generated_local="2026-08-03 22:00:00 CDT",
        market=MarketSnapshot("neutral", 50.0, True, 0.1, 0.02),
        risk=RiskSnapshot(False, False, 0.0, 0.0, 0.0, 0.1),
        positions=(
            PositionSnapshot(
                symbol="AAPL",
                side=Side.LONG,
                quantity=1.0,
                market_value_fraction=0.1,
                unrealized_return_fraction=0.01,
                sector="technology",
                strategy_bucket="core",
            ),
        ),
        candidates=(candidate or _candidate(),),
        selected_symbols=selected,
    )


class ShadowDecisionComparisonTests(unittest.TestCase):
    def test_identical_decisions_have_parity(self) -> None:
        current = _cycle()
        report = compare_cycles(current, current)
        self.assertTrue(report.parity)
        self.assertEqual(report.authority, "comparison_only")
        self.assertEqual(
            report.candidate_comparisons[0].divergences,
            (DivergenceType.PARITY,),
        )

    def test_selection_and_allowance_divergence_are_recorded(self) -> None:
        current = _cycle()
        shadow = _cycle(
            candidate=_candidate(
                allowed=False,
                terminal_reason="volatility_high",
                size=0.25,
            ),
            selected=(),
        )
        report = compare_cycles(current, shadow)
        self.assertFalse(report.parity)
        divergences = set(report.candidate_comparisons[0].divergences)
        self.assertIn(DivergenceType.ALLOWANCE, divergences)
        self.assertIn(DivergenceType.SELECTION, divergences)
        self.assertIn(DivergenceType.TERMINAL_REASON, divergences)
        self.assertIn(DivergenceType.SIZE, divergences)
        self.assertEqual(report.selected_only_by_current, ("DELL",))

    def test_different_cycle_or_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compare_cycles(_cycle(), _cycle(cycle_id="cycle-2"))
        changed_market = replace(_cycle(), market=MarketSnapshot("risk_on", 60.0, True))
        with self.assertRaises(ValueError):
            compare_cycles(_cycle(), changed_market)

    def test_contract_is_non_authoritative(self) -> None:
        contract = json.loads(
            (ROOT / "shadow_decision_comparison_contract.json").read_text(
                encoding="utf-8"
            )
        )
        policy = contract["policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["authoritative_runtime_source"])
        self.assertFalse(policy["connected_to_runtime"])
        self.assertFalse(policy["replaces_callables"])
        self.assertFalse(policy["places_orders"])
        gate = contract["forward_evidence_gate"]
        self.assertFalse(gate["automatic_promotion"])
        self.assertGreaterEqual(gate["minimum_forward_candidates"], 30)
        self.assertGreaterEqual(gate["minimum_one_day_outcomes"], 20)

    def test_comparison_module_has_no_runtime_or_order_authority(self) -> None:
        path = ROOT / "shadow_decision_comparison.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "core_entry_pipeline",
            "state_io_hardening",
            "alpaca_trade_api",
            "yfinance",
        }
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
            "load_state",
            "add_url_rule",
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
