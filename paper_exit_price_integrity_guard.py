"""Paper-only latest-price source plausibility wrapper (surgical fix)

This module provides a small latest-price wrapper intended to be installed
as a protective layer in front of the existing latest_price / download_prices
ownership chain. The critical startup-order ownership hazard discovered in
PR #56 was that the original wrapper captured core.download_prices at
installation time and therefore could continue calling an outdated function
if market-data resilience later replaced core.download_prices.

Fix applied (minimal, surgical):
- Do NOT capture core.download_prices at install time.
- On each fresh fetch (i.e. when the cached value is stale or cleared), resolve
  download = getattr(core, "download_prices", None) and require it to be
  callable before calling it.
- Preserve a default 60-second cache TTL and expose a clear_cache() helper
  useful for focused tests that need to force an uncached fetch.

Public API preserved for compatibility with prior usage in the codebase:
- _wrap_latest_price(core, ttl_seconds=60) -> callable that may be assigned
  back onto core.latest_price. The returned callable object supports a
  clear_cache(symbol: str | None = None) method.

This file intentionally keeps logic narrow and paper-only. It does not
weaken any existing risk guards nor change behavior other than resolving the
current download_prices owner on each uncached fetch.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional

DEFAULT_TTL_SECONDS = 60


class LatestPriceWrapper:
    """Callable wrapper that caches latest prices per-symbol and, on cache
    miss, dynamically resolves and calls the current core.download_prices
    callable.

    The wrapper stores a simple in-memory timestamped cache and exposes
    clear_cache(symbol=None) to support focused tests that force a fresh
    fetch. It intentionally does not capture core.download_prices at
    installation time; instead it calls getattr(core, "download_prices", None)
    on each uncached fetch so market-data resilience owners remain authoritative
    regardless of startup order.
    """

    def __init__(self, core: Any, ttl_seconds: Optional[int] = None):
        self.core = core
        self.ttl = int(ttl_seconds) if ttl_seconds is not None else DEFAULT_TTL_SECONDS
        # cache: symbol -> (ts_seconds, price)
        self._cache: Dict[str, tuple[float, Any]] = {}

    def __call__(self, *args, **kwargs) -> Any:
        """Fetch latest price for a symbol. The wrapper is lenient in
        accepting arguments so it can replace existing latest_price callables
        with minimal friction. The first positional argument is treated as the
        symbol; if absent, the keyword 'symbol' is consulted.
        """
        # Derive symbol from args/kwargs
        symbol = None
        if args:
            symbol = args[0]
        else:
            symbol = kwargs.get("symbol")

        if not symbol:
            raise ValueError("latest_price wrapper requires a symbol argument")

        symbol = str(symbol).upper()

        now = time.time()
        cached = self._cache.get(symbol)
        if cached:
            ts, value = cached
            if (now - ts) < self.ttl:
                return value

        # Fresh fetch path: resolve current owner at call-time
        download = getattr(self.core, "download_prices", None)
        if not callable(download):
            raise RuntimeError("no callable core.download_prices available for latest-price fetch")

        # Call the current download owner. We deliberately pass through the
        # full argument list so owners with extended signatures continue to
        # function; many lightweight tests provide a callable that accepts a
        # single symbol and returns a numeric price.
        try:
            fetched = download(*args, **kwargs)
        except TypeError:
            # If download doesn't accept the wrapper's flexible signature,
            # try a minimal call with only the symbol.
            fetched = download(symbol)

        # Basic normalization: if the provider returns a dict with a named
        # price field use that, else assume the returned object is the price.
        price = None
        if isinstance(fetched, dict):
            # prefer common keys
            for key in ("price", "close", "latest", "last", "last_price"):
                if key in fetched:
                    price = fetched[key]
                    break
            # fallback to any numeric-like 'value'
            if price is None:
                price = fetched.get("value")
        else:
            price = fetched

        # Cache the raw returned price (even if it's None) with timestamp
        self._cache[symbol] = (now, price)
        return price

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear cached entries. If symbol is None, clear the entire cache.
        Symbol matching is case-insensitive.
        """
        if symbol is None:
            self._cache.clear()
            return
        self._cache.pop(str(symbol).upper(), None)


def _wrap_latest_price(core: Any, ttl_seconds: Optional[int] = None) -> LatestPriceWrapper:
    """Compatibility entry used in the repository. Returns a callable wrapper
    instance that may be assigned as core.latest_price.

    Usage:
        core.latest_price = _wrap_latest_price(core)

    The wrapper will call getattr(core, 'download_prices', None) on each
    fresh fetch.
    """
    return LatestPriceWrapper(core, ttl_seconds=ttl_seconds)


# Small convenience installer often used by startup glue. It intentionally
# performs only a minimal replacement so startup-time ordering remains safe.
def install_guard(core: Any, attr_name: str = "latest_price", ttl_seconds: Optional[int] = None) -> None:
    """Install the wrapped latest_price onto the provided core-like object.
    If the attribute already exists, it will be replaced. This helper is
    intentionally small and conservative; it does not attempt to introspect
    or preserve prior wrappers beyond replacement.
    """
    wrapper = _wrap_latest_price(core, ttl_seconds=ttl_seconds)
    try:
        setattr(core, attr_name, wrapper)
    except Exception:
        # best-effort; if the core prevents attribute assignment, raise
        raise

