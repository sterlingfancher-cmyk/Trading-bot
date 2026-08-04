from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cycle_completion_contract as cycle
import provider_timeout_contract as provider
import runtime_worker_registration as registration
import state_persistence_contract as persistence


class RuntimeRepairContractTests(unittest.TestCase):
    def test_provider_contract_injects_bounded_timeout(self) -> None:
        import yfinance as yf

        calls = []
        original_download = yf.download
        original_installed = provider._INSTALLED
        original_saved = provider._ORIGINAL_DOWNLOAD

        def fake_download(*args, **kwargs):
            calls.append(dict(kwargs))
            return {"ok": True}

        try:
            yf.download = fake_download
            provider._INSTALLED = False
            provider._ORIGINAL_DOWNLOAD = None
            result = provider.apply(None)
            self.assertEqual(result["status"], "ok")
            yf.download("SPY", period="1d", interval="5m")
            self.assertEqual(len(calls), 1)
            self.assertGreaterEqual(calls[0]["timeout"], 1.0)
            self.assertLessEqual(calls[0]["timeout"], provider.MAX_TIMEOUT_SECONDS)
        finally:
            yf.download = original_download
            provider._INSTALLED = original_installed
            provider._ORIGINAL_DOWNLOAD = original_saved

    def test_cycle_contract_records_completed_cycle_and_phase(self) -> None:
        saved = []
        core = SimpleNamespace()
        core.portfolio = {"auto_runner": {}}
        core.local_ts_text = lambda: "2026-08-04 10:00:00 CDT"
        core.save_state = lambda state: saved.append(dict(state.get("auto_runner", {})))
        core.market_status = lambda force=True: {"market_mode": "neutral"}
        core.manage_exits = lambda params, market: []
        core.calculate_equity = lambda refresh_prices=True: 10_000.0
        core.scan_signals = lambda market: ([], [], [])
        core.try_entries_and_rotations = lambda *args, **kwargs: ([], [], [])
        core.performance_snapshot = lambda: {}

        def run_cycle(source="auto", allow_after_hours=False):
            core.market_status(force=True)
            core.scan_signals({})
            return {"signals_found": 0, "market_open_now": True}

        core.run_cycle = run_cycle
        cycle._APPLIED.discard(id(core))
        result = cycle.apply(core)
        self.assertEqual(result["status"], "ok")
        payload = core.run_cycle(source="auto", allow_after_hours=False)
        self.assertEqual(payload["signals_found"], 0)
        auto = core.portfolio["auto_runner"]
        self.assertFalse(auto["cycle_in_progress"])
        self.assertEqual(auto["last_completed_cycle_status"], "completed")
        self.assertEqual(auto["last_completed_cycle_source"], "auto")
        self.assertIsNotNone(auto["last_completed_cycle_duration_seconds"])
        self.assertGreaterEqual(len(saved), 2)

    def test_state_contract_migrates_only_richer_legacy_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_file = root / "state.json"
            legacy_file = root / "legacy.json"
            legacy_file.write_text(
                '{"cash":9878.62,"equity":9999.56,"positions":{"TSM":{"entry":100}},"trades":[{"symbol":"TSM"}],"history":[9999.56]}',
                encoding="utf-8",
            )
            core = SimpleNamespace(
                STATE_FILE=str(state_file),
                STATE_DIR=str(root),
                portfolio={"cash": 10000.0, "equity": 10000.0, "positions": {}, "trades": [], "history": []},
            )
            core.save_state = lambda state: state_file.write_text(__import__("json").dumps(state), encoding="utf-8")
            persistence._APPLIED.discard(id(core))
            persistence._LAST = {}
            with patch.object(persistence, "_is_distinct_mount", return_value=True), patch.object(
                persistence, "_legacy_candidates", return_value=[str(legacy_file)]
            ), patch.dict(os.environ, {"STATE_DIR": str(root)}, clear=False):
                result = persistence.apply(core)
            self.assertTrue(result["persistent_mount_detected"])
            self.assertTrue(result["migration"]["performed"])
            self.assertIn("TSM", core.portfolio["positions"])
            self.assertTrue(state_file.is_file())
            self.assertTrue(Path(str(state_file) + ".bak").is_file())

    def test_deferred_auto_runner_restores_and_starts_post_composition_kickoff(self) -> None:
        called = threading.Event()
        portfolio = {
            "auto_runner": {
                "enabled": False,
                "thread_started": False,
                "interval_seconds": 300,
            }
        }
        core = SimpleNamespace(portfolio=portfolio, AUTO_THREAD_STARTED=False, AUTO_RUN_ENABLED=False)

        def ensure_auto_thread() -> None:
            core.AUTO_THREAD_STARTED = True
            portfolio["auto_runner"]["thread_started"] = True

        def run_cycle(source="auto", allow_after_hours=False):
            called.set()
            return {"status": "ok"}

        core.ensure_auto_thread = ensure_auto_thread
        core.run_cycle = run_cycle
        registration._KICKOFF_STARTED.discard(id(core))
        with patch.dict(
            os.environ,
            {
                "AUTO_RUN_DEFERRED_BOOTSTRAP": "true",
                "AUTO_RUN_REQUESTED": "true",
                "AUTO_RUN_ENABLED": "false",
            },
            clear=False,
        ):
            result = registration._start_auto_runner(core)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["deferred_configuration"]["restored"])
        self.assertTrue(core.AUTO_RUN_ENABLED)
        self.assertTrue(portfolio["auto_runner"]["enabled"])
        self.assertTrue(result["immediate_kickoff"]["started"])
        self.assertTrue(called.wait(2.0))


if __name__ == "__main__":
    unittest.main()
