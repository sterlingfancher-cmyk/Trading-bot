import paper_exit_price_integrity_guard as guard


class FakeCore:
    def __init__(self, prices):
        self.portfolio = {"positions": {}, "risk_controls": {}}
        self._price_cache = {"data": {}}
        self._prices = list(prices)
        self.download_calls = 0

    def latest_price(self, symbol):
        raise AssertionError("wrapped latest_price must not delegate through the unsafe cache path")

    def download_prices(self, symbol, period="5d", interval="5m"):
        self.download_calls += 1
        return list(self._prices)

    def price_series(self, frame, column="Close"):
        return list(frame)

    def exit_position(self, symbol, px, *args, **kwargs):
        return {"symbol": symbol, "price": px}

    def reduce_position(self, symbol, px, *args, **kwargs):
        return {"symbol": symbol, "price": px}


def test_catastrophic_terminal_outlier_is_rejected_before_cache():
    core = FakeCore([311.8, 312.2, 312.5, 312.7, 312.4, 312.9, 313.1, 18.401199340820312])
    guard.apply(core)

    assert core.latest_price("LRCX") is None
    assert "LRCX" not in core._price_cache["data"]

    status = guard.status_payload(core)
    source = status["source_plausibility"]
    assert source["installed"] is True
    assert source["last_block"]["symbol"] == "LRCX"
    assert source["last_block"]["boundary"] == "latest_price"
    assert source["last_block"]["reason"] == "catastrophic_terminal_bar_outlier"
    assert source["last_block"]["price"] == 18.401199340820312


def test_plausible_terminal_price_is_returned_and_cached():
    core = FakeCore([311.8, 312.2, 312.5, 312.7, 312.4, 312.9, 313.1, 313.25])
    guard.apply(core)

    assert core.latest_price("LRCX") == 313.25
    assert core._price_cache["data"]["LRCX"]["price"] == 313.25
    assert core.download_calls == 1

    core._prices = [1.0]
    assert core.latest_price("LRCX") == 313.25
    assert core.download_calls == 1
