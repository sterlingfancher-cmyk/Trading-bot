from __future__ import annotations

import time

from paper_exit_price_integrity_guard import _wrap_latest_price


class CoreStub:
    def __init__(self, cache_entry_price, recent_closes=None):
        # production-shaped cache
        self._price_cache = {"data": {"QQQ": {"ts": int(time.time()), "price": cache_entry_price}}}
        # track marker calls
        self.mark_calls = []
        # provider simulation
        self._recent = recent_closes or []

    def latest_price(self, symbol):
        # original latest_price would return what is in cache
        return self._price_cache["data"].get(symbol, {}).get("price")

    def download_prices(self, symbol, *args, **kwargs):
        # Return the simulated recent-closes in a list of dicts (common provider shape)
        return [{"close": v} for v in self._recent]

    def _mark_source_block(self, symbol, reason):
        self.mark_calls.append((symbol, reason))


def test_poisoned_cached_price_is_blocked_and_returns_none():
    # Poisoned cached QQQ ~236 while recent real bars around ~730
    core = CoreStub(cache_entry_price=236.49000549316406, recent_closes=[730.0, 729.5, 731.0, 730.2])
    wrapped = _wrap_latest_price(core)
    val = wrapped("QQQ")
    assert val is None
    assert len(core.mark_calls) == 1
    sym, reason = core.mark_calls[0]
    assert sym == "QQQ"
    assert "cached-source-untrusted" in reason or "cached-poisoned" in reason


def test_valid_cached_price_is_accepted_and_provenance_recorded():
    core = CoreStub(cache_entry_price=730.12, recent_closes=[730.0, 729.9, 730.2, 731.1])
    wrapped = _wrap_latest_price(core)
    val = wrapped("QQQ")
    assert val == 730.12
    # provenance should be stored in the cache entry so subsequent hits do not re-download
    entry = core._price_cache["data"]["QQQ"]
    assert "validation" in entry
    assert isinstance(entry["validation"].get("median_anchor"), float)

    # Call again; download_prices should not be necessary. To validate, replace provider with one that would raise
    core.download_prices = lambda s: (_ for _ in ()).throw(RuntimeError("should-not-be-called"))
    val2 = wrapped("QQQ")
    assert val2 == 730.12


if __name__ == "__main__":
    test_poisoned_cached_price_is_blocked_and_returns_none()
    test_valid_cached_price_is_accepted_and_provenance_recorded()
    print("ok")
