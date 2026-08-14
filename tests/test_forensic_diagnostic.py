from diagnostics import forensic_diagnostic


def test_quarantine_exact_bad_partial_rows_and_insufficient_evidence():
    # Reproduce the exact persisted UCTT sequence seen in the daily audit.
    trades = [
        {
            "action": "entry",
            "symbol": "UCTT",
            "side": "long",
            "price": 93.22,
            "entry_price": 93.22,
        },
        # The bad persisted partial exit row: no entry_price field present,
        # wildly different price, but appears after the entry for UCTT.
        {
            "action": "partial_exit",
            "symbol": "UCTT",
            "side": "long",
            "price": 337.54,
            # intentionally missing entry_price
        },
        # Legitimate final exit row after the bad partial
        {
            "action": "exit",
            "symbol": "UCTT",
            "side": "long",
            "price": 94.025,
            "pnl_dollars": 0.80,
        },
    ]

    state = {"trades": trades}

    report = forensic_diagnostic.forensic_audit(state)

    # Exactly the single bad partial row (index 1) should be quarantined
    assert report["quarantined_trade_indices"] == [1]
    assert len(report["quarantined_trades"]) == 1
    assert report["quarantined_trades"][0]["action"] == "partial_exit"
    assert report["quarantined_trades"][0]["symbol"] == "UCTT"

    # Because no independent equity snapshots or starting equity were provided,
    # the forensic routine must not invent peak evidence and should report
    # insufficient evidence (candidate_peak_equity None)
    assert report["conclusion"] == "insufficient_evidence"
    assert report["candidate_peak_equity"] is None
    assert report["candidate_hard_halt_exceeded"] is None

    # The hard intraday threshold must be exposed and equal to 0.025 exactly
    assert report.get("hard_intraday_threshold") == 0.025
