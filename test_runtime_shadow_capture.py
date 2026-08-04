from __future__ import annotations

import ast
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_report_guard
import runtime_shadow_capture

ROOT = Path(__file__).resolve().parent


def _cycle_result() -> dict:
    return {
        "market_mode": "neutral",
        "regime": "neutral",
        "risk_score": 55,
        "risk_controls": {
            "halted": False,
            "self_defense_active": False,
            "daily_loss_pct": 0.0,
            "intraday_drawdown_pct": 0.0,
            "realized_loss_pct": 0.0,
        },
        "new_entries_allowed": True,
        "entry_block_reason": None,
        "entries": [
            {
                "symbol": "DELL",
                "side": "long",
                "score": 0.031,
                "price": 101.0,
                "alloc_factor": 0.18,
            }
        ],
        "blocked_entries": [
            {
                "symbol": "WDC",
                "side": "long",
                "score": 0.027,
                "price": 84.0,
                "reason": "sector_bucket_limit",
            }
        ],
        "rejected_signals": [],
        "long_signals": ["DELL", "WDC"],
        "short_signals": [],
        "equity": 10750.0,
        "market_open_now": True,
    }


class RuntimeShadowCaptureTests(unittest.TestCase):
    def test_capture_parity_baseline(self) -> None:
        cycle = _cycle_result()
        report = runtime_shadow_capture.capture_cycle(
            cycle_id="cycle-1",
            generated_local="2026-08-03 12:00:00",
            market=cycle,
            risk=cycle["risk_controls"],
            positions={
                "DELL": {
                    "side": "long",
                    "qty": 10,
                    "entry": 100.0,
                    "last_price": 101.0,
                    "sector": "XLK",
                    "bucket": "technology",
                }
            },
            equity=10750.0,
            long_signals=cycle["long_signals"],
            short_signals=[],
            entries=cycle["entries"],
            blocked_entries=cycle["blocked_entries"],
            rejected_signals=[],
            new_entries_allowed=True,
            entry_block_reason=None,
            market_open=True,
        )
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["parity"])
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["selected_symbols"], ["DELL"])
        self.assertFalse(report["independent_policy_active"])
        self.assertFalse(report["forward_evidence_eligible"])
        self.assertFalse(report["authority"]["places_orders"])

    def test_bounded_history_and_cycle_deduplication(self) -> None:
        state: dict = {}
        for index in range(5):
            report = {
                "status": "pass",
                "cycle_id": f"cycle-{index}",
                "generated_local": f"2026-08-03 12:0{index}:00",
                "input_fingerprint": str(index),
                "parity": True,
                "candidate_count": 2,
                "eligible_candidate_count": 1,
                "blocked_candidate_count": 1,
                "selected_symbols": ["DELL"],
                "divergence_counts": {"parity": 2},
                "authority": {"observer_only": True},
            }
            state = runtime_shadow_capture.append_bounded(state, report, history_limit=3)
        self.assertEqual(state["history_count"], 3)
        self.assertEqual(state["total_cycles"], 5)
        self.assertEqual(state["total_candidates"], 10)
        duplicate = runtime_shadow_capture.append_bounded(state, state["latest"], history_limit=3)
        self.assertEqual(duplicate, state)

    def test_run_report_guard_uses_existing_owner_and_preserves_result(self) -> None:
        portfolio = {
            "equity": 10750.0,
            "positions": {
                "DELL": {
                    "side": "long",
                    "qty": 10,
                    "entry": 100.0,
                    "last_price": 101.0,
                }
            },
        }
        original_payload = _cycle_result()

        def original_run_cycle(*args, **kwargs):
            return json.loads(json.dumps(original_payload))

        core = SimpleNamespace(
            run_cycle=original_run_cycle,
            store_compiled_report=lambda *args, **kwargs: {"status": "compiled"},
            portfolio=portfolio,
            LAST_CYCLE_ID="cycle-runtime-1",
            local_ts_text=lambda: "2026-08-03 12:05:00",
            today_key=lambda: "2026-08-03",
        )
        with patch.dict(os.environ, {"RUN_CYCLE_INLINE_REPORTS": "false"}, clear=False):
            applied = run_report_guard.apply(core)
            self.assertTrue(applied["existing_owner_extended"])
            result = core.run_cycle(source="auto")

        for key, value in original_payload.items():
            if key == "compiled_report":
                continue
            self.assertEqual(result[key], value)
        self.assertNotIn("shadow_decision_comparison", result)
        capture = portfolio["shadow_decision_comparison"]
        self.assertEqual(capture["latest"]["cycle_id"], "cycle-runtime-1")
        self.assertTrue(capture["latest"]["parity"])
        self.assertEqual(capture["latest"]["selected_symbols"], ["DELL"])
        self.assertFalse(capture["forward_evidence"]["eligible"])

    def test_skipped_cycle_does_not_create_shadow_state(self) -> None:
        portfolio: dict = {}
        core = SimpleNamespace(
            run_cycle=lambda *args, **kwargs: {
                "skipped": True,
                "reason": "market closed",
            },
            store_compiled_report=lambda *args, **kwargs: {},
            portfolio=portfolio,
            LAST_CYCLE_ID=None,
            local_ts_text=lambda: "2026-08-03 17:00:00",
            today_key=lambda: "2026-08-03",
        )
        with patch.dict(os.environ, {"RUN_CYCLE_INLINE_REPORTS": "false"}, clear=False):
            run_report_guard.apply(core)
            result = core.run_cycle(source="auto")
        self.assertTrue(result["skipped"])
        self.assertNotIn("shadow_decision_comparison", portfolio)

    def test_adapter_has_no_runtime_or_order_authority(self) -> None:
        path = ROOT / "runtime_shadow_capture.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "flask",
            "alpaca_trade_api",
            "yfinance",
            "state_io_hardening",
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

    def test_contract_and_existing_owner_integration(self) -> None:
        contract = json.loads(
            (ROOT / "runtime_shadow_capture_contract.json").read_text(encoding="utf-8")
        )
        self.assertTrue(contract["policy"]["telemetry_only"])
        self.assertFalse(contract["policy"]["independent_policy_active"])
        self.assertFalse(contract["policy"]["adds_callable_owner"])
        self.assertEqual(contract["integration"]["existing_owner"], "run_report_guard.py")
        self.assertFalse(
            contract["promotion_gate"]["capture_baseline_counts_as_forward_policy_evidence"]
        )

        source = (ROOT / "run_report_guard.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("runtime_shadow_capture.capture_cycle("), 1)
        self.assertNotIn('result["shadow_decision_comparison"]', source)


if __name__ == "__main__":
    unittest.main()
