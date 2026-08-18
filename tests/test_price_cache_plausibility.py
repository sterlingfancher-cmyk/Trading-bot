import time

from price_cache_plausibility_guard import ensure_plausible_cached_price


class DummyCore:
    def __init__(self):
        # shape: symbol -> row dict
        self._price_cache = {}
        # keep a lightweight portfolio/market history for median computation
        self.portfolio = {"market_history": {}}
        # expose a TTL to be discovered by the helper
        self.MARKET_CACHE_TTL = 60

    def download_prices(self, symbol):
        # Simulate a real downloader that refreshes the in-memory cache with a sane price
        sym = symbol.upper()
        # produce a sane price for test symbol QQQ (312-ish)
        row = {
            "ts": time.time(),
            "price": 312.0,
            "last_price": 312.0,
            "source_plausibility": {"last_block": time.time()},
            "recent_closes": [310.0, 312.0, 314.0],
        }
        # write to cache under a few keys to simulate real app shapes
        self._price_cache[sym] = row
        self._price_cache[sym.lower()] = row
        return row


def test_rejects_implausible_cached_row_and_refreshes():
    core = DummyCore()
    sym = "QQQ"
    # Insert a poisoned cached value (very low far below prior closes)
    core._price_cache[sym] = {
        "ts": time.time(),
        "price": 18.0,
        "last_price": 18.0,
        # missing source_plausibility.last_block (simulates the observed null)
        "source_plausibility": {"last_block": None},
        # embed prior closes so the guard can compute a median
        "recent_closes": [310.0, 312.0, 314.0],
    }
    # Also mirror a market history entry
    core.portfolio["market_history"][sym] = {"closes": [310.0, 312.0, 314.0]}

    result = ensure_plausible_cached_price(core, sym)
    # The guard should have triggered a downloader refresh and returned a sane row
    assert result is not None
    # After refresh the cached price should be the downloader's 312.0
    assert float(result.get("price") or result.get("last_price")) == 312.0
    # And source_plausibility.last_block should now be present (refreshed by downloader)
    sp = result.get("source_plausibility") or {}
    assert sp.get("last_block") is not None


def test_returns_cached_if_plausibility_present():
    core = DummyCore()
    sym = "QQQ"
    core._price_cache[sym] = {
        "ts": time.time(),
        "price": 18.0,
        "last_price": 18.0,
        # This time plausibility is present, so the guard must not force a refresh
        "source_plausibility": {"last_block": time.time()},
        "recent_closes": [310.0, 312.0, 314.0],
    }
    result = ensure_plausible_cached_price(core, sym)
    # Because source_plausibility.last_block is present, the cached entry must be returned unchanged
    assert float(result.get("price")) == 18.0
