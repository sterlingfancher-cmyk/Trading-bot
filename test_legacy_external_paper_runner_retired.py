from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = Path(".github/workflows/paper-run.yml")


class LegacyExternalPaperRunnerRetiredTests(unittest.TestCase):
    def test_legacy_external_runner_cannot_schedule_or_trigger_a_paper_cycle(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        lowered = text.lower()

        self.assertIn("retired legacy external paper runner", lowered)
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("/paper/run", text)
        self.assertNotIn("trading-bot-clean.up.railway.app", text)
        self.assertNotIn("RUN_KEY", text)
        self.assertNotIn("curl ", lowered)

    def test_retired_workflow_does_not_claim_canonical_cycle_ownership(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8").lower()

        self.assertIn("canonical paper-cycle ownership remains with the splendid service internal runner", text)
        self.assertIn("intentionally performs no http request", text)


if __name__ == "__main__":
    unittest.main()
