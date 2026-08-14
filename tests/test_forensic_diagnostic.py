from diagnostics import forensic_diagnostic as fd


def test_partial_exit_quarantine_and_correlation():
    # Reproduce the exact persisted production sequence (no normalization of action names):
    # 1) entry UCTT side=long price=93.22
    # 2) action="partial_exit" UCTT side=long price=337.54 with no entry_price on that row
    # 3) action="exit" UCTT side=long price=94.025
    trades = [
        {"action": "entry", "symbol": "UCTT", "side": "long", "price": 93.22, "time": 1},
        {"action": "partial_exit", "symbol": "UCTT", "side": "long", "price": 337.54, "time": 2},
        {"action": "exit", "symbol": "UCTT", "side": "long", "price": 94.025, "time": 3},
    ]
    state = {"trades": trades}

    result = fd.analyze(state)

    # We must explicitly recognize partial_exit as exit-like and correlate it to the prior entry
    # and quarantine only that partial_exit row (the 337.54 row). We must NOT mutate action values.
    assert result["conclusion"] == "insufficient_evidence"
    assert result["candidate_peak_equity"] is None

    # Ensure we recognized entry and exit-like rows
    assert 0 in result["matched_entries"]
    assert 1 in result["matched_exits"] and 2 in result["matched_exits"]

    # Only the partial_exit (index 1) should be quarantined
    assert result["quarantined_indices"] == [1]
    assert len(result["quarantined_rows"]) == 1
    assert result["quarantined_rows"][0]["action"] == "partial_exit"

    # Correlation evidence should show the partial_exit correlated to the entry
    correlated_pairs = [c for c in result["correlations"] if c[1] == 1]
    assert any(pair[0] == 0 for pair in correlated_pairs), f"expected correlation to entry index 0, got {correlated_pairs}"

    # Ensure the final legitimate exit remains present and not quarantined
    assert 2 not in result["quarantined_indices"]
    assert trades[2]["action"] == "exit"
