import copy

import pytest

from verified_v3_successor_epoch_migration import (
    _signature_checks,
    EXPECTED_V3_ROWS,
)


def make_base_row(expected):
    # Build a row that matches everything except price and event_hash as needed
    return {
        "execution_id": expected["execution_id"],
        "accounting_epoch_id": expected["accounting_epoch_id"],
        "action": expected["action"],
        "symbol": expected["symbol"],
        "side": expected["side"],
        "shares": expected.get("shares"),
    }


def test_price_within_tolerance_and_exact_event_hash_passes():
    expected = EXPECTED_V3_ROWS[2]
    idx = int(expected["ledger_index"])
    base = make_base_row(expected)
    # Price delta exactly equal to tolerance (5e-6) should pass
    delta = 5e-6
    base_price = float(expected["price"]) + delta
    row = copy.deepcopy(base)
    row["price"] = base_price
    row["event_hash"] = expected["event_hash"]

    checks = _signature_checks(row, expected, idx)
    # all checks should be True when within tolerance and hash matches
    assert all(checks.values()), f"Expected all True, got: {checks}"


def test_price_exceeding_tolerance_fails_price_check():
    expected = EXPECTED_V3_ROWS[2]
    idx = int(expected["ledger_index"])
    base = make_base_row(expected)
    # Price delta just over tolerance should fail the price check
    delta = 6e-6
    row = copy.deepcopy(base)
    row["price"] = float(expected["price"]) + delta
    row["event_hash"] = expected["event_hash"]

    checks = _signature_checks(row, expected, idx)
    assert checks["price"] is False
    # Other identity checks should still be True
    assert checks["execution_id"] is True
    assert checks["event_hash"] is True


def test_event_hash_mismatch_fails_even_when_price_within_tolerance():
    expected = EXPECTED_V3_ROWS[2]
    idx = int(expected["ledger_index"])
    base = make_base_row(expected)
    # Price within tolerance
    row = copy.deepcopy(base)
    row["price"] = float(expected["price"]) + 1e-6
    row["event_hash"] = "mismatched_event_hash_value"

    checks = _signature_checks(row, expected, idx)
    assert checks["price"] is True
    assert checks["event_hash"] is False
