from __future__ import annotations

import math
import statistics
import time
from typing import Any, Dict, List, Optional

# Small, surgical helper to ensure we do not return a cached terminal price
# that lacks source plausibility metadata without independently plausibility-
# checking it first. This module purposely avoids changing any strategy,
# sizing, risk-thresholds, ledger, or live authority. It is paper-only logic
# to validate a cached price when the cache entry's source_plausibility is
# missing (null).
#
# Design notes (minimal, defensive):
# - Resolve the likely cache shapes used across the app: _price_cache, price_cache.
# - Respect a configurable TTL from the hosting core when possible.
# - If a cached entry is fresh but has a null/missing source_plausibility.last_block,
#   attempt an independent plausibility test using nearest available same-symbol
#   recent closes (from the cache entry itself or core.portfolio market history).
# - If an independent plausibility check is impossible (no prior closes), fall
#   back to refreshing via the host core.download_prices() when available.
# - Only perform the extra checks when the cached row is fresh (within TTL).
# - Do not mutate risk controls, execution, or ledger; only update/return the
#   market price row as provided/produced by the host core owner.

# Thresholds must match the repository's production source plausibility policy:
_MIN_RATIO = 0.40
_MAX_RATIO = 2.50


def _now_ts() -> float:
    return time.time()


def _get_price_cache_owner(core: Any) -> Optional[Dict[str, Any]]:
    """Try common attribute names for the in-memory price cache.
    Returns a mapping object or None if none found.
    """
    for name in ("_price_cache", "price_cache", "_prices_cache"):
        cache = getattr(core, name, None)
        if isinstance(cache, dict):
            return cache
    return None


def _fresh_enough(entry_ts: float, ttl: int) -> bool:
    try:
        return ( _now_ts() - float(entry_ts) ) <= float(ttl)
    except Exception:
        return False


def _median_of_closes(candidate: Any) -> Optional[float]:
    # candidate may be a list, tuple or dict with 'closes' or 'recent_closes'.
    vals: List[float] = []
    try:
        if isinstance(candidate, dict):
            for key in ("recent_closes", "closes", "prior_closes", "history"):
                arr = candidate.get(key)
                if isinstance(arr, (list, tuple)) and arr:
                    for v in arr:
                        try:
                            f = float(v)
                            if math.isfinite(f) and f > 0:
                                vals.append(f)
                        except Exception:
                            continue
        elif isinstance(candidate, (list, tuple)):
            for v in candidate:
                try:
                    f = float(v)
                    if math.isfinite(f) and f > 0:
                        vals.append(f)
                except Exception:
                    continue
    except Exception:
        return None
    if not vals:
        return None
    try:
        return float(statistics.median(vals))
    except Exception:
        try:
            return float(sum(vals) / len(vals))
        except Exception:
            return None


def _price_from_entry(entry: Any) -> Optional[float]:
    if not isinstance(entry, dict):
        return None
    for key in ("price", "last_price", "mark", "current_price", "close"):
        try:
            v = entry.get(key)
            if v is None:
                continue
            f = float(v)
            if math.isfinite(f) and f > 0:
                return f
        except Exception:
            continue
    return None


