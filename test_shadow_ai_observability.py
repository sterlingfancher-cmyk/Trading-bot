from __future__ import annotations

import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import shadow_ai_observability as observability
from shadow_ai_evidence_store import EvidenceStoreConfig, ShadowAIEvidenceStore


def evidence(index: int, *, decision: str = "agree", cost=0.01) -> dict:
    return {
        "cycle_id": f"cycle-{index}",
        "candidate_id": f"TEST{index}:long",
        "input_fingerprint": f"fingerprint-{index}",
        "join_eligible": decision != "unavailable",
        "result": {
            "decision": decision,
            "completed_at": "2026-09-10T15:00:00Z",
            "fallback_used": decision == "unavailable",
            "citations": [{"url": "https://example.com"}],
            "telemetry": {
                "provider": "fake",
                "model": "fake-v1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 2,
                "cached_tokens": 3,
                "source_count": 1,
                "cost_usd_exact": cost,
            },
        },
    }


class ShadowAIObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = ShadowAIEvidenceStore(
            EvidenceStoreConfig(path=str(Path(self.directory.name) / "evidence.json"))
        )
        self.store.load()
        self.store_patch = mock.patch.object(observability, "_STORE", self.store)
        self.store_patch.start()

    def tearDown(self) -> None:
        self.store_patch.stop()
        self.directory.cleanup()

    def reviewer_status(self, enabled=False, alive=False):
        return {
            "enabled": enabled,
            "worker_alive": alive,
            "worker_count": int(alive),
            "authority": {"places_or_cancels_orders": False},
        }

    def test_disabled_empty_state_is_read_only_and_not_started(self):
        with mock.patch.object(observability.reviewer, "status_payload", return_value=self.reviewer_status()):
            payload = observability.build_payload()
        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(payload["forward_evidence"]["state"], "not_started_reviewer_disabled")
        self.assertFalse(payload["forward_evidence"]["eligible"])
        self.assertFalse(payload["authority"]["execution_input"])
        self.assertFalse(payload["authority"]["places_or_cancels_orders"])

    def test_telemetry_aggregates_sources_tokens_fallbacks_and_exact_cost(self):
        self.store.append(evidence(1))
        self.store.append(evidence(2, decision="unavailable"))
        with mock.patch.object(observability.reviewer, "status_payload", return_value=self.reviewer_status(True, True)):
            telemetry = observability.build_payload()["telemetry"]
        self.assertEqual(telemetry["record_count"], 2)
        self.assertEqual(telemetry["citation_count"], 2)
        self.assertEqual(telemetry["provider_source_count"], 2)
        self.assertEqual(telemetry["fallback_count"], 1)
        self.assertEqual(telemetry["prompt_tokens"], 20)
        self.assertEqual(telemetry["total_inference_cost_usd_exact"], 0.02)

    def test_threshold_never_authorizes_promotion(self):
        for index in range(observability.MIN_FORWARD_RESULTS):
            self.store.append(evidence(index))
        with mock.patch.object(observability.reviewer, "status_payload", return_value=self.reviewer_status(True, True)):
            payload = observability.build_payload()
        self.assertTrue(payload["forward_evidence"]["eligible"])
        self.assertFalse(payload["forward_evidence"]["promotion_authorized"])
        self.assertFalse(payload["counterfactual_scorecards"]["automatic_promotion"])

    def test_missing_exact_cost_remains_inconclusive(self):
        for index in range(observability.MIN_FORWARD_RESULTS):
            self.store.append(evidence(index, cost=None))
        with mock.patch.object(observability.reviewer, "status_payload", return_value=self.reviewer_status(True, True)):
            payload = observability.build_payload()
        self.assertFalse(payload["forward_evidence"]["eligible"])
        self.assertEqual(payload["forward_evidence"]["state"], "inconclusive_quality_or_cost_coverage")

    def test_malformed_optional_token_telemetry_does_not_break_status(self):
        row = evidence(1)
        row["result"]["telemetry"]["prompt_tokens"] = "invalid"
        self.store.append(row)
        with mock.patch.object(observability.reviewer, "status_payload", return_value=self.reviewer_status(True, True)):
            telemetry = observability.build_payload()["telemetry"]
        self.assertEqual(telemetry["prompt_tokens"], 0)

    def test_install_registers_read_only_route_and_sink(self):
        class Rules:
            def __init__(self, app):
                self.app = app

            def iter_rules(self):
                return [types.SimpleNamespace(rule=path) for path in self.app.routes]

        class App:
            def __init__(self):
                self.routes = {}
                self.url_map = Rules(self)

            def add_url_rule(self, path, _endpoint, function):
                self.routes[path] = function

        app = App()
        fake_flask = types.SimpleNamespace(jsonify=lambda value: value)
        with mock.patch.dict("sys.modules", {"flask": fake_flask}), mock.patch.object(
            observability.reviewer, "configure_evidence_sink"
        ) as configure, mock.patch.object(
            observability.reviewer, "status_payload", return_value=self.reviewer_status()
        ):
            result = observability.install(app)
            response = app.routes["/paper/shadow-ai-research-status"]()
        self.assertTrue(result["route_registered"])
        configure.assert_called_once()
        self.assertFalse(response["authority"]["places_or_cancels_orders"])

    def test_durable_usage_windows_segment_day_and_month(self):
        self.store.append(evidence(1, cost=0.01))
        older = evidence(2, cost=0.02)
        older["result"]["completed_at"] = "2026-09-09T15:00:00Z"
        self.store.append(older)
        prior_month = evidence(3, cost=0.03)
        prior_month["result"]["completed_at"] = "2026-08-31T15:00:00Z"
        self.store.append(prior_month)

        usage = observability.inference_usage_windows(
            datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(usage["day_requests"], 1)
        self.assertEqual(usage["month_requests"], 2)
        self.assertTrue(usage["evidence_integrity_valid"])
        self.assertAlmostEqual(usage["day_cost_usd"], 0.01)
        self.assertAlmostEqual(usage["month_cost_usd"], 0.03)


if __name__ == "__main__":
    unittest.main()
