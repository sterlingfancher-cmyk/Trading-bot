"""Verified-v3 successor epoch migration helpers.

This module provides a very small, focused compatibility comparator used by the
v3->v4 successor recovery validation logic. The repository's authoritative
safety rules require exact identity checks (event_hash/chain/row-order/etc.)
while allowing a bounded serialization tolerance for numeric price fields.

Design constraints (kept deliberately minimal):
- Event identity (event_hash) must match exactly to accept a candidate row.
- Quantity/share checks remain mandatory and strict (numeric equality after
  canonical float coercion).
- Price comparison tolerates only canonical 6-decimal serialization deltas
  (equivalent to round(value, 6)).
- No other invariant, authority, or lifecycle behavior is changed here.

This file is intentionally small and focused so the regression test can exercise
just the tolerant serialization comparison without touching any protected
persistence, lifecycle, or trade-authority codepaths.
"""
from __future__ import annotations

from typing import Any, Dict

__all__ = [
    "EventHashMismatch",
    "PriceMismatch",
    "SharesMismatch",
    "validate_v3_candidate_row",
]


class EventHashMismatch(ValueError):
    """Raised when event_hash does not match exactly.

    The safety model requires exact immutable signature equality. A tolerant
    price comparison is only applied if the event_hash is identical.
    """


class PriceMismatch(ValueError):
    """Raised when prices differ outside the allowed serialization tolerance."""


class SharesMismatch(ValueError):
    """Raised when the shares/quantity do not match exactly (after coercion).

    Quantity checks are kept strict because they materially change the
    successor economics and are forbidden to be relaxed here.
    """


def _to_float_or_none(value: Any) -> float | None:
    """Coerce a numeric-like value to float, or return None if not coercible."""
    try:
        if value is None or value == "":
            return None
        # Accept Decimal-like objects with 'as_tuple' or numpy scalars, etc.
        return float(value)
    except Exception:
        return None


def _prices_equal_canonical(a: Any, b: Any) -> bool:
    """Compare two numeric price values with the canonical 6-decimal
    serialization tolerance.

    The canonical ledger serializes prices using round(..., 6). To allow
    bounded serialization deltas (for example, differences in floating-point
    formatting or tiny binary rounding variations) we accept rows whose prices
    match after rounding both to 6 decimal places.
    """
    fa = _to_float_or_none(a)
    fb = _to_float_or_none(b)
    if fa is None or fb is None:
        return False
    return round(fa, 6) == round(fb, 6)


def _shares_equal_strict(a: Any, b: Any) -> bool:
    """Strict numeric equality for shares/quantity.

    We coerce to float and compare exact equality of the float values. The
    repository policy requires quantity checks remain mandatory and not
    relaxed. Using float equality here is consistent with how quantities are
    stored and compared elsewhere in the codebase; the test-suite covers this
    behavior.
    """
    fa = _to_float_or_none(a)
    fb = _to_float_or_none(b)
    if fa is None or fb is None:
        return False
    return fa == fb


def validate_v3_candidate_row(canonical_row: Dict[str, Any], candidate_row: Dict[str, Any]) -> bool:
    """Validate whether a v3 candidate execution row may be accepted for
    successor reconstruction.

    Rules (minimal, safety-first):
    - canonical_row['event_hash'] must match candidate_row['event_hash'] exactly.
      If it does not match, raise EventHashMismatch.
    - shares/quantity must match strictly (raise SharesMismatch on failure).
    - price comparison uses the canonical 6-decimal serialization tolerance.
      If price differs outside that tolerance, raise PriceMismatch.

    Returns True if all checks pass.
    """
    # Event hash identity: mandatory exact match
    ch = canonical_row.get("event_hash")
    ph = candidate_row.get("event_hash")
    if ch != ph:
        raise EventHashMismatch("event_hash mismatch (must match exactly)")

    # Shares/quantity: mandatory strict numeric match
    if not _shares_equal_strict(canonical_row.get("shares"), candidate_row.get("shares")):
        raise SharesMismatch("shares/quantity mismatch (strict equality required)")

    # Price: allow canonical 6-decimal serialization tolerance
    if not _prices_equal_canonical(canonical_row.get("price"), candidate_row.get("price")):
        raise PriceMismatch("price mismatch outside canonical 6-decimal serialization tolerance")

    return True
