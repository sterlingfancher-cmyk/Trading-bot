import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import performance_audit_lab_v2 as lab
import performance_audit_v2_async_route as resumable
import performance_audit_v2_offline as offline


class PerformanceAuditV2IsolationTests(unittest.TestCase):
    def test_repository_request_is_bounded_and_push_trigger_is_narrow(self):
        request = json.loads(
            Path(".github/performance-audit-v2-request.json").read_text()
        )
        workflow = Path(
            ".github/workflows/performance-audit-v2-research.yml"
        ).read_text()
        self.assertEqual(request["period"], "5y")
        self.assertEqual(request["max_symbols"], 45)
        self.assertTrue(request["include_ablation"])
        self.assertIn('branches: [main]', workflow)
        self.assertIn('".github/performance-audit-v2-request.json"', workflow)
        self.assertNotIn("schedule:", workflow)

    def test_offline_execution_persists_result_without_runtime_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            output = Path(directory) / "result.json"
            result = {"status": "ok", "profiles": {}, "ablation": {}}

            def complete(core, **kwargs):
                section = lab._section(core)
                section["latest"] = result
                section["status"] = "ok"
                core.save_state(core.portfolio)

            with mock.patch.object(resumable, "_background_run", side_effect=complete):
                artifact = offline.execute(
                    period="5y",
                    max_symbols=45,
                    include_ablation=True,
                    checkpoint=checkpoint,
                    output=output,
                )

            self.assertEqual(artifact["status"], "ok")
            self.assertTrue(artifact["execution_boundary"]["isolated_process"])
            self.assertFalse(artifact["execution_boundary"]["production_web_worker"])
            self.assertFalse(artifact["execution_boundary"]["broker_access"])
            self.assertFalse(artifact["execution_boundary"]["order_authority"])
            self.assertEqual(json.loads(output.read_text())["result"], result)
            self.assertTrue(checkpoint.exists())

    def test_matching_checkpoint_is_marked_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            output = Path(directory) / "result.json"
            core = offline.OfflineResearchCore(checkpoint)
            section = lab._section(core)
            section["resilient_core_checkpoint"] = {
                "period": "5y",
                "max_symbols": 45,
                "result": {"status": "ok", "version": lab.VERSION, "profiles": {}},
            }
            core.save_state(core.portfolio)

            def complete(reloaded, **kwargs):
                request = lab._section(reloaded)["queued_request"]
                self.assertTrue(request["resume"])
                state = lab._section(reloaded)
                state["latest"] = {"status": "ok"}
                state["status"] = "ok"

            with mock.patch.object(resumable, "_background_run", side_effect=complete):
                artifact = offline.execute(
                    period="5y",
                    max_symbols=45,
                    include_ablation=True,
                    checkpoint=checkpoint,
                    output=output,
                )
            self.assertTrue(artifact["request"]["resumed"])

    def test_prior_engine_checkpoint_is_not_resumed(self):
        section = {
            "resilient_core_checkpoint": {
                "period": "5y",
                "max_symbols": 45,
                "result": {"status": "ok", "version": "obsolete-engine"},
            }
        }
        self.assertIsNone(resumable._matching_checkpoint(section, "5y", 45))

    def test_failure_is_durable_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            output = Path(directory) / "result.json"

            def fail(core, **kwargs):
                section = lab._section(core)
                section["status"] = "error"
                section["async_launcher_error"] = "RuntimeError: provider unavailable"
                core.save_state(core.portfolio)

            with mock.patch.object(resumable, "_background_run", side_effect=fail):
                artifact = offline.execute(
                    period="5y",
                    max_symbols=45,
                    include_ablation=True,
                    checkpoint=checkpoint,
                    output=output,
                )
            self.assertEqual(artifact["status"], "error")
            self.assertIn("provider unavailable", artifact["error"])
            self.assertEqual(json.loads(output.read_text())["status"], "error")

    def test_import_disables_automatic_research(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            offline.execute.__globals__["os"].environ.pop(
                "PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED", None
            )
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                resumable, "_background_run"
            ) as background:
                core_result = Path(directory) / "result.json"
                offline.execute(
                    period="5y",
                    max_symbols=45,
                    include_ablation=False,
                    checkpoint=Path(directory) / "checkpoint.json",
                    output=core_result,
                )
                background.assert_called_once()
                self.assertEqual(
                    os.environ["PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED"], "false"
                )


if __name__ == "__main__":
    unittest.main()
