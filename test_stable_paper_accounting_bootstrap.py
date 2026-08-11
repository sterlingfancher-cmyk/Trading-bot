import types

import paper_bidirectional_accounting_guard as bidirectional
import paper_execution_timestamp_semantics as timestamp_semantics
import stable_paper_accounting_bootstrap as bootstrap


def _core(state):
    recorded = []

    def record_trade(action, symbol, side, px, shares, extra=None):
        recorded.append((action, symbol, side, px, shares, extra or {}))

    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda *args, **kwargs: "2026-08-11 15:00:00 CDT",
        save_state=lambda *args, **kwargs: None,
        record_trade=record_trade,
    )


def test_bootstrap_installs_final_event_semantics_before_reconcile():
    state = {
        "initial_cash": 10000.0,
        "cash": 8400.0,
        "equity": 10000.0,
        "positions": {
            "VST": {"shares": 10.0, "entry": 160.0, "last_price": 160.0, "side": "long"},
        },
        "trades": [
            {
                "time": "2026-08-11 14:30:00 CDT",
                "symbol": "VST",
                "side": "buy",
                "type": "paper_market_surge_deployment",
                "source": "market_surge_deployment_mode",
                "entry": 160.0,
                "shares": 10.0,
            }
        ],
    }
    core = _core(state)
    result = bootstrap.apply(core)
    assert result["status"] == "ok"
    assert bidirectional._event_fields is timestamp_semantics.normalized_event_fields

    rebuilt = bidirectional.analyze_ledger(state, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["ignored_trade_rows"] == 0
    assert rebuilt["cash"] == 8400.0
    assert rebuilt["equity"] == 10000.0
    assert rebuilt["open_positions"]["VST"]["qty"] == 10.0
