import types

import absolute_daily_halt_lifecycle_guard as guard
import performance_risk_calibration as calibration


def _core(equity, start=10000.0, peak=10010.0):
    state = {
        "equity": equity,
        "cash": equity,
        "performance": {"realized_pnl_today": 0.0},
        "risk_controls": {
            "day_start_equity": start,
            "day_peak_equity": peak,
            "halted": True,
            "halt_reason": "absolute daily equity loss halt (3.00%)",
        },
    }
    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda: "2026-08-12 10:30:00 CDT",
        today_key=lambda: "2026-08-12",
        get_realized_pnl=lambda: {"today": 0.0},
    )


def test_recovered_absolute_daily_halt_is_managed_and_can_clear():
    core = _core(10000.0)
    guard._APPLIED = False
    assert guard.apply(core)["status"] == "ok"

    risk = calibration._decorate_risk(core, core.portfolio["risk_controls"])

    assert risk["daily_loss_pct"] == 0.0
    assert risk["halted"] is False
    assert risk["halt_reason"] == ""
    assert calibration.ABSOLUTE_DAILY == 0.03


def test_active_absolute_daily_loss_is_reasserted_at_same_threshold():
    core = _core(9600.0, start=10000.0, peak=10000.0)
    guard._APPLIED = False
    assert guard.apply(core)["status"] == "ok"

    risk = calibration._decorate_risk(core, core.portfolio["risk_controls"])

    assert risk["daily_loss_pct"] == 4.0
    assert risk["halted"] is True
    assert risk["halt_reason"] == "absolute daily equity loss halt (3.00%)"
    assert calibration.ABSOLUTE_DAILY == 0.03


def test_unrelated_halt_reason_is_not_reclassified():
    guard._APPLIED = False
    assert guard.apply(None)["status"] == "ok"
    assert calibration._managed_halt("canonical execution ledger write failed") is False
