import types

import market_surge_canonical_execution_bridge as bridge
import market_surge_deployment_mode as surge
import paper_bidirectional_accounting_guard as bidirectional
import paper_execution_timestamp_semantics as semantics


def test_verified_legacy_surge_entry_row_reconciles():
    row = {
        "time": "2026-08-11 14:45:00 CDT",
        "symbol": "VST",
        "side": "buy",
        "type": "paper_market_surge_deployment",
        "source": "market_surge_deployment_mode",
        "entry": 150.0,
        "shares": 10.0,
    }
    symbol, event, side, qty, price, timestamp = semantics.normalized_event_fields(row)
    assert symbol == "VST"
    assert event == "entry"
    assert side == "long"
    assert qty == 10.0
    assert price == 150.0
    assert timestamp.startswith("2026-08-11")


def test_unmarked_row_does_not_use_entry_field_as_fill():
    row = {
        "time": "2026-08-11 14:45:00 CDT",
        "symbol": "VST",
        "side": "buy",
        "entry": 150.0,
        "shares": 10.0,
    }
    _, event, side, qty, price, _ = semantics.normalized_event_fields(row)
    assert event == "entry"
    assert side == "long"
    assert qty == 10.0
    assert price == 0.0


def test_legacy_surge_entry_restores_open_position_accounting(monkeypatch):
    monkeypatch.setattr(bidirectional, "_event_fields", semantics.normalized_event_fields)
    state = {
        "initial_cash": 10000.0,
        "cash": 8500.0,
        "equity": 10000.0,
        "positions": {
            "VST": {
                "side": "long",
                "shares": 10.0,
                "entry": 150.0,
                "last_price": 151.0,
            }
        },
        "trades": [
            {
                "time": "2026-08-11 14:45:00 CDT",
                "symbol": "VST",
                "side": "buy",
                "type": "paper_market_surge_deployment",
                "source": "market_surge_deployment_mode",
                "entry": 150.0,
                "shares": 10.0,
            }
        ],
    }
    core = types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda *args, **kwargs: "2026-08-11 15:00:00 CDT",
    )
    rebuilt = bidirectional.analyze_ledger(state, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["ignored_trade_rows"] == 0
    assert rebuilt["economic_issue_count"] == 0
    assert rebuilt["cash"] == 8500.0
    assert rebuilt["equity"] == 10010.0
    assert rebuilt["open_positions"]["VST"]["qty"] == 10.0


def test_surge_bridge_routes_entries_through_record_trade(monkeypatch):
    captured = []

    def record_trade(action, symbol, side, px, shares, extra=None):
        captured.append((action, symbol, side, px, shares, extra or {}))

    core = types.SimpleNamespace(record_trade=record_trade, portfolio={})
    original = surge._append_trade_rows
    try:
        result = bridge.apply(core)
        assert result["status"] == "ok"
        surge._append_trade_rows(
            {},
            [{
                "symbol": "LRCX",
                "entry": 120.0,
                "shares": 5.0,
                "allocation_dollars": 600.0,
                "allocation_pct": 6.0,
                "account_risk_pct": 0.2,
                "bucket": "semi_leaders",
                "selection_reason": "test",
            }],
            "2026-08-11 14:55:00 CDT",
        )
        assert len(captured) == 1
        action, symbol, side, px, shares, extra = captured[0]
        assert action == "entry"
        assert symbol == "LRCX"
        assert side == "long"
        assert px == 120.0
        assert shares == 5.0
        assert extra["source"] == "market_surge_deployment_mode"
        assert extra["type"] == "paper_market_surge_deployment"
    finally:
        surge._append_trade_rows = original
