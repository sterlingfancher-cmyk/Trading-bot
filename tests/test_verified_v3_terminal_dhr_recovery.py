import copy

import verified_v3_successor_epoch_migration as vm


class DummyCore:
    def __init__(self, portfolio):
        self.portfolio = portfolio


def _base_portfolio():
    # minimal portfolio scaffolding for alias-shape checks only
    return {
        "positions": {},
        "trades": [],
        "cash": vm.EXPECTED_BASELINE_CASH,
        "equity": vm.EXPECTED_BASELINE_EQUITY,
        "risk_controls": {"halted": True, "halt_reason": "canonical execution lifecycle integrity halt"},
        "paper_accounting_epoch": {"id": vm.OLD_EPOCH_ID, "prior_epoch_id": vm.PRIOR_EPOCH_ID, "historical_evidence_archived": True, "validation_hold": True, "verified_snapshot_baseline": {"verified": True, "cash": vm.EXPECTED_BASELINE_CASH, "equity": vm.EXPECTED_BASELINE_EQUITY, "positions": {}}},
    }


def test_passing_fixture_contains_both_aliases_exact_shape():
    pf = _base_portfolio()
    # positions exactly DHR + SLS
    pf["positions"] = {
        "DHR": {
            # qty alias must match EXPECTED_BASELINE_DHR_QTY exactly within tolerance
            "qty": vm.EXPECTED_BASELINE_DHR_QTY,
            # shares alias must match EXPECTED_DHR_REMAINDER exactly within tolerance
            "shares": vm.EXPECTED_DHR_REMAINDER,
            "side": "long",
            "last_price": 216.96,
        },
        "SLS": {"qty": vm.EXPECTED_BASELINE_SLS_QTY, "side": "long", "last_price": 13.62},
    }
    core = DummyCore(pf)
    checks = vm._terminal_dhr_alias_checks(pf)
    assert checks["symbols_exact"] is True
    assert checks["side_exact"] is True
    assert checks["qty_alias_exact"] is True
    assert checks["shares_alias_exact"] is True
    assert checks["exact"] is True


def test_fails_when_qty_alias_wrong_but_shares_ok():
    pf = _base_portfolio()
    pf["positions"] = {
        "DHR": {
            # incorrect qty (not baseline)
            "qty": vm.EXPECTED_BASELINE_DHR_QTY + (vm.QTY_TOLERANCE * 100),
            "shares": vm.EXPECTED_DHR_REMAINDER,
            "side": "long",
            "last_price": 216.96,
        },
        "SLS": {"qty": vm.EXPECTED_BASELINE_SLS_QTY, "side": "long", "last_price": 13.62},
    }
    checks = vm._terminal_dhr_alias_checks(pf)
    assert checks["qty_alias_exact"] is False
    # shares remains correct
    assert checks["shares_alias_exact"] is True
    assert checks["exact"] is False


def test_fails_when_shares_alias_wrong_but_qty_ok():
    pf = _base_portfolio()
    pf["positions"] = {
        "DHR": {
            "qty": vm.EXPECTED_BASELINE_DHR_QTY,
            # incorrect shares (not remainder)
            "shares": vm.EXPECTED_DHR_REMAINDER + (vm.QTY_TOLERANCE * 100),
            "side": "long",
            "last_price": 216.96,
        },
        "SLS": {"qty": vm.EXPECTED_BASELINE_SLS_QTY, "side": "long", "last_price": 13.62},
    }
    checks = vm._terminal_dhr_alias_checks(pf)
    assert checks["qty_alias_exact"] is True
    assert checks["shares_alias_exact"] is False
    assert checks["exact"] is False


def test_relaxed_both_remainder_shape_fails_closed():
    # Legacy bug: earlier verifier accepted qty FALLBACK to shares (both remainder).
    # Now we require qty == EXPECTED_BASELINE_DHR_QTY and shares == EXPECTED_DHR_REMAINDER.
    pf = _base_portfolio()
    pf["positions"] = {
        "DHR": {
            # both fields set to the remainder (relaxed shape) -> should fail
            "qty": vm.EXPECTED_DHR_REMAINDER,
            "shares": vm.EXPECTED_DHR_REMAINDER,
            "side": "long",
            "last_price": 216.96,
        },
        "SLS": {"qty": vm.EXPECTED_BASELINE_SLS_QTY, "side": "long", "last_price": 13.62},
    }
    checks = vm._terminal_dhr_alias_checks(pf)
    # qty alias must not accept the remainder; it should compare to the baseline qty
    assert checks["qty_alias_exact"] is False
    # shares alias equals remainder so that one would be True
    assert checks["shares_alias_exact"] is True
    # overall exact must be False because qty-alias isn't correct
    assert checks["exact"] is False
