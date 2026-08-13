import threading

import verified_snapshot_accounting_baseline as vsab


class DummyCore:
    def __init__(self, portfolio):
        self.portfolio = portfolio

    def local_ts_text(self):
        return "2026-08-12 12:00:00"


def test_build_working_skips_noncopyable_telemetry_and_preserves_accounting():
    # Create a non-copyable telemetry object (Lock) and insert into portfolio
    locker = threading.Lock()
    # Put intentionally non-copyable / mutable telemetry under a deep tree key
    portfolio = {
        "trades": [
            {"execution_id": "x1", "symbol": "LRCX", "action": "entry", "price": 312.9, "shares": 3.42486},
            {"execution_id": "bad_exit", "symbol": "LRCX", "action": "exit", "price": 36.26, "shares": 3.42486},
        ],
        "positions": {},
        "cash": 10892.683154582748,
        "equity": 10892.683154582748,
        "history": [],
        "performance": {"realized_pnl_today": 0.0},
        "risk_controls": {"halted": True, "halt_reason": "absolute daily equity loss halt"},
        "paper_accounting_epoch": {"id": "stable-paper-v1-20260810-clean01"},
        # Telemetry subtree that must NOT be traversed / deep-copied by our fix.
        "auto_runner": {"last_result": {"entries": []}, "internal_lock": locker},
    }

    core = DummyCore(portfolio)

    payload = vsab.apply(core)

    # Ensure apply succeeded and returned working counts derived from trades
    assert payload.get("status") == "ok"
    assert payload.get("working_trades_count") == 2
    # Ensure the non-copyable telemetry object still lives in the original portfolio
    assert portfolio["auto_runner"]["internal_lock"] is locker

    # Ensure that the working_snapshot shape is present (backwards-compatible)
    snap = payload.get("working_snapshot")
    assert isinstance(snap, dict)


def test_synthetic_entry_rows_from_verified_baseline():
    # If a verified_snapshot_baseline contains a position, synthetic rows are produced
    portfolio = {
        "trades": [],
        "positions": {},
        "cash": 10000.0,
        "equity": 10000.0,
        "paper_accounting_epoch": {
            "id": "stable-paper-v2-20260812-verified01",
            "verified_snapshot_baseline": {
                "positions": {
                    "LRCX": {"side": "long", "qty": 3.42486, "entry_price": 312.9, "mark": 326.24}
                }
            }
        }
    }
    core = DummyCore(portfolio)
    result = vsab.apply(core)
    assert result["status"] == "ok"
    # Working trades count should equal number of synthetic entries produced
    assert result["working_trades_count"] == 1
