from __future__ import annotations

import contextlib
import copy
import sys
import types
import unittest
from unittest import mock

import verified_v3_successor_epoch_migration as migration


class Issue126V3V4SuccessorMigrationTests(unittest.TestCase):
    def _baseline_snapshot(self):
        return {
            "verified": True,
            "cash": migration.EXPECTED_BASELINE_CASH,
            "equity": migration.EXPECTED_BASELINE_EQUITY,
            "realized_today": 0.0,
            "realized_total": 42.0,
            "positions": {
                "DHR": {"side": "long", "qty": 0.540748758, "entry_price": 216.960007, "mark": 215.79},
                "SLS": {"side": "long", "qty": migration.EXPECTED_BASELINE_SLS_QTY, "entry_price": 14.335, "mark": 14.45},
            },
        }

    def _rows(self):
        rows = [
            {
                "execution_id": f"legacy-{index}",
                "accounting_epoch_id": migration.PRIOR_EPOCH_ID,
                "action": "entry",
                "symbol": f"LEG{index}",
                "side": "long",
                "price": 1.0,
                "shares": 1.0,
                "event_hash": f"legacy-hash-{index}",
            }
            for index in range(migration.EXPECTED_V3_START_INDEX)
        ]
        rows.extend([
            {
                **migration.EXPECTED_V3_ROWS[0],
                "shares": migration.EXPECTED_BASELINE_SLS_QTY,
            },
            {
                **migration.EXPECTED_V3_ROWS[1],
                "shares": 0.178447,
            },
            dict(migration.EXPECTED_V3_ROWS[2]),
        ])
        for row in rows:
            row.pop("ledger_index", None)
            row.pop("economic_disposition", None)
        return rows

    def _projection_numbers(self):
        cash = migration.EXPECTED_BASELINE_CASH
        cash += migration.EXPECTED_BASELINE_SLS_QTY * 13.62
        cash += 0.178447 * 242.4872
        dhr_qty = 0.540748758 - 0.178447
        equity = cash + dhr_qty * 215.79
        return cash, dhr_qty, equity

    def _portfolio(self, *, halt_reason="canonical execution lifecycle integrity halt"):
        projected_cash, dhr_qty, _ = self._projection_numbers()
        invalid_notional = float(migration.EXPECTED_V3_ROWS[2]["shares"]) * 16.04
        rows = self._rows()[-3:]
        trades = []
        for row in rows:
            trades.append({
                "execution_id": row["execution_id"],
                "accounting_epoch_id": migration.OLD_EPOCH_ID,
                "action": row["action"],
                "symbol": row["symbol"],
                "side": row["side"],
                "price": row["price"],
                "shares": round(float(row["shares"]), 6),
                "canonical_ledger_event_hash": row["event_hash"],
            })
        return {
            "cash": projected_cash + invalid_notional,
            "equity": 13601.69,
            "positions": {
                "DHR": {"side": "long", "shares": dhr_qty, "qty": dhr_qty, "entry": 216.960007, "last_price": 215.79},
                "SLS": {
                    "side": "long",
                    "shares": migration.EXPECTED_BASELINE_SLS_QTY - float(migration.EXPECTED_V3_ROWS[2]["shares"]),
                    "qty": migration.EXPECTED_BASELINE_SLS_QTY,
                    "entry": 14.335,
                    "last_price": 16.04,
                    "accounting_integrity_quarantined": True,
                },
            },
            "trades": trades,
            "history": [13535.96, 13618.11, 13601.69],
            "realized_pnl": {"today": 3.9, "total": 45.9},
            "performance": {"realized_pnl_today": 3.9, "realized_pnl_total": 45.9, "unrealized_pnl": -2.33},
            "risk_controls": {
                "date": "2026-08-26",
                "day_start_equity": 13535.962581344369,
                "day_peak_equity": 13618.111792229607,
                "halted": True,
                "halt_reason": halt_reason,
                "intraday_drawdown_pct": 0.121,
            },
            "accounting_epoch_id": migration.OLD_EPOCH_ID,
            "paper_accounting_epoch": {
                "id": migration.OLD_EPOCH_ID,
                "prior_epoch_id": migration.PRIOR_EPOCH_ID,
                "historical_recovery_decision": "verified_v2_historical_disposition_successor_rollforward",
                "historical_evidence_archived": True,
                "validation_hold": True,
                "baseline_type": "verified_snapshot_with_open_position",
                "starting_cash": migration.EXPECTED_BASELINE_CASH,
                "starting_equity": migration.EXPECTED_BASELINE_EQUITY,
                "verified_snapshot_baseline": self._baseline_snapshot(),
            },
        }

    def _canonical(self, rows=None):
        rows = rows or self._rows()
        return {
            "status": "ok",
            "row_count": len(rows),
            "chain_valid": True,
            "v3_rows_exact": True,
            "all_execution_ids_unique": True,
            "raw_rows": rows,
        }

    def test_exact_production_rows_project_only_dhr_and_exclude_invalid_sls_partial(self):
        core = types.SimpleNamespace(portfolio=self._portfolio())
        projection = migration._project(core, self._baseline_snapshot(), self._canonical())
        expected_cash, expected_qty, expected_equity = self._projection_numbers()

        self.assertEqual(projection["status"], "ok")
        self.assertEqual(projection["open_symbols"], ["DHR"])
        self.assertEqual(projection["excluded_execution_ids"], [migration.INVALID_EXECUTION_ID])
        self.assertEqual(projection["valid_execution_ids"], [
            migration.EXPECTED_V3_ROWS[0]["execution_id"],
            migration.EXPECTED_V3_ROWS[1]["execution_id"],
        ])
        self.assertAlmostEqual(projection["cash"], expected_cash, places=6)
        self.assertAlmostEqual(projection["positions"]["DHR"]["shares"], expected_qty, places=9)
        self.assertAlmostEqual(projection["equity"], expected_equity, places=6)
        self.assertNotIn("SLS", projection["positions"])

    def test_exact_canonical_signature_fails_closed_on_hash_mismatch_or_extra_v3_row(self):
        import canonical_execution_ledger as ledger
        rows = self._rows()
        with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])):
            observed, ready = migration._canonical_evidence(types.SimpleNamespace())
        self.assertTrue(ready)
        self.assertTrue(observed["v3_rows_exact"])

        bad = copy.deepcopy(rows)
        bad[-1]["event_hash"] = "wrong"
        with mock.patch.object(ledger, "_read_rows", return_value=(bad, [])), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])):
            _, ready = migration._canonical_evidence(types.SimpleNamespace())
        self.assertFalse(ready)

        extra = copy.deepcopy(rows)
        extra.append({
            "execution_id": "unexpected",
            "accounting_epoch_id": migration.OLD_EPOCH_ID,
            "action": "exit",
            "symbol": "DHR",
            "side": "long",
            "price": 220.0,
            "shares": 0.1,
            "event_hash": "unexpected-hash",
        })
        with mock.patch.object(ledger, "_read_rows", return_value=(extra, [])), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])):
            _, ready = migration._canonical_evidence(types.SimpleNamespace())
        self.assertFalse(ready)

    def test_successor_state_preserves_risk_day_halt_and_history(self):
        before = self._portfolio()
        original_risk = copy.deepcopy(before["risk_controls"])
        original_history = copy.deepcopy(before["history"])
        projection = migration._project(types.SimpleNamespace(portfolio=before), self._baseline_snapshot(), self._canonical())
        after = migration.build_successor_state(before, projection, "/archive/issue126", "2026-08-26 14:00:00 CDT")

        self.assertEqual(before["accounting_epoch_id"], migration.OLD_EPOCH_ID)
        self.assertEqual(after["accounting_epoch_id"], migration.TARGET_EPOCH_ID)
        self.assertEqual(after["trades"], [])
        self.assertEqual(sorted(after["positions"]), ["DHR"])
        self.assertEqual(after["risk_controls"], original_risk)
        self.assertEqual(after["history"], original_history)
        epoch = after["paper_accounting_epoch"]
        self.assertTrue(epoch["validation_hold"])
        self.assertFalse(epoch["validation_released"])
        self.assertEqual(epoch["invalid_execution_id"], migration.INVALID_EXECUTION_ID)
        self.assertTrue(epoch["canonical_history_retained_immutably"])

    def test_exact_authoritative_contamination_shape_satisfies_preconditions(self):
        import canonical_execution_ledger as ledger
        import paper_bidirectional_accounting_guard as accounting
        core = types.SimpleNamespace(portfolio=self._portfolio())
        expected_cash, expected_qty, expected_equity = self._projection_numbers()
        accounting_result = {
            "status": "partial",
            "coverage_complete": False,
            "coverage_issues": [{
                "action": "partial_exit",
                "symbol": "SLS",
                "side": "long",
                "reason": "exit_exceeds_reconstructed_position",
                "requested_qty": 1.436519,
                "matched_qty": 0.0,
                "unmatched_qty": 1.436519,
                "price": 16.04,
            }],
            "coverage_issue_count": 1,
            "economic_issues": [],
            "economic_issue_count": 0,
            "cash": expected_cash,
            "equity": expected_equity,
            "open_positions": {
                "DHR": {"side": "long", "qty": expected_qty, "entry_price": 216.960007, "last_price": 215.79}
            },
        }
        rows = self._rows()
        with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])), mock.patch.object(accounting, "analyze_ledger", return_value=accounting_result):
            pre = migration._preconditions(core)
        self.assertEqual(pre["failed"], [])
        self.assertTrue(all(pre["checks"].values()))

    def test_preconditions_do_not_accept_a_different_halt(self):
        import canonical_execution_ledger as ledger
        import paper_bidirectional_accounting_guard as accounting
        core = types.SimpleNamespace(portfolio=self._portfolio(halt_reason="different halt"))
        expected_cash, expected_qty, expected_equity = self._projection_numbers()
        accounting_result = {
            "coverage_issues": [{"action": "partial_exit", "symbol": "SLS", "side": "long", "reason": "exit_exceeds_reconstructed_position", "requested_qty": 1.436519, "price": 16.04}],
            "economic_issues": [],
            "cash": expected_cash,
            "equity": expected_equity,
            "open_positions": {"DHR": {"qty": expected_qty}},
        }
        rows = self._rows()
        with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(ledger, "_verify_rows", return_value=(True, [])), mock.patch.object(accounting, "analyze_ledger", return_value=accounting_result):
            pre = migration._preconditions(core)
        self.assertIn("existing_lifecycle_halt_preserved", pre["failed"])

    def test_cutover_never_changes_canonical_bytes_or_risk_history(self):
        import canonical_execution_ledger as ledger
        import clean_accounting_epoch as clean
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            ledger_path = Path(folder) / "canonical_execution_ledger.jsonl"
            ledger_bytes = b'{"immutable":"canonical"}\n'
            ledger_path.write_bytes(ledger_bytes)
            marker = Path(folder) / "marker.json"
            core = types.SimpleNamespace(portfolio=self._portfolio(), local_ts_text=lambda: "2026-08-26 14:00:00 CDT")
            projection = migration._project(core, self._baseline_snapshot(), self._canonical())
            pre = {"projection": projection, "canonical": {"row_count": 45, "chain_valid": True}}
            risk_before = copy.deepcopy(core.portfolio["risk_controls"])
            history_before = copy.deepcopy(core.portfolio["history"])
            saved = {}

            def write_state(runtime_core, state):
                saved["state"] = copy.deepcopy(state)
                return str(Path(folder) / "state.json")

            with mock.patch.object(ledger, "LEDGER_FILE", str(ledger_path)), \
                 mock.patch.object(clean, "_runtime_locks", return_value=contextlib.nullcontext()), \
                 mock.patch.object(clean, "_write_clean_state_and_backups", side_effect=write_state), \
                 mock.patch.object(clean, "_reset_snapshot_archive", return_value=None), \
                 mock.patch.object(migration, "_archive_state", return_value={"archive_dir": str(Path(folder) / "archive")}), \
                 mock.patch.object(migration, "_rotate_journal_for_successor", return_value=None), \
                 mock.patch.object(migration, "MARKER_FILE", str(marker)):
                result = migration._cutover(core, pre)

            self.assertEqual(ledger_path.read_bytes(), ledger_bytes)
            self.assertTrue(result["canonical_ledger_unchanged"])
            self.assertEqual(core.portfolio["risk_controls"], risk_before)
            self.assertEqual(core.portfolio["history"], history_before)
            self.assertEqual(core.portfolio["accounting_epoch_id"], migration.TARGET_EPOCH_ID)
            self.assertEqual(saved["state"]["trades"], [])

    def test_authority_never_clears_halt_or_edits_ledger(self):
        authority = migration.status_payload(None)["authority"]
        self.assertFalse(authority["edits_or_deletes_canonical_rows"])
        self.assertFalse(authority["rotates_or_truncates_canonical_ledger"])
        self.assertFalse(authority["rewrites_current_day_peak"])
        self.assertFalse(authority["rewrites_history"])
        self.assertFalse(authority["clears_hard_halt"])
        self.assertFalse(authority["places_orders"])
        self.assertFalse(authority["changes_strategy"])
        self.assertFalse(authority["changes_thresholds"])
        self.assertFalse(authority["changes_risk_or_sizing"])
        self.assertFalse(authority["changes_live_or_ml_authority"])


if __name__ == "__main__":
    unittest.main()
