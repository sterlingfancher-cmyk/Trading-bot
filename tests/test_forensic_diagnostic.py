import copy
import pytest

from diagnostics.forensic_diagnostic import analyze_portfolio_forensic


def test_detect_implausible_partial_exit_and_candidate():
    # Prepare a portfolio that includes stored (suspect) peak and current equity
    portfolio = {
        "risk_controls": {"intraday_drawdown_pct": 0.025},
        "day_start_equity": 10000.0,
        "day_peak_equity": 14000.0,  # suspect stored peak
        "equity": 9700.0,
    }

    # Trades: entry -> partial_exit (implausible spike) -> final exit
    trades = [
        {"symbol": "UCTT", "action": "entry", "price": 93.22, "shares": 100, "pnl_dollars": 0.0, "equity": 10000.0},
        {"symbol": "UCTT", "action": "partial_exit", "price": 337.54, "shares": 34, "pnl_dollars": 4000.0, "equity": 14000.0},
        {"symbol": "UCTT", "action": "exit", "price": 94.025, "shares": 66, "pnl_dollars": 100.0, "equity": 10100.0},
    ]

    # Keep deep copies to prove inputs are unchanged
    pf_before = copy.deepcopy(portfolio)
    tr_before = copy.deepcopy(trades)

    report = analyze_portfolio_forensic(portfolio, trades)

    # Inputs must not be mutated
    assert portfolio == pf_before
    assert trades == tr_before

    # Stored fields reported
    assert report["stored_day_start_equity"] == 10000.0
    assert report["stored_day_peak_equity"] == 14000.0
    assert report["current_equity"] == 9700.0

    # Suspicious partial_exit should be identified (index 1)
    assert 1 in report["suspect_trade_indices"]

    # Candidate peak must be computed from trade equity entries excluding suspect
    assert report["candidate_supportable_peak_equity"] == 10100.0
    assert report["candidate_supportable_peak_method"].startswith("derived_")

    # Under stored (suspect) peak drawdown is > threshold
    assert report["threshold_exceeded_under_stored_peak"] is True

    # Under candidate peak (10100 -> current 9700) drawdown still exceeds 2.5%
    assert report["threshold_exceeded_under_candidate"] is True


def test_insufficient_evidence_and_immutability():
    # No equity or pnl evidence in trades -> insufficient evidence for candidate peak
    portfolio = {"risk_controls": {"intraday_drawdown_pct": 0.025}, "day_start_equity": 5000.0, "equity": 4900.0}
    trades = [
        {"symbol": "ABC", "action": "entry", "price": 10.0, "shares": 100},
        {"symbol": "ABC", "action": "partial_exit", "price": 30.0, "shares": 30},
        {"symbol": "ABC", "action": "exit", "price": 9.9, "shares": 70},
    ]

    pf_before = copy.deepcopy(portfolio)
    tr_before = copy.deepcopy(trades)

    report = analyze_portfolio_forensic(portfolio, trades)

    # Inputs unchanged
    assert portfolio == pf_before
    assert trades == tr_before

    assert report["candidate_supportable_peak_equity"] == "insufficient_evidence"
    assert report["threshold_exceeded_under_candidate"] is None

