import verified_v3_successor_epoch_migration as mod


def _make_expected():
    return {
        "ledger_index": 10,
        "execution_id": "exec1",
        "accounting_epoch_id": mod.OLD_EPOCH_ID,
        "action": "exit",
        "symbol": "TST",
        "side": "long",
        "price": 73.475,
        "shares": 1.0,
        "event_hash": "abcd1234",
    }


def test_price_within_tolerance_accepted():
    expected = _make_expected()
    row = {
        "execution_id": "exec1",
        "accounting_epoch_id": mod.OLD_EPOCH_ID,
        "action": "exit",
        "symbol": "TST",
        "side": "long",
        "price": 73.474998,
        "event_hash": "abcd1234",
        "shares": 1.0,
    }
    checks = mod._signature_checks(row, expected, 10)
    assert checks["price"] is True
    assert checks["event_hash"] is True
    assert checks["execution_id"] is True


def test_materially_different_price_rejected():
    expected = _make_expected()
    row = {
        "execution_id": "exec1",
        "accounting_epoch_id": mod.OLD_EPOCH_ID,
        "action": "exit",
        "symbol": "TST",
        "side": "long",
        "price": 73.48,
        "event_hash": "abcd1234",
        "shares": 1.0,
    }
    checks = mod._signature_checks(row, expected, 10)
    assert checks["price"] is False


def test_event_hash_exact_match_required():
    expected = _make_expected()
    row = {
        "execution_id": "exec1",
        "accounting_epoch_id": mod.OLD_EPOCH_ID,
        "action": "exit",
        "symbol": "TST",
        "side": "long",
        "price": 73.474998,
        "event_hash": "DIFFERENT",
        "shares": 1.0,
    }
    checks = mod._signature_checks(row, expected, 10)
    assert checks["price"] is True
    # event_hash must be exact; even though price is close, event_hash mismatch stays fail-closed
    assert checks["event_hash"] is False
