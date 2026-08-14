import copy

from forensic_intraday_peak_diagnostic import analyze_intraday_peak


class DummyCore:
    def __init__(self, portfolio):
        # store a copy to help test that analyze_intraday_peak does not mutate
        self.portfolio = copy.deepcopy(portfolio)

    def load_state(self):
        return copy.deepcopy(self.portfolio)


def test_detects_implausible_uctt_partial_exit_and_halt_warranted():
    # Historical UCTT entry at 93.22 then a partial exit at 337.54 -> ratio ~3.628 (>2.5)
    portfolio = {
        "day_start_equity": 10000.0,
        "day_peak_equity": 11000.0,
        "equity": 10500.0,
        "trade_journal": [
            {"symbol": "UCTT", "action": "entry", "price": 93.22, "quantity": 10},
            {"symbol": "UCTT", "action": "partial_exit", "price": 337.54, "quantity": 5},
        ],
    }
    core = DummyCore(portfolio)
    before_state = copy.deepcopy(core.portfolio)

    report = analyze_intraday_peak(core, intraday_halt_threshold=0.025, partial_exit_implausible_ratio=2.5)

    # Stored values are reported as given
    assert report["stored_day_start_equity"] == 10000.0
    assert report["stored_day_peak_equity"] == 11000.0
    assert report["current_equity"] == 10500.0

    # Drawdown from stored peak: (11000 - 10500) / 11000 ~ 0.04545
    assert report["reported_drawdown_pct"] is not None
    assert 0.045 <= report["reported_drawdown_pct"] <= 0.046

    # Implausible partial exit flagged
    implaus = report["implausible_partial_exits"]
    assert isinstance(implaus, list) and len(implaus) >= 1
    u = [x for x in implaus if x["symbol"] == "UCTT"][0]
    assert u["entry_price"] == 93.22
    assert u["partial_exit_price"] == 337.54
    assert u["ratio"] > 2.5

    # Candidate day peak should be the max of start/peak/current -> 11000
    assert report["candidate_day_peak_equity"] == 11000.0

    # Candidate drawdown (11000->10500) still > 2.5% threshold -> halt warranted
    assert report["candidate_halt_warranted"] is True

    # Ensure original core.portfolio was not mutated
    assert core.portfolio == before_state


def test_no_implausible_when_ratio_below_threshold_and_halt_not_warranted():
    portfolio = {
        "day_start_equity": 20000.0,
        "day_peak_equity": 20500.0,
        "equity": 20490.0,
        "trade_journal": [
            {"symbol": "ABC", "action": "entry", "price": 100.0, "quantity": 10},
            {"symbol": "ABC", "action": "partial_exit", "price": 200.0, "quantity": 5},
        ],
    }
    core = DummyCore(portfolio)
    report = analyze_intraday_peak(core, intraday_halt_threshold=0.025, partial_exit_implausible_ratio=2.5)

    # Ratio 2.0 should not be flagged
    assert report["implausible_partial_exits"] == []

    # Candidate peak is max(20000,20500,20490) -> 20500
    assert report["candidate_day_peak_equity"] == 20500.0

    # Candidate drawdown = (20500 - 20490) / 20500 = ~0.0004878 -> not > 0.025
    assert report["candidate_halt_warranted"] is False
