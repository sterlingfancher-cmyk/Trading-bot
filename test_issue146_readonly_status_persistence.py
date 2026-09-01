from __future__ import annotations

import json
import os
import tempfile
import types
import unittest

from flask import Flask

import state_journal_apply_guardrail as guardrail


class Issue146ReadonlyStatusPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        guardrail._CORE_SAVE_PATCHED.clear()
        guardrail._LAST_STALE_WRITE_BLOCK.clear()
        self.app = Flask(__name__)
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = os.path.join(self.tmp.name, "state.json")
        self.journal_file = os.path.join(self.tmp.name, "trade_journal.json")
        with open(self.state_file, "w", encoding="utf-8") as handle:
            json.dump({"cash": 10000.0, "positions": {}}, handle)
        with open(self.journal_file, "w", encoding="utf-8") as handle:
            json.dump([], handle)

        self.save_calls = []
        self.guard_calls = []

        def original_save(state, *args, **kwargs):
            self.save_calls.append(state)
            return "saved"

        def build_guard(*, state, journal, core=None):
            self.guard_calls.append((state, journal, core))
            return {"status": "ok", "active": False}

        self.core = types.SimpleNamespace(save_state=original_save)
        self.guard_module = types.SimpleNamespace(
            TRADE_JOURNAL_FILE=self.journal_file,
            build_guard=build_guard,
        )
        result = guardrail._install_core_stale_write_guard(
            self.core, self.guard_module, self.state_file
        )
        self.assertEqual(result["status"], "ok")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_paper_status_skips_persistence_and_reconciliation(self) -> None:
        with self.app.test_request_context("/paper/status", method="GET"):
            result = self.core.save_state({"cash": 10000.0, "positions": {}})
        self.assertIsNone(result)
        self.assertEqual(self.save_calls, [])
        self.assertEqual(self.guard_calls, [])

    def test_head_paper_status_skips_persistence_and_reconciliation(self) -> None:
        with self.app.test_request_context("/paper/status", method="HEAD"):
            self.core.save_state({"cash": 10000.0, "positions": {}})
        self.assertEqual(self.save_calls, [])
        self.assertEqual(self.guard_calls, [])

    def test_non_status_save_preserves_stale_write_guard_and_persistence(self) -> None:
        state = {"cash": 10000.0, "positions": {}}
        with self.app.test_request_context("/paper/run", method="POST"):
            result = self.core.save_state(state)
        self.assertEqual(result, "saved")
        self.assertEqual(self.save_calls, [state])
        self.assertEqual(len(self.guard_calls), 2)

    def test_status_post_is_not_suppressed(self) -> None:
        state = {"cash": 10000.0, "positions": {}}
        with self.app.test_request_context("/paper/status", method="POST"):
            result = self.core.save_state(state)
        self.assertEqual(result, "saved")
        self.assertEqual(self.save_calls, [state])
        self.assertEqual(len(self.guard_calls), 2)


if __name__ == "__main__":
    unittest.main()
