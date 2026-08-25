from __future__ import annotations

import paper_bidirectional_accounting_guard as accounting


def _trade(action, shares, price=36.0):
    return {
        "action": action,
        "symbol": "TOST",
        "side": "long",
        "shares": shares,
        "price": price,
        "timestamp": "2026-08-25 10:00:00 CDT",
    }


def test_six_decimal_state_trade_residue_is_accepted_as_serialization_only():
    portfolio = {
        "initial_cash": 10000.0,
        "trades": [
            _trade("entry", 3.767684, 36.0501),
            _trade("partial_exit", 1.243336, 36.87),
            _trade("exit", 2.524349, 36.775),
        ],
        "positions": {},
    }

    rebuilt = accounting.analyze_ledger(portfolio)

    assert rebuilt["coverage_complete"] is True
    assert rebuilt["coverage_issue_count"] == 0
    assert rebuilt["ignored_trade_rows"] == 0
    assert rebuilt["open_positions"] == {}


def test_material_state_trade_quantity_gap_still_fails_closed():
    portfolio = {
        "initial_cash": 10000.0,
        "trades": [
            _trade("entry", 3.767684, 36.0501),
            _trade("partial_exit", 1.243336, 36.87),
            _trade("exit", 2.524354, 36.775),
        ],
        "positions": {},
    }

    rebuilt = accounting.analyze_ledger(portfolio)

    assert rebuilt["coverage_complete"] is False
    assert rebuilt["coverage_issue_count"] == 1
    issue = rebuilt["coverage_issues"][0]
    assert issue["reason"] == "exit_exceeds_reconstructed_position"
    assert issue["unmatched_qty"] > accounting.STATE_TRADE_QTY_SERIALIZATION_TOLERANCE
