from __future__ import annotations

import contextlib
import copy
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

import canonical_execution_ledger as ledger
import clean_accounting_epoch as clean
import clean_epoch_successor_compatibility as compatibility
import issue222_verified_flat_successor as recovery
import paper_bidirectional_accounting_guard as accounting
import trade_journal
import verified_v4_validation_release as v4_release


def _fixture():
    rows = []
    for index in range(20):
        rows.append({
            "execution_id": f"before-{index}", "accounting_epoch_id": recovery.OLD_EPOCH_ID,
            "event_hash": f"before-hash-{index}", "previous_event_hash": f"before-prev-{index}",
            "action": "entry" if index % 2 == 0 else "exit", "symbol": f"B{index}",
            "side": "long", "price": 10.0 + index, "shares": 1.0,
        })
    for expected in recovery.EXPECTED_MISSING_ROWS:
        row = copy.deepcopy(expected)
        if "execution_id" not in row:
            available = sorted(recovery.EXPECTED_MISSING_IDS - {str(r.get("execution_id")) for r in rows})
            available = [value for value in available if value != "9cad03cbec994e29a9b65293d573f54b"]
            row["execution_id"] = available[0]
        rows.append(row)
    used = {str(row.get("execution_id")) for row in rows}
    for index in range(18):
        execution_id = f"after-{index}"
        if index == 17:
            execution_id = recovery.EXPECTED_LAST_EXECUTION_ID
        rows.append({
            "execution_id": execution_id, "accounting_epoch_id": recovery.OLD_EPOCH_ID,
            "event_hash": f"after-hash-{index}", "previous_event_hash": f"after-prev-{index}",
            "action": "exit" if index == 17 else ("entry" if index % 2 == 0 else "exit"),
            "symbol": "ORCL" if index == 17 else f"A{index}",
            "side": "short" if index == 17 else "long",
            "price": 142.275 if index == 17 else 20.0 + index,
            "shares": 4.383375 if index == 17 else 1.0,
        })
    missing_ids = recovery.EXPECTED_MISSING_IDS
    state_trades = []
    for row in rows:
        if str(row.get("execution_id")) in missing_ids:
            continue
        mirrored = copy.deepcopy(row)
        mirrored["canonical_ledger_event_hash"] = row["event_hash"]
        state_trades.append(mirrored)
    state = {
        "accounting_epoch_id": recovery.OLD_EPOCH_ID,
        "paper_accounting_epoch": {
            "id": recovery.OLD_EPOCH_ID,
            "validation_hold": False,
            "validation_released": True,
            "validation_release_status": "released",
            "historical_evidence_archived": True,
        },
        "cash": recovery.EXPECTED_CASH,
        "equity": recovery.EXPECTED_EQUITY,
        "positions": {},
        "trades": state_trades,
        "realized_pnl": {"today": 48.63, "total": -514.18},
        "performance": {
            "open_positions": {}, "unrealized_pnl": 0.0,
            "realized_pnl_today": 48.63, "realized_pnl_total": -514.18,
        },
        "risk_controls": {
            "halted": True, "halt_reason": recovery.HALT_REASON,
            "day_start_equity": 13380.5, "day_peak_equity": 13429.13,
            "canonical_state_projection_missing_execution_ids": sorted(missing_ids),
        },
        "history": [13380.5, 13429.13],
    }
    assert len(rows) == recovery.EXPECTED_CURRENT_EPOCH_ROWS
    assert len(state_trades) == recovery.EXPECTED_STATE_ROWS
    return rows, state


def _accounting_result():
    return {
        "coverage_complete": True,
        "coverage_issue_count": 0,
        "economic_issue_count": 0,
        "cash": recovery.EXPECTED_CASH,
        "equity": recovery.EXPECTED_EQUITY,
        "open_positions": {},
    }


