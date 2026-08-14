from diagnostics import forensic_diagnostic as fd
import copy
import math


def test_quarantine_and_insufficient_evidence_does_not_use_stored_peak_and_keeps_threshold():
    # Build production-like nested risk_controls with a stored day_peak_equity and intraday_drawdown_pct
    portfolio = {
        "risk_controls": {
            "current": 11.73,  # provenance metric (k-format in production-like state)
            "day_peak_equity": 20000.0,  # MUST NOT be used as candidate support
            "intraday_drawdown_pct": 0.10,
        },
        # current equity metric in account (11.73k)
        "equity": 11730.0,
        # Trades include a legitimate entry and legitimate final exit, plus the single bad partial
        "trades": [
            {"id": "t_entry", "symbol": "UCTT", "action": "entry", "price": 93.22, "timestamp": 1},
            {"id": "t_bad_partial", "symbol": "UCTT", "action": "exit", "price": 337.54, "timestamp": 2, "reason": "partial_exit", "entry_price": 93.22},
            {"id": "t_normal_exit", "symbol": "UCTT", "action": "exit", "price": 94.025, "timestamp": 3, "pnl_dollars": 100.0, "entry_price": 93.22},
        ],
        # day_start_equity intentionally omitted to force insufficient independent evidence
    }

    before = copy.deepcopy(portfolio)
    report = fd.analyze(portfolio)

    # Stored peak must NOT be used
    assert report["used_stored_peak"] is False

    # The single known bad partial should be quarantined, others not
    assert report["quarantined_trade_ids"] == ["t_bad_partial"]

    # Threshold remains the fixed value exactly 0.025
    assert math.isclose(report["reported_threshold"], 0.025, rel_tol=1e-12)

    # Independent evidence is insufficient because no day_start_equity and no explicit equity snapshots
    assert report["conclusion"] == "insufficient_evidence"
    assert report["candidate_peak_equity"] is None
    assert report["candidate_intraday_drawdown_fraction"] is None
    # No claim about whether the halt is justified
    assert report["candidate_hard_halt_exceeded"] is None

    # Ensure inputs were not mutated
    assert portfolio == before


def test_independent_equity_evidence_computes_candidate_and_threshold_applies():
    # Here we provide explicit independent equity evidence via equity_snapshot and day_start_equity
    portfolio = {
        "risk_controls": {
            "current": 11.73,
            "day_peak_equity": 999999.0,  # must NOT be used
            "intraday_drawdown_pct": 0.50,
        },
        # current equity lower than the explicit peak
        "equity": 14500.0,
        # day_start_equity available to allow realized progression if needed
        "day_start_equity": 12000.0,
        "trades": [
            {"id": "t_entry", "symbol": "UCTT", "action": "entry", "price": 93.22, "timestamp": 1},
            # known bad partial must still be quarantined
            {"id": "t_bad_partial", "symbol": "UCTT", "action": "exit", "price": 337.54, "timestamp": 2, "reason": "partial_exit", "entry_price": 93.22, "pnl_dollars": 2000.0},
            # a normal exit that is legitimate and contributes realized pnl
            {"id": "t_normal_exit", "symbol": "UCTT", "action": "exit", "price": 94.025, "timestamp": 3, "pnl_dollars": 100.0, "entry_price": 93.22},
            # explicit equity snapshot giving an independent peak
            {"id": "snapshot_peak", "equity_snapshot": 15100.0, "timestamp": 4},
        ],
    }

    before = copy.deepcopy(portfolio)
    report = fd.analyze(portfolio)

    # Stored peak must still NOT be used
    assert report["used_stored_peak"] is False

    # Only the known implausible partial is quarantined
    assert report["quarantined_trade_ids"] == ["t_bad_partial"]

    # Candidate should be found (explicit snapshot 15100) and used as peak
    assert report["conclusion"] == "candidate_found"
    assert report["candidate_peak_equity"] == 15100.0

    # Drawdown fraction = (15100 - 14500) / 15100
    expected_fraction = (15100.0 - 14500.0) / 15100.0
    assert math.isclose(report["candidate_intraday_drawdown_fraction"], expected_fraction, rel_tol=1e-12)

    # Threshold is fixed 0.025; this drawdown should exceed it
    assert math.isclose(report["reported_threshold"], 0.025, rel_tol=1e-12)
    assert report["candidate_hard_halt_exceeded"] is True

    # Ensure inputs were not mutated
    assert portfolio == before
