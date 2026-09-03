from __future__ import annotations

import copy
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import canonical_execution_ledger as ledger
import v4_canonical_state_reconciliation as recovery


def _row(execution_id, event_hash, action, symbol, price, shares):
    return {
        "execution_id": execution_id,
        "event_hash": event_hash,
        "previous_event_hash": "",
        "ledger_version": ledger.VERSION,
        "recorded_local": "2026-09-03 09:59:24 CDT",
        "accounting_epoch_id": recovery.EPOCH_ID,
        "action": action,
        "symbol": symbol,
        "side": "short",
        "price": price,
        "shares": shares,
        "exit_reason": "structure_stop_short" if action == "exit" else None,
    }


def _fixture():
    mu_entry = _row("mu-entry", "mu-entry-hash", "entry", "MU", 935.83, 1.079923684)
    stx_entry = _row("stx-entry", "stx-entry-hash", "entry", "STX", 783.175, 1.290454899)
    mu_exit_id, stx_exit_id = sorted(recovery.EXPECTED_MISSING)
    expected_a = recovery.EXPECTED_MISSING[mu_exit_id]
    expected_b = recovery.EXPECTED_MISSING[stx_exit_id]
    missing = {
        expected_a["symbol"]: _row(mu_exit_id, expected_a["event_hash"], "exit", expected_a["symbol"], expected_a["price"], expected_a["shares"]),
        expected_b["symbol"]: _row(stx_exit_id, expected_b["event_hash"], "exit", expected_b["symbol"], expected_b["price"], expected_b["shares"]),
    }
    rows = [mu_entry, stx_entry, missing["MU"], missing["STX"]]
    trades = []
    for row in rows[:2]:
        trades.append({
            "time": "2026-09-03 09:20:00 CDT",
            "action": row["action"], "symbol": row["symbol"], "side": row["side"],
            "price": row["price"], "shares": row["shares"],
            "execution_id": row["execution_id"],
            "accounting_epoch_id": recovery.EPOCH_ID,
            "canonical_ledger_event_hash": row["event_hash"],
            "canonical_ledger_version": ledger.VERSION,
        })
    positions = {
        "MU": {"side": "short", "entry": 935.83, "shares": 1.079923684, "margin": 935.83 * 1.079923684, "last_price": 940.0},
        "STX": {"side": "short", "entry": 783.175, "shares": 1.290454899, "margin": 783.175 * 1.290454899, "last_price": 786.0},
    }
    cash = 10000.0 - sum(pos["margin"] for pos in positions.values())
    state = {
        "accounting_epoch_id": recovery.EPOCH_ID,
        "paper_accounting_epoch": {"id": recovery.EPOCH_ID, "validation_hold": False},
        "initial_cash": 10000.0,
        "cash": cash,
        "equity": cash + sum(pos["margin"] for pos in positions.values()),
        "positions": positions,
        "trades": trades,
        "realized_pnl": {"today": 0.0, "total": -400.0},
        "performance": {"open_positions": copy.deepcopy(positions), "unrealized_pnl": 0.0},
        "risk_controls": {
            "halted": True, "halt_reason": recovery.HALT_REASON,
            "day_start_equity": 10000.0, "day_peak_equity": 10025.0,
        },
        "history": [10000.0, 10005.0],
    }
    return rows, state


