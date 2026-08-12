import types

import data_integrity_startup_bridge as startup
import paper_accounting_integrity_guard as accounting
import paper_bidirectional_accounting_guard as bidirectional
import paper_execution_timestamp_semantics as timestamp_semantics
import paper_ledger_matched_exit_guard as matched
import paper_trade_action_semantics_recovery as action_semantics
import stable_paper_accounting_bootstrap as bootstrap


def _core(state):
    recorded = []

    def record_trade(action, symbol, side, px, shares, extra=None):
        recorded.append((action, symbol, side, px, shares, extra or {}))

    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda *args, **kwargs: "2026-08-12 10:45:00 CDT",
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


def test_startup_places_final_bootstrap_after_legacy_overlays_before_reconcile():
    modules = startup.MODULES
    assert modules.index("paper_ledger_matched_exit_guard") < modules.index("stable_paper_accounting_bootstrap")
    assert modules.index("paper_trade_action_semantics_recovery") < modules.index("stable_paper_accounting_bootstrap")
    assert modules.index("stable_paper_accounting_bootstrap") < modules.index("paper_accounting_integrity_guard")


def test_final_bootstrap_restores_surge_entry_semantics_before_exit_reconcile():
    state = {
        "initial_cash": 10000.0,
        "cash": 10010.0,
        "equity": 10010.0,
        "paper_accounting_epoch": {
            "id": "stable-paper-v1-20260810-clean01",
            "clean_start": True,
            "zero_trade_baseline": True,
        },
        "positions": {},
        "trades": [
            {
                "time": "2026-08-11 14:45:00 CDT",
                "symbol": "CLSK",
                "side": "buy",
                "type": "paper_market_surge_deployment",
                "source": "market_surge_deployment_mode",
                "entry": 10.0,
                "shares": 100.0,
            },
            {
                "time": 1786456978,
                "action": "exit",
                "symbol": "CLSK",
                "side": "long",
                "price": 10.1,
                "shares": 100.0,
            },
        ],
    }
    core = _core(state)

    matched.apply(core)
    action_semantics.apply(core)
    result = bootstrap.apply(core)

    assert result["status"] == "ok"
    assert accounting.reconstruct_from_ledger is bidirectional.analyze_ledger
    assert bidirectional._event_fields is timestamp_semantics.normalized_event_fields

    rebuilt = accounting.reconstruct_from_ledger(state, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["ignored_trade_rows"] == 0
    assert rebuilt["coverage_issue_count"] == 0
    assert rebuilt["realized_total"] == 10.0
    assert rebuilt["cash"] == 10010.0
    assert rebuilt["open_positions"] == {}
