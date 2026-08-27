import pytest

import verified_v3_successor_epoch_migration as v3m


def make_row(event_hash: str, price: float, shares: float) -> dict:
    return {"event_hash": event_hash, "price": price, "shares": shares}


def test_tolerant_price_with_exact_event_hash_passes():
    # Representative serialization delta: prices differ only within 6-decimal
    # rounding, event_hash and shares are identical -> should pass.
    canonical = make_row("90b22aad76074031906e0c6459dfa0bc", 13.0050000, 1.43651871)
    candidate = make_row("90b22aad76074031906e0c6459dfa0bc", 13.005000399999999, 1.43651871)

    assert v3m.validate_v3_candidate_row(canonical, candidate) is True


def test_price_outside_tolerance_fails_even_with_exact_event_hash():
    # Same event hash and shares, but price differs outside 6-decimal
    canonical = make_row("90b22aad76074031906e0c6459dfa0bc", 13.0050000, 1.43651871)
    candidate = make_row("90b22aad76074031906e0c6459dfa0bc", 13.006, 1.43651871)

    with pytest.raises(v3m.PriceMismatch):
        v3m.validate_v3_candidate_row(canonical, candidate)


def test_event_hash_mismatch_always_fails_even_within_tolerance():
    # Price is within tolerance but event_hash differs -> should fail with
    # EventHashMismatch regardless of price closeness.
    canonical = make_row("90b22aad76074031906e0c6459dfa0bc", 13.0050000, 1.43651871)
    candidate = make_row("SOME_OTHER_HASH_0000000000000000000000", 13.005000399999999, 1.43651871)

    with pytest.raises(v3m.EventHashMismatch):
        v3m.validate_v3_candidate_row(canonical, candidate)
