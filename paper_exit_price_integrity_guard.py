from __future__ import annotations

import math
import statistics
import time
from typing import Any, Callable, Dict, List, Optional

VERSION = "paper-exit-price-integrity-guard-2026-08-18"


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _extract_closes(obj: Any) -> List[float]:
    """Try to extract a list of recent close prices from a provider return.

    The provider may return a list of dicts with keys like 'close' or 'price', a
    pandas.DataFrame-like object, or a bare list of floats. Be defensive.
    """
    out: List[float] = []
    if obj is None:
        return out
    # If it's a DataFrame-like object with a 'close' or 'Close' column
    try:
        # duck-typed DataFrame -> has columns and can yield values
        cols = getattr(obj, "columns", None)
        if cols is not None:
            for key in ("close", "Close", "price", "close_price"):
                if key in cols:
                    series = getattr(obj, "__getitem__", None)
                    try:
                        seq = obj[key]
                        # try to iterate
                        for v in seq:
                            try:
                                out.append(float(v))
                            except Exception:
                                continue
                        if out:
                            return out
                    except Exception:
                        pass
    except Exception:
        pass

    # If it's an iterable list/sequence
    if isinstance(obj, (list, tuple)):
        for item in obj:
            if isinstance(item, dict):
                for key in ("close", "Close", "price", "close_price"):
                    if key in item:
                        try:
                            out.append(float(item[key]))
                        except Exception:
                            pass
                        break
            else:
                # attempt to coerce scalars
                try:
                    out.append(float(item))
                except Exception:
                    pass
        return out

    # If it's a scalar numeric
    try:
        out.append(float(obj))
    except Exception:
        pass
    return out


def _mark_block(core: Any, symbol: str, reason: str) -> None:
    """Call core's marker if available, be best-effort.

    Requirement: tests expect _mark_source_block to be called with a cached-source reason.
    We'll attempt several attribute names to be robust to small naming differences.
    """
    for name in ("_mark_source_block", "mark_source_block", "_mark_block", "mark_block"):
        fn = getattr(core, name, None)
        if callable(fn):
            try:
                fn(symbol, reason)
            except TypeError:
                # some markers may expect (symbol, reason, extra)
                try:
                    fn(symbol, reason, {})
                except Exception:
                    pass
            except Exception:
                pass
            return


def _call_download_prices(core: Any, symbol: str) -> Optional[List[float]]:
    """Dynamically resolve and call the core.download_prices owner.

    This tries a few common invocation signatures used across the codebase/tests.
    On success returns a list of numeric closes (possibly empty). On any failure
    returns None so the caller can fail closed.
    """
    owner = getattr(core, "download_prices", None)
    if not callable(owner):
        return None
    candidates = []
    # Try a few call styles; tests will typically implement a simple signature
    # so one of these should succeed.
    try:
        # Preferred simple call: owner(symbol)
        raw = owner(symbol)
        closes = _extract_closes(raw)
        if closes:
            return closes
        candidates.append(closes)
    except TypeError:
        pass
    except Exception:
        # provider failed; treat as inability to validate
        return None

    try:
        # owner(symbol, limit=40)
        raw = owner(symbol, limit=40)
        closes = _extract_closes(raw)
        if closes:
            return closes
        candidates.append(closes)
    except TypeError:
        pass
    except Exception:
        return None

    try:
        # owner(symbol=symbol, lookback=40)
        raw = owner(symbol=symbol, lookback=40)
        closes = _extract_closes(raw)
        if closes:
            return closes
        candidates.append(closes)
    except TypeError:
        pass
    except Exception:
        return None

    try:
        # owner([symbol]) style
        raw = owner([symbol])
        closes = _extract_closes(raw)
        if closes:
            return closes
        candidates.append(closes)
    except TypeError:
        pass
    except Exception:
        return None

    # Nothing usable
    return None


