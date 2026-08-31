import copy

from verified_v3_successor_epoch_migration import (
    canonical_only_terminal_dhr_state_shape_exact,
    EXPECTED_BASELINE_DHR_QTY,
    EXPECTED_DHR_REMAINDER,
    EXPECTED_BASELINE_SLS_QTY,
    QTY_TOLERANCE,
)


def _baseline_portfolio():
    # Build the minimal expected portfolio shape that the verifier expects.
    return {
        "paper_accounting_epoch": {
            "verified_snapshot_baseline": {
                "verified": True,
                "positions": {
                    "DHR": {
                        "side": "long",
                        # both aliases present and exact within tolerance
                        "qty": EXPECTED_BASELINE_DHR_QTY,
                        "shares": EXPECTED_DHR_REMAINDER,
                    },
                    "SLS": {
                        "side": "long",
                        # SLS quantity may be under either alias; we'll use 'qty' here
                        "qty": EXPECTED_BASELINE_SLS_QTY,
                    },
                },
            }
        }
    }


def test_passes_with_exact_dual_alias_shape():
    pf = _baseline_portfolio()
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf)
    assert ok is True
    assert payload.get("status") == "ok"
    assert abs(payload.get("dhr_qty") - EXPECTED_BASELINE_DHR_QTY) <= QTY_TOLERANCE
    assert abs(payload.get("dhr_shares") - EXPECTED_DHR_REMAINDER) <= QTY_TOLERANCE


def test_fails_if_dhr_qty_wrong():
    pf = _baseline_portfolio()
    pf_bad = copy.deepcopy(pf)
    pf_bad["paper_accounting_epoch"]["verified_snapshot_baseline"]["positions"]["DHR"]["qty"] = EXPECTED_BASELINE_DHR_QTY + (QTY_TOLERANCE * 10)
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf_bad)
    assert ok is False
    assert "dhr_qty_mismatch" in payload.get("issues", [])


def test_fails_if_dhr_shares_wrong():
    pf = _baseline_portfolio()
    pf_bad = copy.deepcopy(pf)
    pf_bad["paper_accounting_epoch"]["verified_snapshot_baseline"]["positions"]["DHR"]["shares"] = EXPECTED_DHR_REMAINDER + (QTY_TOLERANCE * 10)
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf_bad)
    assert ok is False
    assert "dhr_shares_mismatch" in payload.get("issues", [])


def test_fails_if_relaxed_both_remainder_shape():
    """A relaxed shape that omits the explicit DHR 'shares' alias must fail.

    This verifies we do not accept a fallback behavior where qty is used to
    imply shares or vice versa; both aliases must be present and individually
    within tolerance.
    """
    pf = _baseline_portfolio()
    pf_bad = copy.deepcopy(pf)
    # remove the explicit shares alias to simulate a relaxed shape
    pf_bad["paper_accounting_epoch"]["verified_snapshot_baseline"]["positions"]["DHR"].pop("shares", None)
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf_bad)
    assert ok is False
    assert "dhr_shares_alias_missing" in payload.get("issues", [])
