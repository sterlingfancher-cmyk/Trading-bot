# Verified v3 -> v4 successor epoch migration helpers
# Minimal, focused utilities for deterministic successor verification.
# This module is intentionally small and read-only: it performs signature
# and price-tolerance checks used by the deterministic migration tests.
# Safety: no live trading, no ledger mutation, no authority changes here.

VERSION = "verified-v3-successor-migration-2026-08-27-v1"

# Tolerance for allowable proportional price delta between the verified v3
# evidence price and the reconstructed successor price during deterministic
# successor recovery validation. This value was carefully chosen to be
# permissive enough for tiny rounding or representation differences while
# remaining small to avoid meaningful economic divergence.
PRICE_TOLERANCE = 5e-6


def _rel_delta(a: float, b: float) -> float:
    """Return symmetric relative delta between a and b.

    Uses max(|a|, |b|, 1.0) as the denominator to avoid division by tiny
    values; callers here operate on positive market prices so the risk is
    minimal. The result is non-negative.
    """
    try:
        na = float(abs(a))
        nb = float(abs(b))
    except Exception:
        return float("inf")
    denom = max(na, nb, 1.0)
    return abs(na - nb) / denom


class VerificationError(Exception):
    """Raised when a verification step fails."""


def verify_successor_event(event_hash_expected: str, event_hash_actual: str, price_v3: float, price_successor: float) -> bool:
    """Verify that a successor reconstruction matches the verified v3 evidence.

    Checks performed (all must pass):
    - event hash exact-match equality (byte-exact string equality)
    - price matching within the configured PRICE_TOLERANCE (relative delta)

    Returns True on success. Raises VerificationError with a short message on
    first failure.
    """
    if not (isinstance(event_hash_expected, str) and isinstance(event_hash_actual, str)):
        raise VerificationError("event_hash_type_mismatch")

    if event_hash_expected != event_hash_actual:
        # event hash must match exactly; a mismatch indicates different
        # canonical execution or tampering and must fail even if the price is close.
        raise VerificationError("event_hash_mismatch")

    try:
        a = float(price_v3)
        b = float(price_successor)
    except Exception:
        raise VerificationError("price_not_numeric")

    delta = _rel_delta(a, b)
    if delta <= PRICE_TOLERANCE:
        return True
    raise VerificationError(f"price_mismatch:delta={delta}")
