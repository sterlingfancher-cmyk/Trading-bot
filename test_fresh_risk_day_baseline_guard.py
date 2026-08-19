import importlib

import fresh_risk_day_baseline_guard as guard


class FakeCore:
    def __init__(self):
        self.portfolio = {
            "equity": -26064.31,
            "risk_controls": {
                "date": "2026-08-18",
                "day_start_equity": 13274.84,
                "day_peak_equity": 13274.84,
                "halted": True,
                "halt_reason": "daily loss limit hit (3.0%)",
            },
        }

    def today_key(self):
        return "2026-08-19"

    def default_risk_controls(self):
        return {
            "date": self.today_key(),
            "day_start_equity": 10000.0,
            "day_peak_equity": 10000.0,
            "day_pnl_pct": 0.0,
            "daily_loss_pct": 0.0,
            "daily_drawdown_pct": 0.0,
            "intraday_drawdown_pct": 0.0,
            "halted": False,
            "halt_reason": "",
            "self_defense_active": False,
            "self_defense_reason": "",
            "cooldowns": {},
        }

    def get_risk_controls(self):
        rc = self.portfolio.setdefault("risk_controls", self.default_risk_controls())
        if rc.get("date") != self.today_key():
            current_equity = float(self.portfolio.get("equity", 10000.0))
            rc.clear()
            rc.update(self.default_risk_controls())
            rc["day_start_equity"] = current_equity
            rc["day_peak_equity"] = current_equity
        return rc

    def update_daily_risk_controls(self, equity):
        rc = self.get_risk_controls()
        equity = float(equity)
        start = max(float(rc.get("day_start_equity", equity)), 0.01)
        old_peak = max(float(rc.get("day_peak_equity", equity)), 0.01)
        peak = max(old_peak, equity, 0.01)
        rc["day_peak_equity"] = peak
        rc["day_pnl_pct"] = round(((equity - start) / start) * 100.0, 3)
        rc["daily_loss_pct"] = round(max(0.0, ((start - equity) / start) * 100.0), 3)
        return rc


def _fresh_module():
    return importlib.reload(guard)


def test_invalid_persisted_equity_defers_new_day_reset_without_point_zero_one_baseline():
    module = _fresh_module()
    core = FakeCore()
    result = module.apply(core)
    assert result["overall"] == "pass"

    rc = core.get_risk_controls()
    assert rc["date"] == "2026-08-18"
    assert rc["day_start_equity"] == 13274.84
    assert rc["day_peak_equity"] == 13274.84
    assert rc["fresh_day_reset_pending"] is True
    assert rc["fresh_day_reset_candidate_equity"] == -26064.31


def test_invalid_update_candidate_does_not_manufacture_huge_loss_or_rewrite_baseline():
    module = _fresh_module()
    core = FakeCore()
    module.apply(core)

    rc = core.update_daily_risk_controls(-26064.31)
    assert rc["date"] == "2026-08-18"
    assert rc["day_start_equity"] == 13274.84
    assert rc["day_peak_equity"] == 13274.84
    assert rc.get("day_pnl_pct") is None
    assert rc["fresh_day_reset_pending"] is True


def test_sane_update_candidate_performs_normal_new_day_reset_from_current_equity():
    module = _fresh_module()
    core = FakeCore()
    module.apply(core)

    rc = core.update_daily_risk_controls(13250.25)
    assert rc["date"] == "2026-08-19"
    assert rc["day_start_equity"] == 13250.25
    assert rc["day_peak_equity"] == 13250.25
    assert rc["day_pnl_pct"] == 0.0
    assert rc["daily_loss_pct"] == 0.0
    assert rc["halted"] is False
    assert rc["halt_reason"] == ""
    assert rc["fresh_day_reset_source"] == "update_daily_risk_controls.argument"


def test_sane_portfolio_equity_allows_legacy_reset_path():
    module = _fresh_module()
    core = FakeCore()
    core.portfolio["equity"] = 13190.5
    module.apply(core)

    rc = core.get_risk_controls()
    assert rc["date"] == "2026-08-19"
    assert rc["day_start_equity"] == 13190.5
    assert rc["day_peak_equity"] == 13190.5
    assert rc["halted"] is False
    assert rc["fresh_day_reset_source"] == "normal_get_risk_controls_reset"


def test_already_initialized_current_day_is_never_rewritten():
    module = _fresh_module()
    core = FakeCore()
    core.portfolio["risk_controls"] = {
        "date": "2026-08-19",
        "day_start_equity": -26064.31,
        "day_peak_equity": 0.01,
        "day_pnl_pct": -260643183.249,
        "daily_loss_pct": 0.0,
        "intraday_drawdown_pct": 0.0,
        "halted": True,
        "halt_reason": "daily loss limit hit (3.0%)",
    }
    core.portfolio["equity"] = 13200.0
    module.apply(core)

    rc = core.get_risk_controls()
    assert rc["day_start_equity"] == -26064.31
    assert rc["day_peak_equity"] == 0.01
    assert rc["halted"] is True
    assert rc["halt_reason"] == "daily loss limit hit (3.0%)"
