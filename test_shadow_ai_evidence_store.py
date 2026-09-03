from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shadow_ai_evidence_store import EvidenceStoreConfig, ShadowAIEvidenceStore


def record(index: int = 1) -> dict:
    return {
        "cycle_id": f"cycle-{index}",
        "candidate_id": f"TEST{index}:long",
        "input_fingerprint": f"fingerprint-{index}",
        "join_eligible": True,
        "result": {
            "decision": "agree",
            "citations": [],
            "fallback_used": False,
            "telemetry": {"provider": "fake", "model": "fake-v1", "cost_usd_exact": 0.01},
        },
    }


class ShadowAIEvidenceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "evidence.json")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def store(self, **overrides) -> ShadowAIEvidenceStore:
        return ShadowAIEvidenceStore(EvidenceStoreConfig(path=self.path, **overrides))

    def test_missing_store_loads_as_valid_empty_without_creating_file(self):
        status = self.store().load()
        self.assertTrue(status["integrity_valid"])
        self.assertTrue(status["restart_loadable"])
        self.assertEqual(status["record_count"], 0)
        self.assertFalse(Path(self.path).exists())

    def test_atomic_snapshot_is_restart_loadable(self):
        first = self.store()
        self.assertEqual(first.append(record())["status"], "persisted")
        restarted = self.store()
        status = restarted.load()
        self.assertTrue(status["integrity_valid"])
        self.assertEqual(restarted.records_snapshot(), (record(),))
        self.assertFalse(Path(self.path + ".tmp").exists())

    def test_retention_is_bounded(self):
        store = self.store(max_records=2)
        for index in range(1, 4):
            self.assertEqual(store.append(record(index))["status"], "persisted")
        self.assertEqual([row["cycle_id"] for row in store.records_snapshot()], ["cycle-2", "cycle-3"])

    def test_duplicate_is_idempotent_and_conflict_fails_closed(self):
        store = self.store()
        store.append(record())
        self.assertEqual(store.append(record())["status"], "deduplicated")
        changed = record()
        changed["result"]["decision"] = "reject"
        rejected = store.append(changed)
        self.assertEqual(rejected, {"status": "rejected", "reason": "contradictory_record_identity"})

    def test_corrupt_checksum_is_not_overwritten(self):
        store = self.store()
        store.append(record())
        payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        payload["records"][0]["join_eligible"] = False
        Path(self.path).write_text(json.dumps(payload), encoding="utf-8")
        before = Path(self.path).read_bytes()

        restarted = self.store()
        status = restarted.load()
        self.assertFalse(status["integrity_valid"])
        self.assertEqual(restarted.append(record(2))["reason"], "store_integrity_error")
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_forbidden_and_oversized_records_are_rejected(self):
        store = self.store(max_record_bytes=1_024)
        forbidden = record()
        forbidden["result"]["prompt"] = "do not persist"
        self.assertIn("forbidden_key", store.append(forbidden)["reason"])
        secret = record(2)
        secret["result"]["access_token"] = "do not persist"
        self.assertIn("forbidden_key", store.append(secret)["reason"])
        oversized = record(3)
        oversized["result"]["risk_factors"] = ["x" * 2_000]
        self.assertEqual(store.append(oversized)["reason"], "record_too_large")

    def test_store_status_has_no_trading_authority(self):
        authority = self.store().load()["authority"]
        self.assertTrue(authority["research_evidence_only"])
        self.assertTrue(authority["separate_from_portfolio_state"])
        self.assertTrue(authority["separate_from_canonical_ledger"])
        self.assertFalse(authority["execution_input"])
        self.assertFalse(authority["places_or_cancels_orders"])


if __name__ == "__main__":
    unittest.main()