class Issue222VerifiedFlatSuccessorTests(unittest.TestCase):
    def _patches(self, root: Path, rows, state):
        ledger_path = root / "canonical.jsonl"
        ledger_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        journal = root / "journal.json"
        journal_backup = root / "journal.backup.json"
        journal.write_text(json.dumps({"trades": state["trades"]}), encoding="utf-8")
        journal_backup.write_text(json.dumps({"trades": state["trades"]}), encoding="utf-8")

        def write_state(_core, successor):
            path = root / "state.json"
            path.write_text(json.dumps(successor, default=str), encoding="utf-8")
            return str(path)

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(recovery, "STATE_DIR", str(root)))
        stack.enter_context(mock.patch.object(recovery, "ARCHIVE_ROOT", str(root / "forensic_archives")))
        stack.enter_context(mock.patch.object(recovery, "MARKER_FILE", str(root / "marker.json")))
        stack.enter_context(mock.patch.object(ledger, "LEDGER_FILE", str(ledger_path)))
        stack.enter_context(mock.patch.object(ledger, "_read_rows", return_value=(copy.deepcopy(rows), [])))
        stack.enter_context(mock.patch.object(ledger, "_verify_rows", return_value=(True, [])))
        stack.enter_context(mock.patch.object(accounting, "analyze_ledger", return_value=_accounting_result()))
        stack.enter_context(mock.patch.object(clean, "_runtime_locks", return_value=contextlib.nullcontext()))
        stack.enter_context(mock.patch.object(clean, "_write_clean_state_and_backups", side_effect=write_state))
        stack.enter_context(mock.patch.object(clean, "_reset_snapshot_archive", return_value=None))
        stack.enter_context(mock.patch.object(trade_journal, "TRADE_JOURNAL_FILE", str(journal)))
        stack.enter_context(mock.patch.object(trade_journal, "TRADE_JOURNAL_BACKUP_FILE", str(journal_backup)))
        return stack, ledger_path, journal

    def test_exact_verified_flat_successor_preserves_evidence_and_halt(self):
        rows, state = _fixture()
        before_risk = copy.deepcopy(state["risk_controls"])
        before_history = copy.deepcopy(state["history"])
        before_trades = copy.deepcopy(state["trades"])
        core = types.SimpleNamespace(
            portfolio=state,
            local_ts_text=lambda: "2026-09-14 13:30:00 CDT",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stack, ledger_path, journal = self._patches(root, rows, state)
            digest_before = recovery._sha256(str(ledger_path))
            with stack:
                result = recovery.apply(core)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(core.portfolio["accounting_epoch_id"], recovery.TARGET_EPOCH_ID)
            self.assertEqual(core.portfolio["positions"], {})
            self.assertEqual(core.portfolio["trades"], [])
            self.assertEqual(core.portfolio["risk_controls"], before_risk)
            self.assertEqual(core.portfolio["history"], before_history)
            self.assertTrue(core.portfolio["paper_accounting_epoch"]["validation_hold"])
            self.assertFalse(core.portfolio["paper_accounting_epoch"]["prior_epoch_economics_promotable"])
            self.assertEqual(core.portfolio["paper_accounting_epoch"]["fabricated_exit_rows"], 0)
            self.assertEqual(recovery._sha256(str(ledger_path)), digest_before)
            self.assertTrue(result["canonical_ledger_unchanged"])
            self.assertTrue(Path(result["archive_dir"]).exists())
            archived = json.loads(
                (Path(result["archive_dir"]) / "issue222_verified_flat_successor_manifest.json").read_text()
            )
            self.assertEqual(archived["pre_cutover_account"]["trades"], before_trades)
            self.assertEqual(archived["unresolved_prior_discrepancy"]["status"], "unresolved_non_promotable")
            self.assertEqual(json.loads(journal.read_text())["accounting_epoch_id"], recovery.TARGET_EPOCH_ID)

    def test_possible_later_exit_blocks_without_state_write(self):
        rows, state = _fixture()
        rows[-2].update({
            "symbol": "SPCX", "side": "short", "action": "exit",
            "recorded_local": "2026-09-14 12:00:00 CDT",
            "entry_price": 148.88, "realized_pnl": -1.25,
            "reason": "trailing_stop", "parent_execution_id": "entry-1",
        })
        core = types.SimpleNamespace(portfolio=state)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stack, _, _ = self._patches(root, rows, state)
            with stack:
                result = recovery.apply(core)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("canonical_evidence_exact", result["failed_checks"])
            candidate = result["canonical"]["later_exit_candidates"][0]
            self.assertEqual(candidate["previous_event_hash"], rows[-2]["previous_event_hash"])
            self.assertEqual(candidate["recorded_local"], "2026-09-14 12:00:00 CDT")
            self.assertEqual(candidate["entry_price"], 148.88)
            self.assertEqual(candidate["realized_pnl"], -1.25)
            self.assertEqual(candidate["reason"], "trailing_stop")
            self.assertEqual(candidate["parent_execution_id"], "entry-1")
            self.assertEqual(state["accounting_epoch_id"], recovery.OLD_EPOCH_ID)
            self.assertFalse((root / "marker.json").exists())

    def test_signature_or_missing_set_drift_blocks(self):
        rows, state = _fixture()
        rows[20]["price"] += 0.01
        core = types.SimpleNamespace(portfolio=state)
        with tempfile.TemporaryDirectory() as directory:
            stack, _, _ = self._patches(Path(directory), rows, state)
            with stack:
                result = recovery.apply(core)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(state["trades"], _fixture()[1]["trades"])

    def test_nonflat_or_unclean_accounting_blocks(self):
        rows, state = _fixture()
        state["positions"] = {"QQQ": {"side": "long", "shares": 1, "entry": 100}}
        core = types.SimpleNamespace(portfolio=state)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stack, _, _ = self._patches(root, rows, state)
            stack.enter_context(mock.patch.object(
                accounting, "analyze_ledger",
                return_value={**_accounting_result(), "coverage_issue_count": 1},
            ))
            with stack:
                result = recovery.apply(core)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("current_state_flat", result["failed_checks"])
        self.assertIn("independent_accounting_clean_flat", result["failed_checks"])

    def test_interrupted_marker_retries_only_exact_old_shape(self):
        rows, state = _fixture()
        core = types.SimpleNamespace(portfolio=state, local_ts_text=lambda: "2026-09-14 13:31:00 CDT")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stack, _, _ = self._patches(root, rows, state)
            marker = {
                "status": "cutover_started", "prior_epoch_id": recovery.OLD_EPOCH_ID,
                "target_epoch_id": recovery.TARGET_EPOCH_ID,
                "missing_execution_ids": sorted(recovery.EXPECTED_MISSING_IDS),
                "fabricated_exit_rows": 0,
            }
            (root / "marker.json").write_text(json.dumps(marker), encoding="utf-8")
            with stack:
                result = recovery.apply(core)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["interrupted_completion_retry_performed"])

    def test_concurrent_apply_serializes_to_one_cutover(self):
        rows, state = _fixture()
        core = types.SimpleNamespace(portfolio=state, local_ts_text=lambda: "2026-09-14 13:32:00 CDT")
        results = []
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stack, _, _ = self._patches(root, rows, state)
            with stack:
                def run():
                    try:
                        results.append(recovery.apply(core))
                    except Exception as exc:
                        errors.append(exc)
                threads = [threading.Thread(target=run) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(result["status"] for result in results), ["completed", "validation_hold"])
        self.assertEqual(core.portfolio["accounting_epoch_id"], recovery.TARGET_EPOCH_ID)
        archives = list((root / "forensic_archives").glob("*"))
        self.assertEqual(len(archives), 1)

    def test_active_epoch_without_completed_marker_fails_closed(self):
        _, state = _fixture()
        state["accounting_epoch_id"] = recovery.TARGET_EPOCH_ID
        state["paper_accounting_epoch"]["id"] = recovery.TARGET_EPOCH_ID
        core = types.SimpleNamespace(portfolio=state)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(recovery, "MARKER_FILE", str(Path(directory) / "missing.json")):
                result = recovery.apply(core)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "v5_active_without_completed_issue222_marker")

    def test_live_runtime_is_blocked(self):
        _, state = _fixture()
        core = types.SimpleNamespace(portfolio=state)
        with mock.patch.object(recovery.v3, "_paper_only", return_value=False):
            result = recovery.apply(core)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "paper_runtime_only")


