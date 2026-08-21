from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verified_snapshot_backup_provenance_status as probe


class DummyCore:
    def local_ts_text(self):
        return "2026-08-21 12:10:00 CDT"


class VerifiedSnapshotBackupProvenanceStatusTests(unittest.TestCase):
    def _patch_root(self, root: str):
        snapshot_dir = os.path.join(root, "state_snapshots")
        return mock.patch.multiple(
            probe,
            STATE_DIR=root,
            STATE_FILE=os.path.join(root, "state.json"),
            BACKUP_FILES=(
                os.path.join(root, "state.json.bak"),
                os.path.join(root, "state_backup_latest.json"),
                os.path.join(root, "state_backup_prewrite.json"),
                os.path.join(root, "state_backup_largest.json"),
            ),
            SNAPSHOT_DIR=snapshot_dir,
            SNAPSHOT_MANIFEST=os.path.join(snapshot_dir, "manifest.json"),
        )

    def _verified_state_text(self) -> str:
        return json.dumps(
            {
                "cash": 10768.497731,
                "equity": 11915.688807,
                "positions": {"LRCX": {"qty": 3.42486}},
                "trades": [],
                "accounting_epoch_id": probe.VERIFIED_EPOCH_ID,
                "paper_accounting_epoch": {
                    "id": probe.VERIFIED_EPOCH_ID,
                    "decision_id": probe.VERIFIED_DECISION_ID,
                    "baseline_type": probe.VERIFIED_BASELINE_TYPE,
                    "historical_recovery_decision": probe.VERIFIED_RECOVERY_DECISION,
                    "historical_evidence_archived": True,
                    "prior_epoch_id": probe.CLEAN_EPOCH_ID,
                    "forensic_archive_dir": "/data/forensic_archives/example",
                    "verified_snapshot_baseline": {
                        "bad_tick_reversed": {"execution_id": probe.BAD_EXECUTION_ID}
                    },
                },
            },
            separators=(",", ":"),
        )

    def test_verified_backup_block_is_proven_without_full_json_load(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            path = Path(root) / "state.json.bak"
            path.write_text(self._verified_state_text(), encoding="utf-8")
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "pass")
            self.assertEqual(
                payload["diagnosis"], "verified_snapshot_backup_provenance_found"
            )
            self.assertTrue(payload["verified_snapshot_backup_evidence_found"])
            self.assertEqual(payload["verified_signature_paths"], [str(path)])
            row = payload["backup_files"][0]
            self.assertTrue(row["verified_signature"])
            self.assertEqual(row["epoch_block"]["id"], probe.VERIFIED_EPOCH_ID)
            self.assertEqual(
                row["epoch_block"]["decision_id"], probe.VERIFIED_DECISION_ID
            )
            self.assertFalse(
                payload["performance_contract"]["loads_whole_state_files_into_memory"]
            )

    def test_token_without_exact_epoch_block_is_not_overstated(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            path = Path(root) / "state_backup_latest.json"
            path.write_text(
                json.dumps(
                    {
                        "cash": -26064.31,
                        "reports": {"note": probe.VERIFIED_EPOCH_ID},
                        "paper_accounting_epoch": {},
                    }
                ),
                encoding="utf-8",
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "warn")
            self.assertEqual(
                payload["diagnosis"],
                "verified_epoch_token_found_without_verified_epoch_block_signature",
            )
            self.assertFalse(payload["verified_snapshot_backup_evidence_found"])
            self.assertIn(str(path), payload["verified_token_only_paths"])

    def test_clean_backup_only_is_reported_as_incomplete_provenance(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            path = Path(root) / "state_backup_largest.json"
            path.write_text(
                json.dumps(
                    {
                        "accounting_epoch_id": probe.CLEAN_EPOCH_ID,
                        "paper_accounting_epoch": {
                            "id": probe.CLEAN_EPOCH_ID,
                            "decision_id": probe.CLEAN_DECISION_ID,
                        },
                    }
                ),
                encoding="utf-8",
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "warn")
            self.assertEqual(
                payload["diagnosis"],
                "clean_epoch_backup_provenance_found_verified_snapshot_missing",
            )
            self.assertIn(str(path), payload["clean_signature_paths"])

    def test_targeted_zero_trade_snapshot_can_prove_verified_epoch(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            snapshot_dir = Path(root) / "state_snapshots"
            snapshot_dir.mkdir(parents=True)
            snapshot = snapshot_dir / "state_t000000_r0_20260812_100000.json"
            snapshot.write_text(self._verified_state_text(), encoding="utf-8")
            manifest = {
                "status": "ok",
                "snapshots": [
                    {
                        "path": str(snapshot),
                        "filename": snapshot.name,
                        "created_local": "2026-08-12 10:00:00",
                        "created_ts": 1786546800,
                        "trades_count": 0,
                        "positions_count": 1,
                        "runner_timestamp_rank": 0,
                        "size_bytes": snapshot.stat().st_size,
                        "reason": "execution_advanced",
                    }
                ],
            }
            (snapshot_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            payload = probe.status_payload(DummyCore())
            self.assertEqual(payload["overall"], "pass")
            self.assertTrue(payload["verified_snapshot_backup_evidence_found"])
            self.assertIn(str(snapshot), payload["verified_signature_paths"])
            self.assertEqual(len(payload["targeted_snapshot_files"]), 1)

    def test_status_is_read_only_and_apply_does_not_scan(self):
        with tempfile.TemporaryDirectory() as root, self._patch_root(root):
            path = Path(root) / "state.json.bak"
            path.write_text(self._verified_state_text(), encoding="utf-8")
            before = {
                str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in Path(root).rglob("*")
                if p.is_file()
            }
            payload = probe.status_payload(DummyCore())
            after = {
                str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in Path(root).rglob("*")
                if p.is_file()
            }
            self.assertEqual(before, after)
            self.assertFalse(payload["authority"]["writes_files"])
            self.assertFalse(payload["authority"]["restores_backups"])
            self.assertFalse(payload["authority"]["deletes_or_prunes_snapshots"])

            with mock.patch.object(
                probe, "_scan_state_file", side_effect=AssertionError("startup scanned")
            ):
                applied = probe.apply(DummyCore())
            self.assertEqual(applied["status"], "ok")
            self.assertFalse(applied["startup_scans_backups"])


if __name__ == "__main__":
    unittest.main()
