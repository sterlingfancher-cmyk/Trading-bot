import math
import types

import paper_bidirectional_accounting_guard as bidirectional
import verified_snapshot_accounting_baseline as baseline
import verified_snapshot_epoch_recovery as recovery


def test_exact_contamination_signature_requires_known_bad_tick_rows():
    trades = [{} for _ in range(11)]
    trades[4] = {
        "execution_id": recovery.BAD_VST_EXECUTION_ID,
        "symbol": "VST",
        "action": "exit",
        "price": 20.16,
        "shares": 11.014993,
    }
    trades[10] = {
        "execution_id": recovery.BAD_EXECUTION_ID,
        "symbol": "LRCX",
        "action": "exit",
        "price": 36.26,
        "shares": 3.42486,
    }
    pf = {
        "cash": recovery.EXPECTED_CURRENT_CASH,
        "positions": {},
        "trades": trades,
        "paper_accounting_epoch": {"id": recovery.OLD_EPOCH_ID},
        "risk_controls": {"halted": True, "halt_reason": "absolute daily equity loss halt (3.00%)"},
    }
    assert recovery.contamination_signature(pf) is True
    pf["cash"] += 100.0
    assert recovery.contamination_signature(pf) is False


def test_recovery_reverses_only_lrcx_bad_tick_and_restores_lot():
    pf = {
        "cash": recovery.EXPECTED_CURRENT_CASH,
        "equity": recovery.EXPECTED_CURRENT_CASH,
        "positions": {},
        "trades": [{"x": 1}],
        "history": [],
        "realized_pnl": {"today": -914.64, "total": -800.0, "losses_today": 1, "losses_total": 1},
        "performance": {"realized_pnl_today": -914.64, "realized_pnl_total": -800.0, "losses_today": 1, "losses_total": 1},
        "risk_controls": {"halted": True, "halt_reason": "absolute daily equity loss halt (3.00%)"},
    }
    out = recovery.build_recovered_state(pf, "/tmp/archive", "2026-08-12 15:50:00 CDT")
    expected_cash = recovery.EXPECTED_CURRENT_CASH - recovery.BAD_PROCEEDS
    assert math.isclose(out["cash"], expected_cash, abs_tol=1e-9)
    assert list(out["positions"]) == ["LRCX"]
    pos = out["positions"]["LRCX"]
    assert math.isclose(pos["shares"], 3.42486, abs_tol=1e-9)
    assert math.isclose(pos["entry"], 312.90, abs_tol=1e-9)
    assert math.isclose(pos["last_price"], 326.24, abs_tol=1e-9)
    assert out["trades"] == []
    assert out["paper_accounting_epoch"]["baseline_type"] == "verified_snapshot_with_open_position"
    assert out["risk_controls"]["verified_snapshot_validation_hold"] is True
    assert math.isclose(out["realized_pnl"]["today"], -914.64 - recovery.BAD_REALIZED, abs_tol=1e-9)


def test_snapshot_baseline_reconstructs_open_position_without_trade_rows(monkeypatch):
    # Use the real bidirectional reconciler as the wrapped prior.
    monkeypatch.setattr(bidirectional, "analyze_ledger", getattr(bidirectional.analyze_ledger, "_verified_snapshot_baseline_prior", bidirectional.analyze_ledger))
    baseline._APPLIED = False
    core = types.SimpleNamespace()
    assert baseline.apply(core)["status"] == "ok"

    pf = {
        "cash": 10768.497731,
        "equity": 11885.824057,
        "positions": {
            "LRCX": {"side": "long", "shares": 3.42486, "entry": 312.90, "last_price": 326.24}
        },
        "trades": [],
        "paper_accounting_epoch": {
            "baseline_type": "verified_snapshot_with_open_position",
            "verified_snapshot_baseline": {
                "verified": True,
                "cash": 10768.497731,
                "equity": 11885.824057,
                "realized_today": 32.81327,
                "realized_total": 32.81327,
                "positions": {"LRCX": {"side": "long", "qty": 3.42486, "entry_price": 312.90, "mark": 326.24}},
            },
        },
    }
    rebuilt = bidirectional.analyze_ledger(pf, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["parsed_trade_rows"] == 0
    assert rebuilt["baseline_type"] == "verified_snapshot_with_open_position"
    assert math.isclose(rebuilt["cash"], 10768.497731, abs_tol=1e-6)
    assert "LRCX" in rebuilt["open_positions"]
    assert math.isclose(rebuilt["equity"], 11885.824057, abs_tol=1e-5)


def test_snapshot_baseline_future_exit_closes_restored_lot(monkeypatch):
    monkeypatch.setattr(bidirectional, "analyze_ledger", getattr(bidirectional.analyze_ledger, "_verified_snapshot_baseline_prior", bidirectional.analyze_ledger))
    baseline._APPLIED = False
    core = types.SimpleNamespace()
    baseline.apply(core)
    pf = {
        "positions": {},
        "trades": [{"action": "exit", "symbol": "LRCX", "side": "long", "shares": 3.42486, "price": 326.24, "timestamp": "2026-08-13 14:00:00 UTC"}],
        "paper_accounting_epoch": {
            "baseline_type": "verified_snapshot_with_open_position",
            "verified_snapshot_baseline": {
                "verified": True,
                "cash": 10768.497731,
                "equity": 11885.824057,
                "realized_today": 0.0,
                "realized_total": 0.0,
                "positions": {"LRCX": {"side": "long", "qty": 3.42486, "entry_price": 312.90, "mark": 326.24}},
            },
        },
    }
    rebuilt = bidirectional.analyze_ledger(pf, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["parsed_trade_rows"] == 1
    assert rebuilt["open_positions"] == {}
    assert math.isclose(rebuilt["cash"], 11885.824057, abs_tol=1e-5)
