from __future__ import annotations

from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import system_sentinel_runtime as runtime


def _collectors(*, accounting=None, ledger=None, active_error=False):
    return {
        "self_check": lambda core: {
            "account": {"equity": 12_000.0},
            "risk": {"halted": False},
            "auto_runner": {
                "last_error_active": active_error,
                "last_error": "boom" if active_error else None,
                "last_attempt": "now",
            },
        },
        "daily_audit": lambda core: {
            "market_data": {
                "status": "pass",
                "accounting_complete_at_snapshot": True,
                "in_flight_or_unclassified_requests": 0,
            }
        },
        "accounting": lambda core: accounting or {
            "status": "ok", "coverage_complete": True,
            "coverage_issue_count": 0, "economic_issue_count": 0,
        },
        "execution_ledger": lambda core: ledger or {
            "chain_valid": True, "row_count": 3,
        },
        "startup": lambda core: {"status": "ok"},
    }


class SystemSentinelRuntimeTests(unittest.TestCase):
    def setUp(self):
        runtime._REGISTERED_APP_IDS.clear()
        runtime._INSTALL_STATUS_BY_CORE.clear()
        self.core = SimpleNamespace(
            portfolio={
                "equity": 12_000.0,
                "risk_controls": {
                    "day_start_equity": 12_000.0,
                    "day_peak_equity": 12_100.0,
                    "halted": False,
                },
            }
        )

    def test_clean_runtime_is_quiet_and_read_only(self):
        before = repr(self.core.portfolio)
        payload = runtime.build_payload(self.core, collectors=_collectors())
        self.assertEqual(payload["status"], "quiet")
        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(payload["incident_count"], 0)
        self.assertEqual(repr(self.core.portfolio), before)
        self.assertFalse(payload["authority"]["writes_production_state"])
        self.assertFalse(payload["authority"]["starts_worker"])

    def test_runtime_faults_are_classified_with_mandatory_tests(self):
        payload = runtime.build_payload(
            self.core,
            collectors=_collectors(
                accounting={
                    "status": "partial", "coverage_complete": False,
                    "coverage_issue_count": 1, "economic_issue_count": 1,
                },
                ledger={"chain_valid": False, "row_count": 4},
                active_error=True,
            ),
        )
        reasons = {row["reason_code"] for row in payload["incidents"]}
        self.assertEqual(
            reasons,
            {"accounting_integrity_failure", "execution_chain_invalid", "runner_active_error"},
        )
        self.assertEqual(payload["overall"], "warn")
        self.assertTrue(all(row["selected_tests"] for row in payload["incidents"]))

    def test_collection_failure_is_visible_and_cannot_break_route(self):
        collectors = _collectors()

        def broken(core):
            raise RuntimeError("diagnostic unavailable")

        collectors["daily_audit"] = broken
        payload = runtime.build_payload(self.core, collectors=collectors)
        self.assertEqual(payload["overall"], "warn")
        self.assertIn("daily_audit", payload["collection_errors"])

    def test_one_expected_concurrent_provider_request_is_not_false_incident(self):
        collectors = _collectors()
        collectors["daily_audit"] = lambda core: {
            "market_data": {
                "status": "pass",
                "accounting_complete_at_snapshot": True,
                "in_flight_or_unclassified_requests": 1,
            }
        }
        payload = runtime.build_payload(self.core, collectors=collectors)
        self.assertEqual(payload["status"], "quiet")
        self.assertEqual(
            payload["snapshot"]["market_data"]["observed_in_flight_or_unclassified_requests"],
            1,
        )
        self.assertEqual(
            payload["snapshot"]["market_data"]["in_flight_or_unclassified_requests"],
            0,
        )

    def test_route_registration_is_idempotent_and_starts_no_worker(self):
        class FakeApp:
            def __init__(self):
                self._rules = []
                self.url_map = SimpleNamespace(
                    iter_rules=lambda: [SimpleNamespace(rule=row) for row in self._rules]
                )

            def add_url_rule(self, path, endpoint, view):
                self._rules.append(path)

        app = FakeApp()
        fake_flask = SimpleNamespace(jsonify=lambda payload: payload)
        with patch.dict(sys.modules, {"flask": fake_flask}):
            first = runtime.install(app, self.core)
            second = runtime.install(app, self.core)
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertEqual(rules.count("/paper/system-sentinel-status"), 1)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertFalse(first["worker_started"])


if __name__ == "__main__":
    unittest.main()