def _is_catastrophic(candidate: float, median_anchor: float) -> bool:
    """Return True if candidate is outside the trusted 0.40x - 2.50x band.

    Preserves the policy from PR #56.
    """
    if median_anchor <= 0 or not math.isfinite(median_anchor) or not math.isfinite(candidate):
        return True
    low = 0.40 * median_anchor
    high = 2.50 * median_anchor
    return candidate <= low or candidate >= high


def _wrap_latest_price(core: Any) -> Callable[[str], Optional[float]]:
    """Wrap core.latest_price with an independent cached-price validator.

    Behavior summary (surgical/strict):
    - If the cache entry for symbol already contains validation provenance (we
      use 'validation' sub-dict), accept it locally and return the cached price.
    - If the cache entry exists but lacks validation, attempt to obtain recent
      same-symbol closes from core.download_prices. If unavailable or the
      validation fails, fail closed: call _mark_source_block(..., reason="cached-source-untrusted")
      and return None.
    - If validation passes, annotate the cache entry with a 'validation' dict
      that includes the anchor median and timestamp so subsequent hits can be
      validated locally without another provider call (preserving 60s cache).
    - If no cache entry exists, simply call the original latest_price and
      preserve its normal path (we do not weaken the existing entry-anchored
      exit guard).
    """

    orig_latest = getattr(core, "latest_price", None)

    def wrapped(symbol: str) -> Optional[float]:
        # If orig not present, can't proceed
        if not callable(orig_latest):
            return None

        # Defensive access to the production-shaped cache
        cache_root = getattr(core, "_price_cache", None)
        if not isinstance(cache_root, dict):
            # Fall back to original behavior
            try:
                return orig_latest(symbol)
            except Exception:
                return None

        data = cache_root.get("data") if isinstance(cache_root.get("data"), dict) else {}
        entry = data.get(symbol)

        # If there's no cached entry yet, defer to the original latest_price
        if not isinstance(entry, dict):
            try:
                return orig_latest(symbol)
            except Exception:
                return None

        # If entry already carries validation provenance, trust it locally
        validation = entry.get("validation")
        if isinstance(validation, dict):
            # Return the cached price; we assume the prior protected path wrote validation.
            try:
                return float(entry.get("price"))
            except Exception:
                return None

        # Legacy/unvalidated fresh cache entry. Validate before returning.
        try:
            candidate = float(entry.get("price"))
        except Exception:
            _mark_block(core, symbol, "cached-source-untrusted:bad-format")
            return None

        # Obtain independent recent same-symbol evidence
        closes = _call_download_prices(core, symbol)
        if closes is None or len(closes) == 0:
            # Can't validate -> fail closed per requirement
            _mark_block(core, symbol, "cached-source-untrusted:no-provider-evidence")
            return None

        # compute robust median anchor of the recent closes ignoring non-finite
        finite = [float(x) for x in closes if isinstance(x, (int, float)) and math.isfinite(float(x)) and float(x) > 0]
        if not finite:
            _mark_block(core, symbol, "cached-source-untrusted:no-finite-evidence")
            return None

        try:
            median_anchor = float(statistics.median(finite))
        except Exception:
            median_anchor = float(finite[len(finite) // 2]) if finite else 0.0

        if _is_catastrophic(candidate, median_anchor):
            # Poison detected. Mark and fail closed. Do not pass poisoned value downstream.
            _mark_block(core, symbol, "cached-source-untrusted:cached-poisoned")
            return None

        # Candidate appears plausible. Annotate cache entry with validation provenance
        try:
            entry["validation"] = {
                "median_anchor": median_anchor,
                "validated_at": int(time.time()),
                "source": "recent-bars-download",
            }
            # persist back to the shaped cache
            data[symbol] = entry
            cache_root["data"] = data
            # Return the cached price
            return candidate
        except Exception:
            # If we cannot write provenance, still prefer to fail closed rather than return unvalidated data
            _mark_block(core, symbol, "cached-source-untrusted:write-provenance-failed")
            return None

    return wrapped


# Expose the wrapper so tests/importers can apply it
__all__ = ["_wrap_latest_price", "VERSION"]