class Issue172CanonicalStateCommitTests(unittest.TestCase):
    def test_execution_mirror_is_persisted_before_record_trade_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.jsonl"
            portfolio = {"risk_controls": {"halted": False}, "accounting_epoch_id": "epoch-test", "trades": []}
            calls = []
            saves = []

            def mirror(action, symbol, side, px, shares, extra=None):
                row = {"action": action, "symbol": symbol, "side": side, "price": px, "shares": shares, **(extra or {})}
                calls.append(row)
                portfolio["trades"].append(row)

            def save(state):
                saves.append({
                    "execution_ids": [row.get("execution_id") for row in state.get("trades", [])],
                    "ledger_rows": len(ledger_path.read_text().splitlines()),
                })

            core = types.SimpleNamespace(
                portfolio=portfolio, record_trade=mirror, save_state=save,
                local_ts_text=lambda: "2026-09-03 12:00:00 CDT",
            )
            with mock.patch.object(ledger, "LEDGER_FILE", str(ledger_path)):
                ledger.apply(core)
                core.record_trade("entry", "QQQ", "long", 100, 2, {})
                status = ledger.status_payload(core)

            self.assertEqual(len(calls), 1)
            self.assertEqual(saves, [{"execution_ids": [calls[0]["execution_id"]], "ledger_rows": 1}])
            self.assertEqual(status["last_state_projection_commit"]["status"], "committed")

    def test_projection_persist_failure_halts_and_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio = {"risk_controls": {"halted": False}, "accounting_epoch_id": "epoch-test", "trades": []}
            calls = []

            def mirror(action, symbol, side, px, shares, extra=None):
                row = {"action": action, "symbol": symbol, "side": side, "price": px, "shares": shares, **(extra or {})}
                calls.append(row)
                portfolio["trades"].append(row)

            def fail_save(_state):
                raise OSError("volume unavailable")

            core = types.SimpleNamespace(
                portfolio=portfolio, record_trade=mirror, save_state=fail_save,
                local_ts_text=lambda: "2026-09-03 12:00:00 CDT",
            )
            with mock.patch.object(ledger, "LEDGER_FILE", str(Path(directory) / "ledger.jsonl")):
                ledger.apply(core)
                with self.assertRaisesRegex(OSError, "volume unavailable"):
                    core.record_trade("exit", "QQQ", "long", 100, 1, {})

            self.assertEqual(len(calls), 1)
            self.assertTrue(portfolio["risk_controls"]["halted"])
            self.assertEqual(portfolio["risk_controls"]["halt_reason"], "canonical execution state projection commit failed")
            self.assertEqual(portfolio["risk_controls"]["canonical_state_projection_execution_id"], calls[0]["execution_id"])

    def test_exact_ledger_only_exits_reconcile_state_and_preserve_halt(self):
        rows, state = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "canonical.jsonl"
            ledger_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            saved = []
            core = types.SimpleNamespace(
                portfolio=state,
                local_ts_text=lambda: "2026-09-03 12:00:00 CDT",
                save_state=lambda value: saved.append(copy.deepcopy(value)),
            )
            with mock.patch.object(ledger, "LEDGER_FILE", str(ledger_path)), mock.patch.object(
                ledger, "_read_rows", return_value=(copy.deepcopy(rows), [])
            ), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])), mock.patch.object(
                recovery, "STATE_DIR", str(root)
            ), mock.patch.object(recovery, "MARKER_FILE", str(root / "marker.json")):
                result = recovery.apply(core)

            self.assertEqual(result["status"], "completed")
            self.assertTrue(saved)
            self.assertEqual(saved[-1]["positions"], {})
            self.assertEqual(len(saved[-1]["trades"]), 4)
            self.assertTrue(saved[-1]["risk_controls"]["halted"])
            self.assertEqual(saved[-1]["risk_controls"]["halt_reason"], recovery.HALT_REASON)
            self.assertEqual(saved[-1]["history"], [10000.0, 10005.0])
            self.assertFalse(result["canonical_history_rewritten"])
            self.assertFalse(result["risk_halt_cleared"])
            self.assertTrue((root / "marker.json").exists())
            self.assertTrue(list((root / "forensic_archives").glob("*_issue172_canonical_state_divergence")))

    def test_nonexact_missing_set_is_observational_only(self):
        rows, state = _fixture()
        rows = rows[:-1]
        saves = []
        core = types.SimpleNamespace(portfolio=state, save_state=lambda value: saves.append(value))
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            ledger, "_read_rows", return_value=(copy.deepcopy(rows), [])
        ), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])), mock.patch.object(
            recovery, "MARKER_FILE", str(Path(directory) / "marker.json")
        ):
            result = recovery.apply(core)

        self.assertEqual(result["status"], "not_applicable")
        self.assertEqual(saves, [])
        self.assertFalse(result["canonical_history_rewritten"])
        self.assertFalse(result["risk_halt_cleared"])

    def test_reconciliation_is_blocked_outside_paper_runtime(self):
        rows, state = _fixture()
        saves = []
        core = types.SimpleNamespace(portfolio=state, save_state=lambda value: saves.append(value))
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            recovery, "MARKER_FILE", str(Path(directory) / "marker.json")
        ), mock.patch.object(recovery.v3, "_paper_only", return_value=False):
            result = recovery.apply(core)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "paper_runtime_required")
        self.assertEqual(saves, [])

    def test_interrupted_marker_fails_closed_without_state_write(self):
        _, state = _fixture()
        saves = []
        core = types.SimpleNamespace(portfolio=state, save_state=lambda value: saves.append(value))
        with tempfile.TemporaryDirectory() as directory:
            marker_path = Path(directory) / "marker.json"
            marker_path.write_text(json.dumps({"status": "repair_started"}), encoding="utf-8")
            with mock.patch.object(recovery, "MARKER_FILE", str(marker_path)):
                result = recovery.apply(core)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["reason"], "interrupted_reconciliation_requires_inspection")
        self.assertEqual(saves, [])


if __name__ == "__main__":
    unittest.main()
