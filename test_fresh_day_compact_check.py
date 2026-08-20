from __future__ import annotations

import fresh_risk_day_baseline_guard as guard


class FakeCore:
    def __init__(self):
        self.get_calls = 0
        self.portfolio = {
            "equity": 13240.0,
            "risk_controls": {
                "date": "2026-08-20",
                "day_start_equity": 13240.0,
                "day_peak_equity": 13255.0,
                "halted": False,
                "halt_reason": "",
                "intraday_drawdown_pct": 0.113,
                "fresh_day_reset_pending": False,
            },
        }

    def today_key(self):
        return "2026-08-20"

    def get_risk_controls(self):
        self.get_calls += 1
        raise AssertionError("compact endpoint must not invoke mutable reset boundary")


def test_compact_payload_contains_only_fresh_day_operator_fields_and_is_observational():
    core = FakeCore()
    payload = guard.fresh_day_check_payload(core)

    assert payload == {
        "baseline_status": "pass",
        "date": "2026-08-20",
        "day_start_equity": 13240.0,
        "day_peak_equity": 13255.0,
        "halted": False,
        "halt_reason": "",
        "intraday_drawdown_pct": 0.113,
        "fresh_day_reset_pending": False,
    }
    assert core.get_calls == 0


def test_compact_payload_reports_contaminated_current_day_as_fail_without_repairing_it():
    core = FakeCore()
    core.portfolio["risk_controls"].update(
        {
            "day_start_equity": -26064.31,
            "day_peak_equity": 0.01,
            "halted": True,
            "halt_reason": "daily loss limit hit (3.0%)",
            "intraday_drawdown_pct": 0.0,
        }
    )

    payload = guard.fresh_day_check_payload(core)

    assert payload["baseline_status"] == "fail"
    assert payload["day_start_equity"] == -26064.31
    assert payload["day_peak_equity"] == 0.01
    assert payload["halted"] is True
    assert core.portfolio["risk_controls"]["day_start_equity"] == -26064.31
    assert core.portfolio["risk_controls"]["day_peak_equity"] == 0.01


def test_compact_payload_reports_pending_when_risk_date_has_not_rolled_forward():
    core = FakeCore()
    core.portfolio["risk_controls"]["date"] = "2026-08-19"
    core.portfolio["risk_controls"]["fresh_day_reset_pending"] = True

    payload = guard.fresh_day_check_payload(core)

    assert payload["baseline_status"] == "pending"
    assert payload["date"] == "2026-08-19"
    assert payload["fresh_day_reset_pending"] is True
