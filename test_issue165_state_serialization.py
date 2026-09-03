from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import cycle_completion_contract as completion
import state_io_hardening as state_io


class Issue165StateSerializationTests(unittest.TestCase):
    def test_atomic_write_retries_transient_dictionary_mutation(self):
        real_dumps = json.dumps
        attempts = []

        def unstable(value, *args, **kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("dictionary changed size during iteration")
            return real_dumps(value, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            state_io.json, "dumps", side_effect=unstable
        ), mock.patch.object(state_io.time, "sleep") as sleep:
            path = str(Path(directory) / "state.json")
            self.assertTrue(state_io.atomic_json_write(path, {"cash": 100.0}))
            self.assertEqual(
                json.loads(Path(path).read_text(encoding="utf-8")),
                {"cash": 100.0},
            )
            self.assertEqual(len(attempts), 3)
            self.assertEqual(sleep.call_count, 2)

    def test_atomic_write_does_not_hide_persistent_mutation(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            state_io.json,
            "dumps",
            side_effect=RuntimeError("dictionary keys changed during iteration"),
        ), mock.patch.object(state_io.time, "sleep"):
            path = str(Path(directory) / "state.json")
            with self.assertRaises(RuntimeError):
                state_io.atomic_json_write(path, {"cash": 100.0})
            self.assertFalse(Path(path).exists())

    def test_successful_later_skip_preserves_then_clears_prior_error(self):
        portfolio = {
            "auto_runner": {
                "last_error": "dictionary changed size during iteration",
                "last_error_trace": "trace",
            }
        }
        core = types.SimpleNamespace(
            portfolio=portfolio,
            local_ts_text=lambda: "2026-09-03 00:25:49 CDT",
            save_state=lambda _state: None,
        )
        cycle_id = "auto-skip-cycle"
        completion._ACTIVE[id(core)] = {cycle_id}

        completion._complete(
            core,
            cycle_id=cycle_id,
            source="auto",
            started=1.0,
            status="skipped",
        )

        auto = portfolio["auto_runner"]
        self.assertIsNone(auto["last_error"])
        self.assertIsNone(auto["last_error_trace"])
        self.assertEqual(auto["last_recovered_error"], "dictionary changed size during iteration")
        self.assertEqual(auto["last_recovered_error_trace"], "trace")
        self.assertEqual(auto["last_recovered_error_cycle_id"], cycle_id)
        self.assertEqual(auto["last_completed_cycle_status"], "skipped")

    def test_failed_cycle_never_clears_error(self):
        portfolio = {"auto_runner": {"last_error": "existing"}}
        core = types.SimpleNamespace(
            portfolio=portfolio,
            local_ts_text=lambda: "2026-09-03 00:25:49 CDT",
            save_state=lambda _state: None,
        )
        cycle_id = "auto-failed-cycle"
        completion._ACTIVE[id(core)] = {cycle_id}
        completion._complete(
            core,
            cycle_id=cycle_id,
            source="auto",
            started=1.0,
            status="error",
            error="RuntimeError: still broken",
        )
        self.assertEqual(portfolio["auto_runner"]["last_error"], "existing")
        self.assertEqual(portfolio["auto_runner"]["cycle_error"], "RuntimeError: still broken")


if __name__ == "__main__":
    unittest.main()
