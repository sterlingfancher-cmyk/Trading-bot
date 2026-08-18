import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import canonical_execution_ledger as ledger
import paper_ledger_matched_exit_guard as guard


class FakeCore:
    def __init__(self, *, symbol="TEM", side="long", shares=29.640567, entry=54.885):
        self.exit_calls = 0
        self.save_calls = 0
        self.portfolio = {
            "cash": 11500.0,
            "equity": 13000.0,
            "accounting_epoch_id": "stable-paper-v2-20260812-verified01",
            "paper_accounting_epoch": {
                "id": "stable-paper-v2-20260812-verified01",
                "epoch_id": "stable-paper-v2-20260812-verified01",
                "baseline_type": "verified_snapshot_with_open_position",
            },
            "positions": {
                symbol: {
                    "side": side,
                    "shares": shares,
                    "entry": entry,
                    "last_price": entry,
                }
            },
            "risk_controls": {"halted": False, "halt_reason": ""},
            "trades": [],
        }

    def local_ts_text(self):
        return "2026-08-18 13:30:00 CDT"

    def save_state(self, state=None):
        self.save_calls += 1

    def exit_position(self, symbol, px, reason, market_mode=None, extra=None):
        self.exit_calls += 1
        pos = self.portfolio["positions"].get(symbol)
        if not pos:
            return None
        shares = float(pos.get("shares", 0.0))
        if pos.get("side", "long") == "long":
            self.portfolio["cash"] += shares * float(px)
        del self.portfolio["positions"][symbol]
        return {"symbol": symbol, "price": px, "shares": shares, "reason": reason}


class CanonicalFullExitRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "canonical_execution_ledger.jsonl"
        self.ledger_patch = mock.patch.object(ledger, "LEDGER_FILE", str(self.path))
        self.ledger_patch.start()

    def tearDown(self):
        self.ledger_patch.stop()
        self.tempdir.cleanup()

    def test_literal_tem_second_full_exit_is_blocked_before_any_state_mutation(self):
        core = FakeCore()
        ids = iter([
            "d647d8a0580b44edbab0224e6c339bfd",
            "7b13d9194a23407f926667b2f48d4057",
        ])
        with mock.patch.object(ledger.uuid, "uuid4", side_effect=lambda: types.SimpleNamespace(hex=next(ids))):
            ledger.append_execution("entry", "TEM", "long", 54.885, 29.640567, {}, core)
            ledger.append_execution("exit", "TEM", "long", 53.105, 29.640567, {}, core)

        rows_before = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(
            [row["execution_id"] for row in rows_before],
            [
                "d647d8a0580b44edbab0224e6c339bfd",
                "7b13d9194a23407f926667b2f48d4057",
            ],
        )

        cash_before = core.portfolio["cash"]
        applied = guard.apply(core)
        self.assertTrue(applied["runtime_full_exit_guard_installed"])
        result = core.exit_position("TEM", 52.905, "stop_loss")

        self.assertIsNone(result)
        self.assertEqual(core.exit_calls, 0)
        self.assertEqual(core.portfolio["cash"], cash_before)
        self.assertEqual(core.portfolio["positions"]["TEM"]["shares"], 29.640567)
        self.assertEqual(core.save_calls, 1)

        rows_after = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(rows_after, rows_before)

        risk = core.portfolio["risk_controls"]
        self.assertTrue(risk["halted"])
        block = risk["canonical_full_exit_preflight_block"]
        self.assertEqual(block["boundary"], "exit_position_pre_mutation")
        self.assertEqual(block["symbol"], "TEM")
        self.assertEqual(block["reason"], "canonical_position_already_closed")
        self.assertEqual(block["canonical_remaining_qty"], 0.0)

    def test_verified_snapshot_baseline_position_without_canonical_entry_remains_manageable(self):
        self.path.write_text("")
        core = FakeCore(symbol="LRCX", shares=3.42486, entry=312.90)
        core.portfolio["paper_accounting_epoch"]["verified_snapshot_baseline"] = {
            "verified": True,
            "positions": {
                "LRCX": {
                    "side": "long",
                    "qty": 3.42486,
                    "entry_price": 312.90,
                }
            },
        }

        guard.apply(core)
        result = core.exit_position("LRCX", 333.12, "target")

        self.assertIsNotNone(result)
        self.assertEqual(core.exit_calls, 1)
        self.assertNotIn("LRCX", core.portfolio["positions"])
        self.assertIsNone(core.portfolio["risk_controls"].get("canonical_full_exit_preflight_block"))

    def test_malformed_canonical_ledger_fails_closed_before_full_exit(self):
        self.path.write_text("{not-json}\n")
        core = FakeCore(symbol="QQQ", shares=2.218803, entry=730.92)
        cash_before = core.portfolio["cash"]

        guard.apply(core)
        result = core.exit_position("QQQ", 718.0, "stop_loss")

        self.assertIsNone(result)
        self.assertEqual(core.exit_calls, 0)
        self.assertEqual(core.portfolio["cash"], cash_before)
        self.assertIn("QQQ", core.portfolio["positions"])
        block = core.portfolio["risk_controls"]["canonical_full_exit_preflight_block"]
        self.assertEqual(block["reason"], "canonical_execution_ledger_unreadable_for_full_exit")

    def test_runtime_position_without_canonical_entry_or_verified_baseline_fails_closed(self):
        self.path.write_text("")
        core = FakeCore(symbol="QQQ", shares=2.218803, entry=730.92)

        guard.apply(core)
        result = core.exit_position("QQQ", 718.0, "stop_loss")

        self.assertIsNone(result)
        self.assertEqual(core.exit_calls, 0)
        block = core.portfolio["risk_controls"]["canonical_full_exit_preflight_block"]
        self.assertEqual(block["reason"], "canonical_entry_missing_for_runtime_position")


if __name__ == "__main__":
    unittest.main()
