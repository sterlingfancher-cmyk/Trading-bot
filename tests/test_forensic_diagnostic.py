from copy import deepcopy

from diagnostics.forensic_diagnostic import (
    forensic_analysis,
    DEFAULT_HARD_INTRADAY_THRESHOLD_FRACTION,
)


def test_report_shape_and_threshold_ignores_intraday_pct_metric():
    # Prepare a production-like portfolio where intraday_drawdown_pct is stored
    # as a percent-like metric (11.73) inside risk_controls. Current equity sits
    # at portfolio['equity'] per canonical shape.
    portfolio = {
        "equity": 9900.0,
        "risk_controls": {
            "day_start_equity": 10000.0,
            "day_peak_equity": 11000.0,
            "intraday_drawdown_pct": 11.73,  # stored metric (percent-like)
        },
    }
    trades = []

    # preserve a deep copy for mutation-proof check
    portfolio_copy = deepcopy(portfolio)
    trades_copy = deepcopy(trades)

    report = forensic_analysis(portfolio, trades)

    # Inputs must remain unchanged
    assert portfolio == portfolio_copy
    assert trades == trades_copy

    # Canonical shape: current equity at portfolio['equity'] and day_* inside risk_controls
    assert report["metrics"]["equity"] == portfolio["equity"]
    rc = report["metrics"]["risk_controls"]
    assert rc["day_start_equity"] == portfolio["risk_controls"]["day_start_equity"]
    assert rc["day_peak_equity"] == portfolio["risk_controls"]["day_peak_equity"]

    # The stored intraday metric is reported as current but NOT used as the hard threshold
    assert rc["raw_intraday_drawdown_pct_stored"] == 11.73
    # reported converted fraction should reflect 11.73% -> 0.1173
    assert abs(rc["intraday_drawdown_fraction_current"] - 0.1173) < 1e-8

    # Effective hard threshold should remain default 0.025 unless explicitly supplied
    assert report["effective_hard_intraday_threshold_fraction"] == DEFAULT_HARD_INTRADAY_THRESHOLD_FRACTION
    assert report["effective_hard_intraday_threshold_pct"] == DEFAULT_HARD_INTRADAY_THRESHOLD_FRACTION * 100.0

    # Because computed intraday drawdown is (11000 - 9900)/11000 ~= 0.10 and that's
    # above the stored metric converted (and above threshold), the report may flag
    # potential issue based only on computed drawdown. Ensure the stored metric was
    # not used as threshold by checking explicit fields are present.
    assert "intraday_drawdown_fraction_computed" in report["metrics"]["computed"]


def test_exclude_uctt_bad_tick_and_insufficient_evidence():
    # Construct trades that include the known bad-tick UCTT rows and one innocuous trade
    trades = [
        {"symbol": "UCTT", "type": "entry", "price": 93.22, "qty": 1},
        {"symbol": "UCTT", "type": "partial_exit", "price": 337.54, "qty": 0.5},
        {"symbol": "UCTT", "type": "exit", "price": 94.025, "qty": 0},
        # a small normal trade that should not by itself constitute independent evidence
        {"symbol": "ABC", "type": "entry", "price": 20.0, "qty": 1},
    ]
    portfolio = {
        "equity": 10000.0,
        "risk_controls": {
            "day_start_equity": 10005.0,
            "day_peak_equity": 10010.0,
            "intraday_drawdown_pct": 0.05,  # stored as fraction-ish value (allowed)
        },
    }

    portfolio_copy = deepcopy(portfolio)
    trades_copy = deepcopy(trades)

    report = forensic_analysis(portfolio, trades)

    # Inputs not mutated
    assert portfolio == portfolio_copy
    assert trades == trades_copy

    # The UCTT bad-tick indices should be listed as excluded and not appear in suspect_trades
    excluded = report["excluded_trade_indices_known_bad_ticks"]
    assert set(excluded) == {0, 1, 2}
    # Suspect trades should not include the excluded UCTT rows
    for s in report["suspect_trades"]:
        assert s["index"] not in excluded

    # There is insufficient independent evidence here: only an innocuous ABC entry
    assert report["conclusion"] == "insufficient_evidence"


def test_day_peak_not_used_as_support_and_report_flagged_false():
    # Ensure the report explicitly states that stored day_peak_equity was not used as support
    portfolio = {
        "equity": 9999.0,
        "risk_controls": {
            "day_start_equity": 10000.0,
            "day_peak_equity": 12000.0,
            "intraday_drawdown_pct": 16.675,  # percent-like number
        },
    }
    trades = []
    r = forensic_analysis(portfolio, trades)
    assert r.get("used_stored_day_peak_equity_as_support") is False