def ensure_plausible_cached_price(core: Any, symbol: str, ttl: Optional[int] = None) -> Dict[str, Any]:
    """Return a market-price row for symbol, preferring a fresh cached value
    but ensuring that if the cache entry lacks source_plausibility.last_block we
    independently validate it before returning.

    Behavior (conservative and minimal):
    - If no cache present for the symbol, call core.download_prices(symbol)
      if available (to let the host populate cache) and return whatever the
      host produced.
    - If a cached entry is present and fresh (within ttl) and source_plausibility
      is present with a non-null last_block: return the cached entry unchanged.
    - If a cached entry is present and fresh but source_plausibility.last_block is
      missing/null: attempt to compute a recent median from the entry itself
      (recent_closes) or core.portfolio market history and validate the cached
      price against [_MIN_RATIO, _MAX_RATIO]. If implausible, attempt to force
      a refresh by calling core.download_prices(symbol) if available. Return
      the best available row after these steps.

    This helper intentionally does not modify risk controls or ledger and is
    intended for use by exit/marking/quote-return paths where a poisoned cache
    must be double-checked before use.
    """
    # resolve TTL: prefer explicit passed value, else prefer core.MARKET_CACHE_TTL if present,
    # otherwise default to 60 seconds to preserve the intent of a short cache for terminal quotes.
    if ttl is None:
        ttl = getattr(core, "MARKET_CACHE_TTL", None)
        try:
            ttl = int(ttl) if ttl is not None else 60
        except Exception:
            ttl = 60
    cache = _get_price_cache_owner(core)
    symbol_key = str(symbol).upper()

    def _attempt_refresh() -> Optional[Dict[str, Any]]:
        # Best-effort: call the host's download_prices to refresh cache. This is
        # a conservative non-invasive approach — we do not mutate anything else.
        try:
            downloader = None
            # dynamic resolution of the downloader (keeps with PR #56 approach)
            for candidate in ("download_prices", "download_price", "fetch_prices", "fetch_price"):
                fn = getattr(core, candidate, None)
                if callable(fn):
                    downloader = fn
                    break
            if downloader is None:
                return None
            # If the downloader accepts symbol argument, pass it. Otherwise call without args
            try:
                # prefer symbol-specific call
                result = downloader(symbol)
            except TypeError:
                try:
                    result = downloader([symbol])
                except TypeError:
                    result = downloader()
            # If the downloader returns a mapping for the symbol, prefer it; else fall-through
            if isinstance(result, dict):
                # if downloader returned a dict keyed by symbol
                maybe = result.get(symbol_key) or result.get(symbol.upper()) or result.get(symbol.lower())
                if isinstance(maybe, dict):
                    return maybe
            # otherwise, let caller inspect the cache after downloader returned
            return None
        except Exception:
            return None

    # Helper to read an entry from cache safely
    def _read_cache_entry() -> Optional[Dict[str, Any]]:
        try:
            if cache is None:
                return None
            # Some caches may store keys as upper or lower; try a few variants
            for key in (symbol_key, symbol_key.upper(), symbol_key.lower(), symbol):
                if key in cache:
                    return cache[key]
            return None
        except Exception:
            return None

    entry = _read_cache_entry()
    # If no cached entry, attempt to let the host provide one and return whatever we get.
    if entry is None:
        _attempt_refresh()
        entry = _read_cache_entry() or {}
        return entry

    # If cache is stale, let the caller continue with a fresh host fetch (do nothing here)
    entry_ts = entry.get("ts") or entry.get("time") or entry.get("timestamp")
    try:
        entry_ts = float(entry_ts) if entry_ts is not None else None
    except Exception:
        entry_ts = None

    if entry_ts is None or not _fresh_enough(entry_ts, ttl):
        # Not fresh enough; attempt to refresh (best-effort) and return updated row
        _attempt_refresh()
        refreshed = _read_cache_entry()
        return refreshed or entry

    # At this point we have a fresh cached entry. If source_plausibility exists
    # and last_block is present, return the cached entry unchanged.
    sp = None
    try:
        sp = entry.get("source_plausibility") or entry.get("plausibility") or {}
    except Exception:
        sp = {}

    last_block = None
    try:
        last_block = sp.get("last_block") if isinstance(sp, dict) else None
    except Exception:
        last_block = None

    if last_block:
        return entry

    # Missing last_block: independently compute a recent-median from available sources
    median_candidates: List[Any] = []
    # 1) candidate closes embedded in the cached entry
    for key in ("recent_closes", "closes", "prior_closes", "history"):
        if isinstance(entry.get(key), (list, tuple)):
            median_candidates.append(entry.get(key))
    # 2) any market-history available on core.portfolio (best-effort)
    try:
        pf = getattr(core, "portfolio", {}) or {}
        mh = None
        # many shapes exist; try core.portfolio["market_history"][symbol]["closes"] etc.
        if isinstance(pf, dict):
            mroot = pf.get("market_history") or pf.get("market") or {}
            if isinstance(mroot, dict):
                sym_block = mroot.get(symbol_key) or mroot.get(symbol_key.upper()) or mroot.get(symbol_key.lower())
                if isinstance(sym_block, dict):
                    for key in ("closes", "recent_closes", "prior_closes"):
                        arr = sym_block.get(key)
                        if isinstance(arr, (list, tuple)) and arr:
                            median_candidates.append(arr)
                            break
            # fallback: positions may have last_price/entry price
            pos = pf.get("positions") or {}
            if isinstance(pos, dict):
                prow = pos.get(symbol_key) or pos.get(symbol_key.upper()) or pos.get(symbol_key.lower())
                if isinstance(prow, dict):
                    for fld in ("last_price", "current_price", "entry_price", "avg_price"):
                        v = prow.get(fld)
                        if v:
                            median_candidates.append([v])
                            break
    except Exception:
        pass

    median_val: Optional[float] = None
    for cand in median_candidates:
        m = _median_of_closes(cand)
        if m:
            median_val = m
            break

    cached_price = _price_from_entry(entry)
    if cached_price is None:
        # No numeric price in cache; attempt host refresh
        _attempt_refresh()
        refreshed = _read_cache_entry()
        return refreshed or entry

    # If we have a median to compare: apply the established source plausibility ratios
    if median_val is not None and median_val > 0:
        ratio = cached_price / float(median_val)
        if ratio < _MIN_RATIO or ratio > _MAX_RATIO:
            # Implausible. Attempt to force a host refresh and return that if available.
            _attempt_refresh()
            refreshed = _read_cache_entry()
            # If refresh yields a plausible value, return it; otherwise return the refreshed row
            if refreshed is not None:
                new_price = _price_from_entry(refreshed)
                if new_price is not None and median_val > 0:
                    new_ratio = new_price / float(median_val)
                    if _MIN_RATIO <= new_ratio <= _MAX_RATIO:
                        return refreshed
                return refreshed
            # If refresh failed, return original entry but leave a conservative diagnostic
            return entry
        # otherwise cached price appears plausible; return it unchanged
        return entry

    # No median available to validate against: best-effort call to host downloader to refresh
    _attempt_refresh()
    refreshed = _read_cache_entry()
    return refreshed or entry
