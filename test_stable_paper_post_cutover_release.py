import datetime as dt
import types

import administrative_halt_classification_guard as admin_guard
import clean_epoch_validation_release as release
import paper_bidirectional_accounting_guard as bidirectional
import paper_execution_timestamp_semantics as timestamp_semantics


def _core(state=None):
    state = state or {}
    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda *args, **kwargs: "2026-08-10 13:45:00 CDT",
        save_state=lambda *args, **kwargs: None,
    )


def test_epoch_seconds_are_normalized_to_calendar_timestamp():
    epoch = dt.datetime(2026, 8, 10, 18, 30, tzinfo=dt.timezone.utc).timestamp()
    row = {
        "action": "exit",
        "symbol": "AMD",
        "side": "long",
        "shares": 2,
        "price": 150,
        "time": epoch,
    }
    symbol, event, side, qty, price, timestamp = timestamp_semantics.normalized_event_fields(row)
    assert symbol == "AMD"
    assert event == "exit"
    assert side == "long"
    assert qty == 2
    assert price == 150
    assert timestamp.startswith("2026-08-10 ")


def test_unknown_canonical_side_fails_closed():
    row = {
        "action": "entry",
        "symbol": "AMD",
        "side": "mystery",
        "shares": 1,
        "price": 100,
        "timestamp": "2026-08-10 13:00:00",
    }
    _, event, side, _, _, _ = timestamp_semantics.normalized_event_fields(row)
    assert event == "entry"
    assert side == ""


def test_bidirectional_accounting_reconstructs_long_and_short_round_trips(monkeypatch):
    # Make the reconciler use the normalized Stable Paper semantics directly.
    monkeypatch.setattr(bidirectional, "_event_fields", timestamp_semantics.normalized_event_fields)
    epoch = dt.datetime(2026, 8, 10, 18, 30, tzinfo=dt.timezone.utc).timestamp()
    state = {
        "initial_cash": 10000.0,
        "cash": 10200.0,
        "equity": 10200.0,
        "positions": {},
        "trades": [
            {"action": "entry", "symbol": "AMD", "side": "long", "shares": 10, "price": 100, "time": epoch},
            {"action": "exit", "symbol": "AMD", "side": "long", "shares": 10, "price": 110, "time": epoch},
            {"action": "entry", "symbol": "CRWD", "side": "short", "shares": 5, "price": 200, "time": epoch},
            {"action": "exit", "symbol": "CRWD", "side": "short", "shares": 5, "price": 180, "time": epoch},
        ],
    }
    rebuilt = bidirectional.analyze_ledger(state, _core(state))
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["ignored_trade_rows"] == 0
    assert rebuilt["economic_issue_count"] == 0
    assert rebuilt["cash"] == 10200.0
    assert rebuilt["equity"] == 10200.0
    assert rebuilt["realized_total"] == 200.0
    assert rebuilt["realized_today"] == 200.0
    assert rebuilt["open_positions"] == {}


def test_administrative_hold_is_not_mislabeled_as_loss_self_defense():
    state = {
        "risk_controls": {
            "halted": True,
            "halt_reason": "clean accounting epoch validation hold",
            "clean_epoch_validation_hold": True,
            "daily_loss_pct": 0.0,
            "daily_drawdown_pct": 0.0,
            "intraday_drawdown_pct": 0.0,
            "realized_loss_pct": 0.0,
        },
        "feedback_loop": {},
    }
    feedback = {
        "self_defense_mode": True,
        "block_new_entries": True,
        "hard_halt": True,
        "reasons": ["hard risk halt active"],
    }
    out = admin_guard._normalize(_core(state), feedback, True)
    assert out["self_defense_mode"] is False
    assert out["hard_halt"] is False
    assert state["risk_controls"]["halted"] is True
    assert state["risk_controls"]["halt_reason"] == "clean accounting epoch validation hold"
    assert state["risk_controls"]["self_defense_active"] is False


def test_release_module_never_clears_unrelated_risk_halt():
    state = {
        "accounting_epoch_id": release.TARGET_EPOCH_ID,
        "paper_accounting_epoch": {
            "id": release.TARGET_EPOCH_ID,
            "clean_start": True,
            "zero_trade_baseline": True,
            "historical_evidence_archived": True,
        },
        "risk_controls": {
            "halted": True,
            "halt_reason": "performance risk hard intraday drawdown halt (2.50%)",
            "clean_epoch_validation_hold": False,
        },
    }
    out = release.apply(_core(state))
    assert out["status"] != "released"
    assert state["risk_controls"]["halted"] is True
    assert state["risk_controls"]["halt_reason"].startswith("performance risk hard")
