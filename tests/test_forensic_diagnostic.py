from copy import deepcopy
import diagnostics.forensic_diagnostic as fd


def test_quarantine_exact_production_sequence_and_reporting():
    # Build the exact production sequence described in the instruction.
    # 1) entry UCTT side=long price=93.22
    # 2) partial_exit UCTT side=long price=337.54 with no entry_price on that row
    # 3) final exit UCTT side=long price=94.025
    trades = [
        {
            "action": "entry",
            "symbol": "UCTT",
            "side": "long",
            "price": 93.22,
            # typical production entry row may include entry_price; include it here
            "entry_price": 93.22,
        },
        {
            # partial exit row intentionally missing any entry_price on that row
            "action": "exit",
            "symbol": "UCTT",
            "side": "long",
            "price": 337.54,
        },
        {
            # final legitimate exit near entry
            "action": "exit",
            "symbol": "UCTT",
            "side": "long",
            "price": 94.025,
        },
    ]

    state = {"trades": deepcopy(trades)}
    before = deepcopy(state)

    report = fd.analyze_trades(state)

    # Ensure original input not mutated
    assert state == before, "analyze_trades must not mutate input state"

    # Exact production rows retained in original order
    assert len(state["trades"]) == 3
    assert state["trades"][0]["action"] == "entry"
    assert state["trades"][1]["action"] == "exit"
    assert state["trades"][2]["action"] == "exit"

    # Exactly one quarantined partial: the middle row (index 1)
    assert isinstance(report, dict)
    quarantined = report.get("quarantined_rows")
    assert quarantined is not None
    assert len(quarantined) == 1, "expected exactly one quarantined row"
    assert quarantined[0] == 1, "the partial spike (middle row) must be quarantined"

    # Verify quarantined row details correlate to the most-recent same-side long entry (index 0)
    details = report.get("quarantined_rows_details")
    assert len(details) == 1
    d0 = details[0]
    assert d0["matched_entry_index"] == 0
    assert d0["symbol"] == "UCTT"
    assert d0["side"] == "long"

    # Confirm the specific numeric thresholds remain unchanged exactly
    thr = report.get("thresholds")
    assert thr is not None
    assert thr["low_factor"] == 0.40
    assert thr["high_factor"] == 2.50
    assert thr["intraday_hard_threshold"] == 0.025

    # The quarantined ratio should be >= 2.5 for the middle row
    ratio = d0["ratio"]
    assert ratio >= thr["high_factor"]

    # The legitimate entry and final exit must be retained (not quarantined)
    retained = set(report.get("retained_rows") or [])
    assert 0 in retained and 2 in retained

    # Per instruction: do not fabricate independent peak evidence -> insufficient_evidence
    assert report.get("conclusion") == "insufficient_evidence"
    assert report.get("candidate_peak_equity") is None

    # Confirm input-immutability flag
    assert report.get("input_unchanged") is True
