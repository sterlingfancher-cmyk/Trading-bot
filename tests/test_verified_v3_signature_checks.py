import copy

import verified_v3_successor_epoch_migration as migration


def _row_from_expected(expected):
    row = copy.deepcopy(expected)
    row.pop("economic_disposition", None)
    return row


def test_price_serialization_delta_with_exact_event_hash_passes():
    expected = migration.EXPECTED_V3_ROWS[1]
    row = _row_from_expected(expected)
    row["price"] = float(expected["price"]) + 4e-6

    checks = migration._signature_checks(row, expected, int(expected["ledger_index"]))

    assert all(checks.values())


def test_price_delta_outside_bound_fails_price_only():
    expected = migration.EXPECTED_V3_ROWS[1]
    row = _row_from_expected(expected)
    row["price"] = float(expected["price"]) + 6e-6

    checks = migration._signature_checks(row, expected, int(expected["ledger_index"]))

    assert checks["price"] is False
    assert all(value for name, value in checks.items() if name != "price")


def test_event_hash_mismatch_fails_even_with_close_price():
    expected = migration.EXPECTED_V3_ROWS[2]
    row = _row_from_expected(expected)
    row["price"] = float(expected["price"]) + 4e-6
    row["event_hash"] = "0" * 64

    checks = migration._signature_checks(row, expected, int(expected["ledger_index"]))

    assert checks["price"] is True
    assert checks["event_hash"] is False
    assert all(value for name, value in checks.items() if name != "event_hash")
