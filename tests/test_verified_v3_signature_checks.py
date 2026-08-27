import copy

import verified_v3_successor_epoch_migration as mig


def _make_row_from_expected(expected: dict) -> dict:
    # make a shallow copy usable as a ledger row
    r = dict(expected)
    # signature checks expect some fields present as in ledger rows
    # remove helper-only keys that are not in ledger rows
    r.pop("economic_disposition", None)
    return r


def test_price_within_tolerance_all_checks_true():
    expected = mig.EXPECTED_V3_ROWS[1]
    row = _make_row_from_expected(expected)
    # change price by exactly the tolerance (should be accepted)
    price_mod = float(expected["price"]) + mig.PRICE_TOLERANCE
    row["price"] = price_mod
    index = int(expected["ledger_index"])
    checks = mig._signature_checks(row, expected, index)
    # all checks should be True
    assert all(checks.values()), f"Expected all True but got {checks}"


def test_price_exceeds_tolerance_price_false_only():
    expected = mig.EXPECTED_V3_ROWS[1]
    row = _make_row_from_expected(expected)
    # change price by slightly more than tolerance
    price_mod = float(expected["price"]) + (mig.PRICE_TOLERANCE * 1.2 + 1e-12)
    row["price"] = price_mod
    index = int(expected["ledger_index"])
    checks = mig._signature_checks(row, expected, index)
    # price should be False, other relevant checks True
    assert checks["price"] is False
    # ensure non-price checks that are compared remain True
    for k, v in checks.items():
        if k == "price":
            continue
        assert v is True, f"Expected {k} True but was {v} in {checks}"


def test_event_hash_mismatch_event_hash_false_only():
    expected = mig.EXPECTED_V3_ROWS[1]
    row = _make_row_from_expected(expected)
    # keep price within tolerance
    row["price"] = float(expected["price"]) + (mig.PRICE_TOLERANCE * 0.5)
    # mutate event_hash
    row["event_hash"] = "deadbeef" + (row.get("event_hash") or "")
    index = int(expected["ledger_index"])
    checks = mig._signature_checks(row, expected, index)
    # event_hash should be False, and price True
    assert checks.get("event_hash") is False
    assert checks.get("price") is True
    # other checks True
    for k in checks:
        if k in {"event_hash", "price"}:
            continue
        assert checks[k] is True, f"Expected {k} True but was {checks[k]}"
