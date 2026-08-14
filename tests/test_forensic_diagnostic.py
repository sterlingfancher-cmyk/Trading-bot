from __future__ import annotations

import copy
import diagnostics.forensic_diagnostic as fd


def test_quarantine_implausible_partial_exit_and_preserve_inputs():
    # Persisted sequence to reproduce the scenario described in the handoff:
    # entry UCTT 93.22 -> partial_exit UCTT 337.54 (no entry_price on that row) -> final exit UCTT 94.025
    state = {
        "trades": [
            {
                "action": "entry",
                "symbol": "UCTT",
                "side": "short",
                "price": 93.22,
                "time": 1.0,
            },
            {
                "action": "partial_exit",
                "symbol": "UCTT",
                "side": "short",
                # This is the bad tick that must be quarantined by forensic logic
                "price": 337.54,
                "time": 2.0,
            },
            {
                "action": "exit",
                "symbol": "UCTT",
                "side": "short",
                "price": 94.025,
                "time": 3.0,
            },
        ]
    }

    original = copy.deepcopy(state)
    result = fd.analyze_forensic_trades(state)

    # The function must not mutate inputs
    assert state == original, "analyze_forensic_trades must not mutate its input state"

    # Only the implausible partial_exit should be quarantined
    quarantined = result.get("quarantined_rows") or []
    assert len(quarantined) == 1, f"expected one quarantined row, got {len(quarantined)}"

    q = quarantined[0]
    assert q.get("action") == "partial_exit"
    assert q.get("symbol") == "UCTT"
    assert abs(float(q.get("price")) - 337.54) < 1e-6

    # Never quarantine the legitimate entry or final exit
    entries = [r for r in state.get("trades", []) if r.get("action") == "entry"]
    exits = [r for r in state.get("trades", []) if r.get("action") == "exit"]
    assert entries and exits
    assert all(r not in quarantined for r in entries)
    assert all(r not in quarantined for r in exits)

    # Candidate peak evidence is intentionally absent in this test scenario; the
    # forensic API must return the 'insufficient_evidence' conclusion and None for
    # candidate_peak_equity per the exact handoff contract.
    assert result.get("conclusion") == "insufficient_evidence"
    assert result.get("candidate_peak_equity") is None

    # Hard intraday threshold must remain exactly 0.025 and be reported
    assert result.get("hard_intraday_threshold") == 0.025
