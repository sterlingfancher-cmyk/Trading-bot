from types import SimpleNamespace

import paper_accounting_integrity_guard as accounting
import paper_ledger_economic_integrity as economics
import paper_ledger_matched_exit_guard as guard
import paper_trade_action_semantics_recovery as semantics


def _core(trades):
    return SimpleNamespace(
        portfolio={
            "history": [10000.0],
            "cash": 10000.0,
            "equity": 10000.0,
            "positions": {},
            "trades": trades,
        },
        local_ts_text=lambda: "2026-08-10 12:00:00 CDT",
    )


def _install(core):
    accounting._trade_fields = semantics.action_first_trade_fields
    economics._trade_fields = semantics.action_first_trade_fields
    guard.apply(core)


def test_entry_then_exit_reconstructs_without_synthetic_cash():
    core = _core([
        {"time": 1, "action": "entry", "symbol": "ABC", "side": "long", "price": 100.0, "shares": 10.0},
        {"time": 2, "action": "exit", "symbol": "ABC", "side": "long", "price": 110.0, "shares": 10.0},
    ])
    _install(core)
    rebuilt = accounting.reconstruct_from_ledger(core.portfolio, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["cash"] == 10100.0
    assert rebuilt["open_positions"] == {}
    assert rebuilt["realized_total"] == 100.0


def test_duplicate_exit_does_not_credit_unmatched_proceeds():
    core = _core([
        {"time": 1, "action": "entry", "symbol": "ABC", "side": "long", "price": 100.0, "shares": 10.0},
        {"time": 2, "action": "exit", "symbol": "ABC", "side": "long", "price": 110.0, "shares": 10.0},
        {"time": 3, "action": "exit", "symbol": "ABC", "side": "long", "price": 120.0, "shares": 10.0},
    ])
    _install(core)
    rebuilt = accounting.reconstruct_from_ledger(core.portfolio, core)
    assert rebuilt["coverage_complete"] is False
    assert rebuilt["cash"] == 10100.0
    assert rebuilt["ignored_trade_rows"] == 1
    assert rebuilt["coverage_issues"][0]["reason"] == "sell_exceeds_reconstructed_position"

    econ = economics.status_payload(core)
    assert econ["overall"] == "fail"
    assert econ["promotion_evidence_eligible"] is False
    assert econ["coverage_complete"] is False


def test_partial_exit_credits_only_matched_quantity():
    core = _core([
        {"time": 1, "action": "entry", "symbol": "ABC", "side": "long", "price": 100.0, "shares": 10.0},
        {"time": 2, "action": "partial_exit", "symbol": "ABC", "side": "long", "price": 105.0, "shares": 4.0},
    ])
    _install(core)
    rebuilt = accounting.reconstruct_from_ledger(core.portfolio, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["cash"] == 9420.0
    assert round(rebuilt["open_positions"]["ABC"]["qty"], 6) == 6.0
    assert rebuilt["realized_total"] == 20.0
