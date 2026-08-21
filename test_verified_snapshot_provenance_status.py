from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verified_snapshot_provenance_status as probe


class DummyCore:
    def __init__(self, portfolio=None):
        self.portfolio = portfolio or {}

    def local_ts_text(self):
        return "2026-08-21 11:00:00 CDT"


class VerifiedSnapshotProvenanceStatusTests(unittest.TestCase):
    def _paths(self, root: str):
        archive_root = os.path.join(root, "forensic_archives")
        clean_marker = os.path.join(
            root, f"clean_epoch_{probe.CLEAN_DECISION_ID}.json"
        )
        verified_marker = os.path.join(
            root, f"verified_snapshot_{probe.VERIFIED_DECISION_ID}.json"
        )
        return archive_root, clean_marker, verified_marker

    def _patch_paths(self, root: str):
        archive_root, clean_marker, verified_marker = self._paths(root)
        return mock.patch.multiple(
            probe,
            STATE_DIR=root,
            ARCHIVE_ROOT=archive_root,
            CLEAN_MARKER_FILE=clean_marker,
            VERIFIED_MARKER_FILE=verified_marker,
        )

    def test_absent_provenance_is_warn_and_read_only(self):
        with tempfile.TemporaryDirectory() as root, self._patch_paths(root):
            before = sorted(str(p.relative_to(root)) for p in Path(root).rglob("*"))
            payload = probe.status_payload(DummyCore({"cash": -10.0, "equity": -10.0}))
            after = sorted(str(p.relative_to(root)) for p in Path(root).rglob("*"))

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["overall"], "warn")
            self.assertEqual(
                payload["diagnosis"], "recovery_markers_and_verified_archive_not_found"
            )
            self.assertFalse(payload["durable_verified_evidence_found"])
            self.assertEqual(before, after)
            self.assertFalse(payload["authority"]["writes_files"])
            self.assertFalse(payload["authority"]["restores_backups"])
            self.assertFalse(payload["authority"]["rewrites_canonical_ledger"])

    def test_exact_verified_marker_is_durable_provenance(self):
        with tempfile.TemporaryDirectory() as root, self._patch_paths(root):
            _, _, verified_marker = self._paths(root)
            Path(verified_marker).write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "decision_id": probe.VERIFIED_DECISION_ID,
                        "target_epoch_id": probe.VERIFIED_EPOCH_ID,
                        "archive_dir": "/data/forensic_archives/example",
                        "started_local": "2026-08-12 10:00:00 CDT",
                        "completed_local": "2026-08-12 10:01:00 CDT",
                    }
                ),
                encoding="utf-8",
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "pass")
            self.assertEqual(
                payload["diagnosis"], "verified_snapshot_durable_provenance_found"
            )
            self.assertTrue(payload["verified_snapshot_marker_found"])
            self.assertTrue(payload["durable_verified_evidence_found"])

    def test_exact_verified_archive_manifest_is_durable_provenance(self):
        with tempfile.TemporaryDirectory() as root, self._patch_paths(root):
            archive_root, _, _ = self._paths(root)
            archive_dir = Path(archive_root) / "20260812_100000_verified"
            archive_dir.mkdir(parents=True)
            (archive_dir / probe.MANIFEST_NAME).write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "decision_id": probe.VERIFIED_DECISION_ID,
                        "old_epoch_id": probe.CLEAN_EPOCH_ID,
                        "target_epoch_id": probe.VERIFIED_EPOCH_ID,
                        "created_local": "2026-08-12 10:00:00 CDT",
                        "bad_execution_id": "5ca38922916e4612ae3cda8d9801107d",
                    }
                ),
                encoding="utf-8",
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "pass")
            self.assertTrue(payload["verified_snapshot_archive_found"])
            self.assertEqual(
                payload["verified_snapshot_archives"]["matching_manifest_count"], 1
            )
            match = payload["verified_snapshot_archives"]["matching_manifests"][0]
            self.assertEqual(match["target_epoch_id"], probe.VERIFIED_EPOCH_ID)

    def test_clean_marker_without_verified_evidence_is_not_overstated(self):
        with tempfile.TemporaryDirectory() as root, self._patch_paths(root):
            _, clean_marker, _ = self._paths(root)
            Path(clean_marker).write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "decision_id": probe.CLEAN_DECISION_ID,
                        "target_epoch_id": probe.CLEAN_EPOCH_ID,
                    }
                ),
                encoding="utf-8",
            )
            payload = probe.status_payload(DummyCore())

            self.assertEqual(payload["overall"], "warn")
            self.assertTrue(payload["clean_epoch_marker_found"])
            self.assertFalse(payload["durable_verified_evidence_found"])
            self.assertEqual(
                payload["diagnosis"],
                "clean_epoch_provenance_found_verified_snapshot_missing",
            )

    def test_active_epoch_summary_uses_memory_and_does_not_read_state_file(self):
        portfolio = {
            "cash": 10768.49,
            "equity": 11915.69,
            "positions": {"LRCX": {"qty": 3.4}},
            "trades": [],
            "accounting_epoch_id": probe.VERIFIED_EPOCH_ID,
            "paper_accounting_epoch": {
                "id": probe.VERIFIED_EPOCH_ID,
                "decision_id": probe.VERIFIED_DECISION_ID,
                "baseline_type": "verified_snapshot_with_open_position",
                "historical_recovery_decision": "verified_snapshot_rollforward",
                "historical_evidence_archived": True,
                "forensic_archive_dir": "/data/forensic_archives/example",
                "validation_hold": True,
            },
        }
        with tempfile.TemporaryDirectory() as root, self._patch_paths(root):
            payload = probe.status_payload(DummyCore(portfolio))
            active = payload["active_runtime"]

            self.assertEqual(active["paper_accounting_epoch_id"], probe.VERIFIED_EPOCH_ID)
            self.assertEqual(active["positions_count"], 1)
            self.assertEqual(
                active["baseline_type"], "verified_snapshot_with_open_position"
            )
            self.assertFalse(payload["performance_contract"]["reads_large_state_or_backup_files"])


if __name__ == "__main__":
    unittest.main()
