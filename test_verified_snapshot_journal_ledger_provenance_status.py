from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verified_snapshot_journal_ledger_provenance_status as probe


class DummyCore:
    def local_ts_text(self):
        return "2026-08-21 12:50:00 CDT"


class VerifiedSnapshotJournalLedgerProvenanceTests(unittest.TestCase):
    def _patch_root(self, root: str):
        return mock.patch.multiple(
            probe,
            STATE_DIR=root,
            JOURNAL_FILES=(
                os.path.join(root, "trade_journal.json"),
                os.path.join(root, "trade_journal_backup.json"),
            ),
            LEDGER_FILE=os.path.join(root, "canonical_execution_ledger.jsonl"),
        )

    @staticmethod
    def _canonical_json(payload):
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

    def _write_ledger(self, path: Path, recorded_times, epoch="legacy-pre-stable-core"):
        previous = ""
        rows = []
        for index, recorded in enumerate(recorded_times, start=1):
            body = {
                "execution_id": f"exec-{index}",
                "ledger_version": "canonical-execution-ledger-2026-08-10-v1",
                "recorded_local": recorded,
                "accounting_epoch_id": epoch,
                "action": "entry" if index % 2 else "exit",
                "symbol": "TEST",
                "side": "long",
                "price": 100.0 + index,
                "shares": 1.0,
            }
            event_hash = hashlib.sha256(
                (previous + "|" + self._canonical_json(body)).encode("utf-8")
            ).hexdigest()
            row = dict(body)
            row["previous_event_hash"] = previous
            row["event_hash"] = event_hash
            rows.append(row)
            previous = event_hash
        path.write_text(
            "".join(self._canonical_json(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _write_verified_journal(self, path: Path):
        payload = {
            "accounting_epoch_id": probe.VERIFIED_EPOCH_ID,
            "created_local": "2026-08-10 13:00:00",
            "snapshots": [
                {
                    "accounting_epoch_id": "nested-misleading-value",
                    "verified_snapshot_epoch_started_local": "1999-01-01 00:00:00",
                }
            ],
            "trades": [],
            "updated_local": "2026-08-21 12:00:00",
            "verified_snapshot_epoch_started_local": "2026-08-12 16:00:00 CDT",
            "version": "trade-journal-2026-08-10-v1",
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def test_verified_journal_plus_post_cutover_valid_ledger_is_proven(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            self._write_verified_journal(Path(root) / "trade_journal.json")
            self._write_ledger(
                Path(root) / "canonical_execution_ledger.jsonl",
                ["2026-08-12 16:05:00 CDT", "2026-08-13 09:30:00 CDT"],
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "pass")
            self.assertEqual(
                payload["diagnosis"],
                "verified_journal_cutover_with_post_cutover_ledger_provenance_found",
            )
            self.assertTrue(payload["verified_journal_epoch_found"])
            self.assertTrue(payload["canonical_ledger"]["chain_valid"])
            self.assertEqual(payload["canonical_ledger"]["row_count"], 2)
            self.assertEqual(
                payload["canonical_ledger"]["epoch_counts"],
                {"legacy-pre-stable-core": 2},
            )
            self.assertTrue(
                payload["chronology"]["all_ledger_rows_at_or_after_verified_start"]
            )
            self.assertFalse(payload["authority"]["writes_files"])
            self.assertFalse(
                payload["authority"]["rewrites_or_relabels_canonical_ledger"]
            )

    def test_nested_verified_tokens_do_not_count_as_top_level_epoch(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            journal = {
                "accounting_epoch_id": "legacy-pre-stable-core",
                "snapshots": [
                    {
                        "accounting_epoch_id": probe.VERIFIED_EPOCH_ID,
                        "verified_snapshot_epoch_started_local": "2026-08-12 16:00:00 CDT",
                    }
                ],
                "trades": [],
            }
            (Path(root) / "trade_journal.json").write_text(
                json.dumps(journal), encoding="utf-8"
            )
            self._write_ledger(
                Path(root) / "canonical_execution_ledger.jsonl",
                ["2026-08-13 09:30:00 CDT"],
            )
            payload = probe.status_payload(DummyCore())

            self.assertFalse(payload["verified_journal_epoch_found"])
            self.assertEqual(
                payload["diagnosis"], "verified_journal_provenance_not_found"
            )
            top = payload["journal_files"][0]["top_level"]
            self.assertEqual(top.get("accounting_epoch_id"), "legacy-pre-stable-core")
            self.assertNotIn("verified_snapshot_epoch_started_local", top)

    def test_pre_cutover_ledger_row_prevents_chronology_claim(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            self._write_verified_journal(Path(root) / "trade_journal.json")
            self._write_ledger(
                Path(root) / "canonical_execution_ledger.jsonl",
                ["2026-08-12 15:59:59 CDT", "2026-08-12 16:05:00 CDT"],
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "warn")
            self.assertEqual(
                payload["diagnosis"],
                "verified_journal_epoch_found_but_ledger_chronology_not_proven",
            )
            self.assertFalse(
                payload["chronology"]["all_ledger_rows_at_or_after_verified_start"]
            )

    def test_hash_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            self._write_verified_journal(Path(root) / "trade_journal.json")
            ledger = Path(root) / "canonical_execution_ledger.jsonl"
            self._write_ledger(ledger, ["2026-08-12 16:05:00 CDT"])
            row = json.loads(ledger.read_text(encoding="utf-8"))
            row["price"] = 999.0
            ledger.write_text(self._canonical_json(row) + "\n", encoding="utf-8")

            payload = probe.status_payload(DummyCore())
            self.assertEqual(payload["overall"], "fail")
            self.assertFalse(payload["canonical_ledger"]["chain_valid"])
            self.assertEqual(
                payload["diagnosis"],
                "verified_journal_epoch_found_but_canonical_ledger_not_valid",
            )

    def test_status_is_read_only_and_startup_apply_does_not_scan(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            journal = Path(root) / "trade_journal.json"
            ledger = Path(root) / "canonical_execution_ledger.jsonl"
            self._write_verified_journal(journal)
            self._write_ledger(ledger, ["2026-08-12 16:05:00 CDT"])
            before = {
                str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in Path(root).rglob("*")
                if path.is_file()
            }
            probe.status_payload(DummyCore())
            after = {
                str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in Path(root).rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)

            with mock.patch.object(
                probe,
                "_stream_top_level_strings",
                side_effect=AssertionError("startup scanned journal"),
            ), mock.patch.object(
                probe,
                "_ledger_summary",
                side_effect=AssertionError("startup scanned ledger"),
            ):
                applied = probe.apply(DummyCore())
            self.assertEqual(applied["status"], "ok")
            self.assertFalse(applied["startup_scans_files"])


if __name__ == "__main__":
    unittest.main()