class Issue222SuccessorCompatibilityTests(unittest.TestCase):
    def _v5_state(self):
        _, state = _fixture()
        state["accounting_epoch_id"] = recovery.TARGET_EPOCH_ID
        state["paper_accounting_epoch"] = {
            "id": recovery.TARGET_EPOCH_ID,
            "prior_epoch_id": recovery.OLD_EPOCH_ID,
            "historical_recovery_decision": recovery.HISTORICAL_DECISION,
            "historical_evidence_archived": True,
            "validation_hold": True,
            "prior_epoch_discrepancy_status": "unresolved_non_promotable",
            "prior_epoch_economics_promotable": False,
            "fabricated_exit_rows": 0,
        }
        return state

    def test_clean_epoch_compatibility_accepts_only_exact_v5_lineage(self):
        state = self._v5_state()
        core = types.SimpleNamespace(portfolio=state)
        self.assertEqual(compatibility._successor_epoch(core), recovery.TARGET_EPOCH_ID)
        state["paper_accounting_epoch"]["fabricated_exit_rows"] = 1
        self.assertIsNone(compatibility._successor_epoch(core))

    def test_v4_release_is_superseded_without_mutation(self):
        state = self._v5_state()
        before = copy.deepcopy(state)
        core = types.SimpleNamespace(portfolio=state)
        result = v4_release.apply(core)
        status = v4_release.status_payload(core)
        self.assertEqual(result["status"], "superseded")
        self.assertEqual(status["status"], "superseded")
        self.assertEqual(status["superseded_by_epoch_id"], recovery.TARGET_EPOCH_ID)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
