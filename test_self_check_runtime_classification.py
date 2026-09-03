from __future__ import annotations

import ast
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fast_self_check_override as self_check
import runtime_worker_registration as registration

ROOT = Path(__file__).resolve().parent


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

    def test_runtime_registration_starts_existing_app_runner(self) -> None:
        portfolio = {
            "auto_runner": {
                "enabled": True,
                "thread_started": False,
                "interval_seconds": 300,
            }
        }
        core = SimpleNamespace(
            portfolio=portfolio,
            AUTO_THREAD_STARTED=False,
        )
        calls: list[str] = []

        def ensure_auto_thread() -> None:
            calls.append("ensure_auto_thread")
            core.AUTO_THREAD_STARTED = True
            portfolio["auto_runner"]["thread_started"] = True

        core.ensure_auto_thread = ensure_auto_thread
        result = registration._start_auto_runner(core)

        self.assertEqual(calls, ["ensure_auto_thread"])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["started"])
        self.assertTrue(result["reported_thread_started"])
        self.assertTrue(result["global_thread_started"])
        self.assertFalse(result["diagnostic_state_synchronized"])
        self.assertEqual(result["owner"], "app.ensure_auto_thread")
        self.assertEqual(result["ordering"], "after_runtime_composition")

    def test_runtime_registration_synchronizes_stale_reported_flag(self) -> None:
        portfolio = {
            "auto_runner": {
                "enabled": True,
                "thread_started": False,
                "interval_seconds": 300,
            }
        }
        calls: list[str] = []
        core = SimpleNamespace(
            portfolio=portfolio,
            AUTO_THREAD_STARTED=True,
        )

        def ensure_auto_thread() -> None:
            calls.append("ensure_auto_thread")
            return None

        core.ensure_auto_thread = ensure_auto_thread
        result = registration._start_auto_runner(core)

        self.assertEqual(calls, ["ensure_auto_thread"])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["started"])
        self.assertFalse(result["reported_before_sync"])
        self.assertTrue(result["reported_thread_started"])
        self.assertTrue(result["global_thread_started"])
        self.assertTrue(result["diagnostic_state_synchronized"])
        self.assertTrue(portfolio["auto_runner"]["thread_started"])
        self.assertEqual(
            portfolio["auto_runner"]["thread_start_owner"],
            "runtime_worker_registration",
        )

    def test_runtime_registration_fails_when_runner_owner_missing(self) -> None:
        result = registration._start_auto_runner(
            SimpleNamespace(
                portfolio={
                    "auto_runner": {
                        "enabled": True,
                        "thread_started": False,
                        "interval_seconds": 300,
                    }
                }
            )
        )
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["started"])
        self.assertEqual(result["reason"], "ensure_auto_thread_missing")

    def test_controlled_redeployment_is_one_shot_not_watchdog_reapplied(self) -> None:
        path = ROOT / "usercustomize.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        registry: set[str] = set()
        watchdog: ast.FunctionDef | None = None

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "ONE_SHOT_CORE_MUTATION_MODULES":
                        value = ast.literal_eval(node.value)
                        registry = {str(item) for item in value}
            elif isinstance(node, ast.FunctionDef) and node.name == "_watchdog":
                watchdog = node

        self.assertIn("controlled_redeployment_starter_sleeve", registry)
        self.assertIsNotNone(watchdog)
        repeated_names = {
            str(node.value)
            for node in ast.walk(watchdog)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertNotIn("controlled_redeployment_starter_sleeve", repeated_names)

    def test_final_cycle_observer_precedes_auto_runner(self) -> None:
        source = (ROOT / "runtime_worker_registration.py").read_text(encoding="utf-8")
        observer_call = "run_report_guard_apply = run_report_guard.apply(core)"
        self.assertEqual(source.count(observer_call), 1)
        diagnostics_index = source.index("diagnostics.register_routes(core.app, core)")
        observer_index = source.index(observer_call)
        reviewer_index = source.index(
            "shadow_ai_reviewer = shadow_ai_adversarial_reviewer.install()",
            observer_index,
        )
        observability_index = source.index(
            "shadow_ai_observability_result = shadow_ai_observability.install(core.app)",
            observer_index,
        )
        runner_index = source.index("auto_runner = _start_auto_runner(core)", observer_index)
        self.assertLess(diagnostics_index, observer_index)
        self.assertLess(observer_index, observability_index)
        self.assertLess(observability_index, reviewer_index)
        self.assertLess(reviewer_index, runner_index)


if __name__ == "__main__":
    unittest.main()
