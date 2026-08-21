from __future__ import annotations

import copy
import unittest
from unittest import mock

import day_peak_provenance_status as probe


class _Core:
    def __init__(self, portfolio):
        self.portfolio = portfolio

    def local_ts_text(self, ts=None):
        if ts is None:
            return "2026-08-21 13:40:00 CDT"
        mapping = {
            1000.0: "2026-08-21 13:05:00 CDT",
            1010.0: "2026-08-21 13:10:00 CDT",
        }
        return mapping.get(float(ts), "2026-08-21 13:15:00 CDT")


def _report(time_text, equity, peak, positions, date="2026-08-21"):
    return {
        "type": "intraday",
        "date": date,
        "generated_local": time_text,
        "headline": {
            "equity": equity,
            "cash": 100.0,
            "day_pnl_pct": 2.0,
            "intraday_drawdown_pct": 0.0,
            "open_positions": positions,
        },
        "risk_controls": {
            "date": date,
            "day_start_equity": 100.0,
            "day_peak_equity": peak,
            "intraday_drawdown_pct": max(0.0, (peak - equity) / peak * 100.0),
            "halted": peak >= 150.0,
            "halt_reason": "performance risk hard intraday drawdown halt (2.50%)" if peak >= 150.0 else "",
        },
    }


def _portfolio(transient=True):
    second_equity = 103.0 if transient else 150.0
    return {
        "cash": 100.0,
        "equity": 103.0,
        "history": [100.0, 102.0, 150.0, 103.0],
        "positions": {
            "ABC": {
                "side": "long",
                "shares": 1.0,
                "entry": 100.0,
                "last_price": 103.0,
                "peak": 150.0,
                "entry_time": 1000.0,
            }
        },
        "risk_controls": {
            "date": "2026-08-21",
            "day_start_equity": 100.0,
            "day_peak_equity": 150.0,
            "intraday_drawdown_pct": 31.333,
            "halted": True,
            "halt_reason": "performance risk hard intraday drawdown halt (2.50%)",
        },
        "reports": {
            "date": "2026-08-21",
            "intraday_history": [
                _report("2026-08-21 13:05:00 CDT", 102.0, 102.0, ["OLD"]),
                _report("2026-08-21 13:10:00 CDT", second_equity, 150.0, ["ABC"]),
                _report(
                    "2026-08-20 13:10:00 CDT",
                    999.0,
                    999.0,
                    ["STALE"],
                    date="2026-08-20",
                ),
            ],
        },
        "trades": [
            {
                "time": 1000.0,
                "symbol": "ABC",
                "action": "entry",
                "side": "long",
                "price": 100.0,
                "shares": 1.0,
                "execution_id": "entry-1",
            },
            {
                "time": 1010.0,
                "symbol": "OLD",
                "action": "exit",
                "side": "long",
                "price": 99.0,
                "shares": 1.0,
                "execution_id": "exit-1",
            },
        ],
    }


class DayPeakProvenanceStatusTests(unittest.TestCase):
    def test_transient_peak_between_report_headlines_is_detected(self):
        core = _Core(_portfolio(transient=True))
        payload = probe.status_payload(core)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(
            payload["diagnosis"],
            "transient_equity_peak_observed_between_compiled_report_headlines",
        )
        self.assertTrue(payload["equity_history"]["current_peak_observed"])
        self.assertEqual(payload["equity_history"]["maximum_equity"], 150.0)
        self.assertFalse(payload["intraday_reports"]["current_peak_observed_in_headline"])
        self.assertEqual(payload["intraday_reports"]["maximum_headline_equity"], 103.0)
        self.assertEqual(
            payload["intraday_reports"]["first_report_carrying_current_risk_peak"]["generated_local"],
            "2026-08-21 13:10:00 CDT",
        )
        self.assertEqual(
            payload["intraday_reports"]["report_before_current_risk_peak_first_seen"]["generated_local"],
            "2026-08-21 13:05:00 CDT",
        )
        self.assertEqual(
            payload["intraday_reports"]["candidate_symbols_at_peak_boundary"],
            ["ABC", "OLD"],
        )
        self.assertTrue(payload["evidence_interpretation"]["transient_between_reports"])

    def test_sustained_peak_in_report_headline_is_distinguished(self):
        core = _Core(_portfolio(transient=False))
        payload = probe.status_payload(core)

        self.assertEqual(
            payload["diagnosis"],
            "current_day_peak_observed_in_equity_history_and_report_headline",
        )
        self.assertTrue(payload["intraday_reports"]["current_peak_observed_in_headline"])
        self.assertEqual(payload["intraday_reports"]["maximum_headline_equity"], 150.0)

    def test_probe_is_read_only_and_filters_trades_to_current_risk_date(self):
        portfolio = _portfolio(transient=True)
        before = copy.deepcopy(portfolio)
        core = _Core(portfolio)

        with mock.patch("builtins.open", side_effect=AssertionError("file I/O forbidden")):
            payload = probe.status_payload(core)

        self.assertEqual(portfolio, before)
        self.assertEqual(len(payload["current_day_trades"]), 2)
        self.assertTrue(payload["authority"]["reporting_only"])
        self.assertFalse(payload["authority"]["writes_files"])
        self.assertFalse(payload["authority"]["calls_market_data_providers"])
        self.assertFalse(payload["authority"]["updates_risk_controls"])
        self.assertFalse(payload["authority"]["rewrites_current_day_peak"])
        self.assertFalse(payload["authority"]["clears_hard_halt"])

    def test_startup_apply_does_not_scan_runtime_state(self):
        core = _Core(_portfolio(transient=True))
        with mock.patch.object(probe, "status_payload", side_effect=AssertionError("must not run")):
            payload = probe.apply(core)
        self.assertEqual(payload["overall"], "pass")
        self.assertFalse(payload["startup_reads_runtime_state"])
        self.assertFalse(payload["startup_calls_market_data_providers"])

    def test_route_registration_is_bounded(self):
        try:
            from flask import Flask
        except Exception:  # pragma: no cover - dependency is installed in CI
            self.skipTest("Flask not installed")

        app = Flask(__name__)
        core = _Core(_portfolio(transient=True))
        result = probe.register_routes(app, core)
        self.assertEqual(result["overall"], "pass")
        self.assertIn(probe.ROUTE, {rule.rule for rule in app.url_map.iter_rules()})
        client = app.test_client()
        response = client.get(probe.ROUTE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["type"], "day_peak_provenance_status")


if __name__ == "__main__":
    unittest.main()
