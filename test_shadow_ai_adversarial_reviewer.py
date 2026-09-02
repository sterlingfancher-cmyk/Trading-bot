from __future__ import annotations

import threading
import time
import unittest
from datetime import datetime, timezone

from shadow_ai_adversarial_reviewer import (
    ShadowAIAdversarialReviewer,
    ShadowAIReviewerConfig,
)
from shadow_ai_research_client import (
    SCHEMA_VERSION,
    ShadowAIClientConfig,
    ShadowAIResearchClient,
)


NOW = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)


def report(candidate_count=1):
    return {
        "cycle_id": "cycle-1",
        "input_fingerprint": "cycle-fingerprint",
        "market_mode": "neutral",
        "candidate_sample": [
            {
                "symbol": f"TEST{index}",
                "side": "long",
                "signal_score": 0.5,
                "price": 100.0,
                "sector": "TECH",
                "strategy_bucket": "momentum",
                "confirmations": ["volume"],
                "allowed": True,
                "selected": index == 0,
                "terminal_reason": "",
                "final_score": 0.5,
                "final_size_multiplier": 0.25,
            }
            for index in range(candidate_count)
        ],
    }


def provider_response(payload):
    request = payload["request"]
    return {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": request["cycle_id"],
        "candidate_id": request["candidate_id"],
        "input_fingerprint": request["input_fingerprint"],
        "decision": "agree",
        "confidence": 0.8,
        "risk_factors": ["none_material"],
        "citations": [],
        "telemetry": {},
    }


class ShadowAIAdversarialReviewerTests(unittest.TestCase):
    def enabled_reviewer(self, provider, **config_overrides):
        client = ShadowAIResearchClient(
            ShadowAIClientConfig(enabled=True, provider="fake", model="fake-v1"),
            now=lambda: NOW,
        )
        return ShadowAIAdversarialReviewer(
            client=client,
            provider=provider,
            config=ShadowAIReviewerConfig(enabled=True, **config_overrides),
            now=lambda: NOW,
        )

    def wait_completed(self, reviewer, count=1):
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if reviewer.status_payload()["counters"]["requests_completed"] >= count:
                return
            time.sleep(0.01)
        self.fail("reviewer did not complete in time")

    def test_disabled_registration_starts_no_thread_and_observation_is_noop(self):
        reviewer = ShadowAIAdversarialReviewer(
            client=ShadowAIResearchClient(),
            provider=None,
        )
        start = reviewer.start()
        observed = reviewer.enqueue_report(report())
        status = reviewer.status_payload()

        self.assertFalse(start["started"])
        self.assertEqual(start["reason"], "research_disabled")
        self.assertEqual(observed["status"], "disabled")
        self.assertFalse(status["worker_started"])
        self.assertEqual(status["worker_count"], 0)
        self.assertFalse(status["authority"]["blocks_or_delays_execution"])

    def test_worker_is_explicit_single_and_provider_runs_off_observer_thread(self):
        observer_thread = threading.get_ident()
        provider_threads = []

        def provider(payload, _timeout):
            provider_threads.append(threading.get_ident())
            return provider_response(payload)

        reviewer = self.enabled_reviewer(provider)
        try:
            self.assertTrue(reviewer.start()["started"])
            observed = reviewer.enqueue_report(report())
            self.assertEqual(observed["enqueued"], 1)
            self.assertFalse(observed["execution_waited"])
            self.wait_completed(reviewer)

            status = reviewer.status_payload()
            self.assertEqual(status["worker_count"], 1)
            self.assertEqual(status["counters"]["results_join_eligible"], 1)
            self.assertNotEqual(provider_threads, [observer_thread])
            self.assertEqual(
                reviewer.results_snapshot()[0]["result"]["decision"],
                "agree",
            )
        finally:
            reviewer.stop()

    def test_request_snapshot_is_immutable_after_enqueue(self):
        gate = threading.Event()

        def provider(payload, _timeout):
            gate.wait(1.0)
            self.assertEqual(payload["request"]["features"]["final_score"], 0.5)
            return provider_response(payload)

        reviewer = self.enabled_reviewer(provider)
        cycle = report()
        try:
            reviewer.start()
            reviewer.enqueue_report(cycle)
            cycle["candidate_sample"][0]["final_score"] = 999
            gate.set()
            self.wait_completed(reviewer)
            self.assertEqual(
                reviewer.results_snapshot()[0]["result"]["decision"],
                "agree",
            )
        finally:
            gate.set()
            reviewer.stop()

    def test_requests_per_cycle_are_bounded(self):
        reviewer = self.enabled_reviewer(
            lambda payload, _timeout: provider_response(payload),
            max_requests_per_cycle=3,
        )
        try:
            reviewer.start()
            observed = reviewer.enqueue_report(report(candidate_count=8))
            self.assertEqual(observed["enqueued"], 3)
            self.wait_completed(reviewer, 3)
            self.assertEqual(
                reviewer.status_payload()["counters"]["candidates_observed"],
                3,
            )
        finally:
            reviewer.stop()

    def test_unavailable_result_is_telemetry_only(self):
        def provider(payload, _timeout):
            value = provider_response(payload)
            value["decision"] = "unavailable"
            value["confidence"] = 0.0
            return value

        reviewer = self.enabled_reviewer(provider)
        try:
            reviewer.start()
            reviewer.enqueue_report(report())
            self.wait_completed(reviewer)
            result = reviewer.results_snapshot()[0]
            self.assertFalse(result["join_eligible"])
            self.assertEqual(result["invalid_reason"], "result_unavailable")
            self.assertFalse(result["authority"]["execution_input"])
        finally:
            reviewer.stop()

    def test_queue_full_drops_new_request_without_waiting(self):
        gate = threading.Event()

        def provider(payload, _timeout):
            gate.wait(1.0)
            return provider_response(payload)

        reviewer = self.enabled_reviewer(provider, max_items=1)
        try:
            reviewer.start()
            reviewer.enqueue_report(report())
            deadline = time.monotonic() + 1.0
            while reviewer.status_payload()["queue_size"] and time.monotonic() < deadline:
                time.sleep(0.01)
            reviewer.enqueue_report(report())
            started = time.monotonic()
            dropped = reviewer.enqueue_report(report())
            elapsed = time.monotonic() - started
            self.assertEqual(dropped["dropped"], 1)
            self.assertLess(elapsed, 0.05)
            self.assertEqual(dropped["reason"], "queue_full_drop_new_request")
        finally:
            gate.set()
            reviewer.stop()

    def test_configuration_bounds(self):
        with self.assertRaises(ValueError):
            ShadowAIReviewerConfig(max_items=129)
        with self.assertRaises(ValueError):
            ShadowAIReviewerConfig(max_requests_per_cycle=11)
        with self.assertRaises(ValueError):
            ShadowAIReviewerConfig(result_history_limit=501)


if __name__ == "__main__":
    unittest.main()
