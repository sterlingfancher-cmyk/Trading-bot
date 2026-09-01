from __future__ import annotations

import types
import unittest

from flask import Flask

import readonly_core_status_override as override


class Issue146ReadonlyCoreStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)

        @self.app.route("/", endpoint="home")
        def legacy_home():
            raise AssertionError("legacy root handler must be replaced")

        @self.app.route("/paper/status", endpoint="paper_status")
        def legacy_status():
            raise AssertionError("legacy status handler must be replaced")

        self.forbidden_calls: list[str] = []

        def forbidden(name):
            def inner(*args, **kwargs):
                self.forbidden_calls.append(name)
                raise AssertionError(f"read-only status invoked forbidden helper: {name}")
            return inner

        self.core = types.SimpleNamespace(
            app=self.app,
            portfolio={
                "cash": 11835.97,
                "equity": 13548.40,
                "peak": 13549.83,
                "positions": {
                    "BBAI": {
                        "side": "short",
                        "entry": 4.9,
                        "shares": 100.0,
                        "last_price": 4.8,
                    },
                    "DELL": {
                        "side": "short",
                        "entry": 120.0,
                        "shares": 5.0,
                        "last_price": 119.0,
                    },
                },
                "performance": {
                    "realized_pnl_today": 0.0,
                    "unrealized_pnl": 10.0,
                },
                "realized_pnl": {"date": "2026-09-01", "today": 0.0},
                "risk_controls": {
                    "date": "2026-09-01",
                    "day_start_equity": 13533.9964,
                    "day_peak_equity": 13549.8288,
                    "halted": False,
                    "halt_reason": None,
                    "intraday_drawdown_pct": 0.011,
                },
                "feedback_loop": {
                    "self_defense_mode": True,
                    "block_new_entries": True,
                    "hard_halt": False,
                    "reasons": ["inside final 30 minutes before close"],
                },
                "last_market": {
                    "market_mode": "neutral",
                    "regime": "neutral",
                    "risk_score": 50,
                },
                "scanner_audit": {"signals_found": 2},
                "auto_runner": {
                    "enabled": True,
                    "thread_started": True,
                    "last_successful_run_local": "2026-09-01 14:24:51 CDT",
                    "last_error": None,
                    "last_result": {
                        "market_mode": "neutral",
                        "entries": [],
                        "exits": [],
                    },
                },
                "trades": [{"symbol": "NVDA", "action": "exit_short"}],
                "history": [13533.99, 13548.40],
                "reports": {"date": "2026-09-01"},
            },
            save_state=forbidden("save_state"),
            calculate_equity=forbidden("calculate_equity"),
            performance_snapshot=forbidden("performance_snapshot"),
            market_status=forbidden("market_status"),
            scanner_result_log=forbidden("scanner_result_log"),
            state_file_diagnostic=forbidden("state_file_diagnostic"),
            entry_controls_snapshot=forbidden("entry_controls_snapshot"),
        )

    def test_status_is_in_memory_read_only_and_fast_path(self) -> None:
        result = override.install(self.core)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result["replaced_endpoints"]), {"home", "paper_status"})

        response = self.app.test_client().get("/paper/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["runtime_status"], "running")
        self.assertEqual(payload["position_symbols"], ["BBAI", "DELL"])
        self.assertTrue(payload["authority"]["read_only"])
        self.assertFalse(payload["authority"]["persists_state"])
        self.assertFalse(payload["authority"]["places_orders"])
        self.assertEqual(self.forbidden_calls, [])

    def test_root_is_lightweight_and_uses_same_in_memory_snapshot(self) -> None:
        override.install(self.core)
        response = self.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Trading Bot", text)
        self.assertIn("BBAI, DELL", text)
        self.assertIn(override.VERSION, text)
        self.assertEqual(self.forbidden_calls, [])

    def test_full_query_does_not_reenable_expensive_legacy_status(self) -> None:
        override.install(self.core)
        response = self.app.test_client().get("/paper/status?full=1")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["full_requested"])
        self.assertEqual(payload["version"], override.VERSION)
        self.assertEqual(self.forbidden_calls, [])

    def test_reinstall_reasserts_endpoint_ownership(self) -> None:
        override.install(self.core)
        self.app.view_functions["paper_status"] = lambda: "stale"
        result = override.install(self.core)
        self.assertEqual(result["status"], "ok")
        view = self.app.view_functions["paper_status"]
        self.assertEqual(
            getattr(view, "_readonly_core_status_override_version", None),
            override.VERSION,
        )
        response = self.app.test_client().get("/paper/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["version"], override.VERSION)


if __name__ == "__main__":
    unittest.main()
