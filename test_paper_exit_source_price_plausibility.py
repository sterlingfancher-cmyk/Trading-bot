import time

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
    cached = core._price_cache["data"]["LRCX"]
    assert cached["price"] == 313.25
    assert cached["source_plausibility_validated_version"] == guard.VERSION
    assert cached["source_plausibility_validated_price"] == 313.25
    assert core.download_calls == 1

    core._prices = [1.0]
    assert core.latest_price("LRCX") == 313.25
    assert core.download_calls == 1


def test_poisoned_fresh_cached_qqq_price_is_blocked_before_return():
    core = FakeCore([728.9, 729.4, 730.1, 730.5, 731.0, 730.7, 729.9, 730.2])
    core._price_cache["data"]["QQQ"] = {
        "ts": time.time(),
        "price": 236.49000549316406,
    }
    guard.apply(core)

    assert core.latest_price("QQQ") is None
    assert "QQQ" not in core._price_cache["data"]
    assert core.download_calls == 1

    source = guard.status_payload(core)["source_plausibility"]
    assert source["last_block"]["symbol"] == "QQQ"
    assert source["last_block"]["boundary"] == "latest_price"
    assert source["last_block"]["reason"] == "catastrophic_cached_price_outlier"
    assert source["last_block"]["price"] == 236.49000549316406
    assert source["last_block"]["price_to_recent_median_ratio"] < guard.SOURCE_MIN_PRICE_RATIO


def test_valid_unvalidated_cache_is_checked_once_then_keeps_60_second_cache_behavior():
    core = FakeCore([728.9, 729.4, 730.1, 730.5, 731.0, 730.7, 729.9, 730.2])
    core._price_cache["data"]["QQQ"] = {
        "ts": time.time(),
        "price": 730.0,
    }
    guard.apply(core)

    assert core.latest_price("QQQ") == 730.0
    assert core.download_calls == 1
    cached = core._price_cache["data"]["QQQ"]
    assert cached["source_plausibility_validated_version"] == guard.VERSION
    assert cached["source_plausibility_validated_price"] == 730.0

    core._prices = [1.0]
    assert core.latest_price("QQQ") == 730.0
    assert core.download_calls == 1
