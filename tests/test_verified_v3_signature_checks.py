import pytest

from verified_v3_successor_epoch_migration import (
    PRICE_TOLERANCE,
    verify_successor_event,
    VerificationError,
)


def test_within_tolerance_and_matching_hash_passes():
    # exact hash match, tiny price delta <= PRICE_TOLERANCE
    event_hash = "deadbeefcafebabe"
    price_v3 = 100.0
    # choose a price within relative tolerance: delta = 5e-6 -> allowed +/- 0.0005%
    price_successor = price_v3 * (1.0 + PRICE_TOLERANCE * 0.9)

    assert verify_successor_event(event_hash, event_hash, price_v3, price_successor) is True


def test_price_outside_tolerance_fails_price_mismatch():
    event_hash = "deadbeefcafebabe"
    price_v3 = 50.0
    # pick a price that exceeds tolerance by a bit
    price_successor = price_v3 * (1.0 + PRICE_TOLERANCE * 1.2)

    with pytest.raises(VerificationError) as ctx:
        verify_successor_event(event_hash, event_hash, price_v3, price_successor)

    assert "price_mismatch" in str(ctx.value)


def test_hash_mismatch_fails_even_within_tolerance():
    expected_hash = "deadbeefcafebabe"
    actual_hash = "cafebabedeadbeef"
    price_v3 = 123.456
    price_successor = price_v3 * (1.0 + PRICE_TOLERANCE * 0.5)

    with pytest.raises(VerificationError) as ctx:
        verify_successor_event(expected_hash, actual_hash, price_v3, price_successor)

    assert "event_hash_mismatch" in str(ctx.value)
