from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import fast_self_check_override as self_check


class SelfCheckRuntimeClassificationTests(unittest.TestCase):
    def test_recent_auto_attempt_proves_runner_liveness(self) -> None:
        row = self_check._runner_liveness(
            {
                "thread_started": False,
                "interval_seconds": 300,
                "last_attempt_ts": 1_000.0,
                "last_attempt_source": "auto",
            },
            now_epoch=1_100.0,
        )
        self.assertTrue(row["active"])
        self.assertFalse(row["reported_started"])
        self.assertTrue(row["recent_auto_attempt"])
        self.assertEqual(row["state"], "inferred_from_recent_auto_attempt")

    def test_stale_attempt_does_not_prove_liveness(self) -> None:
        row = self_check._runner_liveness(
            {
                "thread_started": False,
                "interval_seconds": 300,
                "last_attempt_ts": 1_000.0,
                "last_attempt_source": "auto",
            },
            now_epoch=2_000.0,
        )
        self.assertFalse(row["active"])
        self.assertEqual(row["state"], "not_observed")

    def test_isolated_not_run_research_is_deferred_not_failed(self) -> None:
        components, deferred = self_check._normalize_advisory_components(
            {
                "performance_evidence": {
                    "name": "performance_evidence",
                    "overall": "warn",
                    "backtest_status": "not_run",
                }
            },
            research_isolated=True,
        )
        row = components["performance_evidence"]
        self.assertEqual(row["overall"], "pass")
        self.assertEqual(row["evidence_state"], "deferred_to_research_worker")
        self.assertFalse(row["runtime_blocking"])
        self.assertEqual(deferred, ["performance_evidence"])

    def test_research_error_remains_warning(self) -> None:
        components, deferred = self_check._normalize_advisory_components(
            {
                "performance_evidence": {
                    "name": "performance_evidence",
                    "overall": "warn",
                    "backtest_status": "error",
                    "error": "provider unavailable",
                }
            },
            research_isolated=True,
        )
        self.assertEqual(components["performance_evidence"]["overall"], "warn")
        self.assertEqual(deferred, [])

    def test_build_payload_passes_with_observed_runner_and_deferred_research(self) -> None:
        now = time.time()
        core = SimpleNamespace(
            portfolio={
                "cash": 10_000.0,
                "equity": 10_000.0,
                "positions": {},
                "trades": [],
                "performance": {},
                "risk_controls": {
                    "halted": False,
                    "self_defense_active": False,
                },
                "feedback_loop": {},
                "scanner_audit": {},
                "decision_audit": {},
                "auto_runner": {
                    "enabled": True,
                    "thread_started": False,
                    "interval_seconds": 300,
                    "last_attempt_ts": now - 60,
                    "last_attempt_source": "auto",
                    "last_error": None,
                },
            },
            local_ts_text=lambda: "2026-08-04 08:00:00 CDT",
            scan_signals=lambda *args, **kwargs: None,
            try_entries_and_rotations=lambda *args, **kwargs: None,
        )
        components = {
            "performance_evidence": {
                "name": "performance_evidence",
                "overall": "warn",
                "backtest_status": "not_run",
            },
            "scanner_stack": {
                "name": "scanner_stack",
                "overall": "pass",
            },
        }
        with patch.object(self_check, "_component_checks", return_value=components), patch.object(
            self_check,
            "_heavy_research_isolated",
            return_value=True,
        ):
            payload = self_check.build_payload(core)

        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(payload["summary"]["base_failures"], [])
        self.assertEqual(payload["summary"]["failing_components"], [])
        self.assertEqual(payload["summary"]["deferred_components"], ["performance_evidence"])
        self.assertTrue(payload["auto_runner"]["thread_active_observed"])
        self.assertEqual(
            payload["auto_runner"]["thread_liveness_state"],
            "inferred_from_recent_auto_attempt",
        )


if __name__ == "__main__":
    unittest.main()
