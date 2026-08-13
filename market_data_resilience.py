from __future__ import annotations

import time
import math
import numpy as np
from typing import Any, Iterable

VERSION = "market-data-resilience-terminal-plausibility-2026-08-13-v1"
# Robust recent-bar evidence windows
_PRIOR_BARS_MIN = 20         # require at least this many prior bars to be strict
_PRIOR_BARS_CAP = 300        # use at most this many prior bars to compute anchor
_LOW_RATIO = 0.40            # if last/anchor < LOW_RATIO => reject
_HIGH_RATIO = 2.50           # if last/anchor > HIGH_RATIO => reject
_DEFAULT_TTL = 60            # fallback TTL seconds when core.MARKET_CACHE_TTL not available


def _iterable_of_numbers(obj: Any) -> list[float]:
    """Normalize common download_prices return shapes to a plain list of floats.

    Accepts objects like:
    - dict-like with 'Close' key and list/iterable
    - objects with attribute 'Close' (pandas DataFrame/Series) that are indexable
    - plain list/tuple/ndarray of numeric values
    Returns list[float] (may contain math.nan if values are missing)
    """
    if obj is None:
        return []
    # dict-like with 'Close'
    try:
        if isinstance(obj, dict) and "Close" in obj:
            vals = obj.get("Close")
            return [float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else math.nan for x in list(vals or [])]
    except Exception:
        pass
    # pandas-like: has a column/attribute 'Close'
    try:
        close = getattr(obj, "Close", None)
        if close is not None:
            # pandas Series or array-like
            return [float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else math.nan for x in list(close)]
    except Exception:
        pass
    # sequence/iterable
    try:
        if isinstance(obj, (list, tuple)):
            return [float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else math.nan for x in list(obj)]
    except Exception:
        pass
    # last-ditch: try to treat as indexable container (e.g., pandas DataFrame rows of close values)
    try:
        # if obj["Close"] works
        vals = obj["Close"]
        return [float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else math.nan for x in list(vals or [])]
    except Exception:
        pass
    return []


def _median_anchor(prior: list[float]) -> float | None:
    arr = [v for v in prior if isinstance(v, (int, float)) and not math.isnan(v) and v > 0]
    if not arr:
        return None
    return float(np.median(np.array(arr[-_PRIOR_BARS_CAP:], dtype=float)))


def install(core: Any) -> None:
    """Install runtime wrapper into the application's latest_price flow.

    This wrapper provides source-level terminal-bar plausibility validation using
    same-symbol recent-bar evidence. It is intentionally conservative:
    - If there are insufficient prior bars (< _PRIOR_BARS_MIN), the terminal bar
      is accepted (to avoid false positives on sparse history).
    - If an anchor (median of recent prior closes) is available and the terminal
      close deviates beyond configured ratios, the terminal bar is rejected and
      latest_price will return None (and will not cache an implausible terminal price).

    The wrapper is idempotent and safe: it only replaces core.latest_price and
    keeps a per-symbol short-lived cache (TTL) that mirrors the previous
    observed behavior (default 60s). It never modifies account, risk, or
    execution semantics.
    """
    # Idempotent guard
    if getattr(core, "_terminal_plausibility_installed", False):
        return
    setattr(core, "_terminal_plausibility_installed", True)

    orig_download = getattr(core, "download_prices", None)
    # Keep a simple cache separate from other app caches to avoid assumptions.
    cache = {}
    setattr(core, "_plausible_price_cache", cache)

    # determine TTL
    try:
        ttl = int(getattr(core, "MARKET_CACHE_TTL", _DEFAULT_TTL))
    except Exception:
        ttl = _DEFAULT_TTL

    def _is_cache_fresh(entry: dict) -> bool:
        if not entry:
            return False
        ts = entry.get("ts", 0)
        return (time.time() - ts) < ttl

    # Build a small helper to fetch historical closes using existing download_prices
    def _fetch_closes(symbol: str) -> list[float]:
        if orig_download is None:
            return []
        try:
            # prefer to call with threads=False if supported (most wrappers in this repo use it)
            try:
                result = orig_download(symbol, threads=False)
            except TypeError:
                result = orig_download(symbol)
            return _iterable_of_numbers(result)
        except Exception:
            return []

    # Replace latest_price on the core app
    orig_latest = getattr(core, "latest_price", None)

    def _latest_price_wrapped(symbol: str) -> float | None:
        key = (str(symbol or "").upper().strip())
        if not key:
            return None
        # Return fresh cache if present
        entry = cache.get(key)
        if entry and _is_cache_fresh(entry):
            return entry.get("price")
        # Try to obtain recent closes and validate terminal bar
        closes = _fetch_closes(key)
        if not closes:
            # No evidence available. Fall back to original latest_price if present,
            # otherwise None.
            if callable(orig_latest):
                try:
                    val = orig_latest(key)
                    if val is None:
                        return None
                    # cache only if positive finite
                    if isinstance(val, (int, float)) and not math.isnan(val) and val > 0:
                        cache[key] = {"price": float(val), "ts": time.time()}
                        return float(val)
                    return None
                except Exception:
                    return None
            return None
        last = closes[-1]
        if last is None or (isinstance(last, float) and math.isnan(last)) or last <= 0:
            return None
        prior = closes[:-1]
        # If insufficient prior evidence, accept terminal bar to avoid false positives
        if len([v for v in prior if isinstance(v, (int, float)) and not math.isnan(v)]) < _PRIOR_BARS_MIN:
            cache[key] = {"price": float(last), "ts": time.time()}
            return float(last)
        anchor = _median_anchor(prior)
        if anchor is None or anchor <= 0:
            cache[key] = {"price": float(last), "ts": time.time()}
            return float(last)
        ratio = float(last) / float(anchor)
        if ratio < _LOW_RATIO or ratio > _HIGH_RATIO:
            # Implausible terminal bar — do not cache, return None so downstream
            # protection (exit price integrity guard etc.) cannot see this bad tick.
            return None
        # Plausible: cache and return
        cache[key] = {"price": float(last), "ts": time.time()}
        return float(last)

    setattr(core, "latest_price", _latest_price_wrapped)

    # make cache accessible for diagnostics
    setattr(core, "_plausible_price_cache_ttl", ttl)
    setattr(core, "_plausible_price_cache_installed_at", time.time())
