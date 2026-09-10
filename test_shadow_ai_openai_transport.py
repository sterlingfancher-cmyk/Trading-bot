from __future__ import annotations

import json
import unittest
import urllib.error
from datetime import datetime, timezone

from shadow_ai_openai_transport import (
    ENDPOINT,
    MODEL,
    OpenAIShadowConfig,
    OpenAIShadowTransport,
    build_runtime_components,
    config_from_environment,
)
from shadow_ai_research_client import SCHEMA_VERSION, ShadowAITransientError


NOW = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.payload[:limit]


def provider_payload():
    return {
        "system_policy": {"research_only": True},
        "request": {
            "schema_version": SCHEMA_VERSION,
            "cycle_id": "cycle-1",
            "candidate_id": "ABC:long:123",
            "input_fingerprint": "fingerprint",
        },
        "response_contract": {"required": []},
    }


def response_payload():
    result = {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": "cycle-1",
        "candidate_id": "ABC:long:123",
        "input_fingerprint": "fingerprint",
        "decision": "agree",
        "confidence": 0.7,
        "risk_factors": ["thin_volume"],
        "citations": [],
        "advisory_summary": "Rules decision is plausible but liquidity is thin.",
    }
    return {
        "output": [{"content": [{"type": "output_text", "text": json.dumps(result)}]}],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 40,
            "input_tokens_details": {"cached_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 15},
        },
    }


class OpenAIShadowTransportTests(unittest.TestCase):
    def test_key_alone_does_not_enable_runtime(self):
        client, provider, reviewer = build_runtime_components(
            environment={"SHADOW_AI_OPENAI_API_KEY": "secret"}
        )
        self.assertFalse(client.config.enabled)
        self.assertFalse(reviewer.enabled)
        status = provider.status_payload()
        self.assertTrue(status["key_configured"])
        self.assertFalse(status["ready"])
        self.assertNotIn("secret", json.dumps(status))

    def test_enabled_transport_uses_strict_responses_request_without_tools(self):
        captured = {}

        def urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(response_payload())

        config = OpenAIShadowConfig(enabled=True, api_key="top-secret")
        transport = OpenAIShadowTransport(config, urlopen=urlopen, now=lambda: NOW)
        result = transport(provider_payload(), 30)

        self.assertEqual(captured["url"], ENDPOINT)
        self.assertEqual(captured["body"]["model"], MODEL)
        self.assertFalse(captured["body"]["store"])
        self.assertNotIn("tools", captured["body"])
        self.assertEqual(captured["body"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(captured["timeout"], 20.0)
        self.assertEqual(result["telemetry"]["prompt_tokens"], 90)
        self.assertEqual(result["telemetry"]["cached_tokens"], 10)
        self.assertEqual(result["telemetry"]["completion_tokens"], 25)
        self.assertEqual(result["telemetry"]["reasoning_tokens"], 15)
        self.assertNotIn("top-secret", json.dumps(transport.status_payload()))

    def test_durable_usage_supplier_enforces_all_budgets_before_network(self):
        calls = []

        def urlopen(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeResponse(response_payload())

        cases = (
            ({"day_requests": 25}, "daily_request_limit_reached"),
            ({"day_cost_usd": 0.50}, "daily_cost_limit_reached"),
            ({"month_cost_usd": 10.0}, "monthly_cost_limit_reached"),
        )
        for usage, reason in cases:
            transport = OpenAIShadowTransport(
                OpenAIShadowConfig(enabled=True, api_key="secret"),
                usage_supplier=lambda _now, usage=usage: usage,
                urlopen=urlopen,
                now=lambda: NOW,
            )
            with self.assertRaisesRegex(RuntimeError, reason):
                transport(provider_payload(), 20)
        self.assertEqual(calls, [])

    def test_transient_http_errors_are_retryable_and_safe(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate", {}, None)

        transport = OpenAIShadowTransport(
            OpenAIShadowConfig(enabled=True, api_key="secret"),
            urlopen=urlopen,
            now=lambda: NOW,
        )
        with self.assertRaises(ShadowAITransientError):
            transport(provider_payload(), 20)
        self.assertEqual(transport.status_payload()["last_error"], "http_429")

    def test_paid_malformed_model_output_is_unavailable_with_usage(self):
        payload = response_payload()
        payload["output"][0]["content"][0]["text"] = "not-json"
        transport = OpenAIShadowTransport(
            OpenAIShadowConfig(enabled=True, api_key="secret"),
            urlopen=lambda *_args, **_kwargs: FakeResponse(payload),
            now=lambda: NOW,
        )
        result = transport(provider_payload(), 20)
        self.assertEqual(result["decision"], "unavailable")
        self.assertEqual(result["risk_factors"], ["provider_malformed_output"])
        self.assertEqual(result["telemetry"]["prompt_tokens"], 90)

    def test_invalid_budget_evidence_fails_closed_before_network(self):
        transport = OpenAIShadowTransport(
            OpenAIShadowConfig(enabled=True, api_key="secret"),
            usage_supplier=lambda _now: {"evidence_integrity_valid": False},
            urlopen=lambda *_args, **_kwargs: self.fail("network must not be called"),
            now=lambda: NOW,
        )
        with self.assertRaisesRegex(RuntimeError, "budget_evidence_invalid"):
            transport(provider_payload(), 20)

    def test_configuration_is_fail_closed_and_bounded(self):
        config = config_from_environment(
            {
                "SHADOW_AI_ENABLED": "true",
                "SHADOW_AI_OPENAI_API_KEY": "secret",
                "SHADOW_AI_MAX_REQUESTS_PER_DAY": "9999",
                "SHADOW_AI_MAX_REQUESTS_PER_CYCLE": "9999",
                "SHADOW_AI_TIMEOUT_SECONDS": "9999",
            }
        )
        self.assertTrue(config.ready)
        self.assertEqual(config.max_requests_per_day, 100)
        self.assertEqual(config.max_requests_per_cycle, 2)
        self.assertEqual(config.timeout_seconds, 20.0)
        with self.assertRaises(ValueError):
            config_from_environment(
                {
                    "SHADOW_AI_ENABLED": "true",
                    "SHADOW_AI_PROVIDER": "other",
                    "SHADOW_AI_OPENAI_API_KEY": "secret",
                }
            )

        client, provider, reviewer = build_runtime_components(
            environment={
                "SHADOW_AI_ENABLED": "true",
                "SHADOW_AI_PROVIDER": "other",
                "SHADOW_AI_OPENAI_API_KEY": "secret",
            }
        )
        self.assertFalse(client.config.enabled)
        self.assertFalse(reviewer.enabled)
        self.assertEqual(
            provider.status_payload()["last_error"],
            "configuration_invalid_fail_closed",
        )


if __name__ == "__main__":
    unittest.main()
