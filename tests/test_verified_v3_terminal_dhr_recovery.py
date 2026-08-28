import copy

from verified_v3_successor_epoch_migration import (
    canonical_only_terminal_dhr_state_shape_exact,
    EXPECTED_BASELINE_DHR_QTY,
    EXPECTED_DHR_REMAINDER,
    QTY_TOLERANCE,
    TERMINAL_DHR_EXECUTION_ID,
)


def base_portfolio():
    return {
        "paper_accounting_epoch": {
            "id": "stable-paper-v3-20260825-successor01",
            "prior_epoch_id": "stable-paper-v2-20260812-verified01",
            "validation_hold": True,
            "verified_snapshot_baseline": {
                "verified": True,
                "positions": {
                    "DHR": {
                        "side": "long",
                        # production observed alias shape: qty remains baseline
                        "qty": EXPECTED_BASELINE_DHR_QTY,
                        # shares reflects the remainder
                        "shares": EXPECTED_DHR_REMAINDER,
                        "entry_price": 216.960007,
                    },
                    "SLS": {
                        "side": "long",
                        "qty": 4.353086829,
                        "entry_price": 13.62,
                    },
                },
                "cash": 13483.47647864577,
                "equity": 13602.08,
                "realized_today": 0.0,
            },
            "starting_cash": 13357.874520862653,
            "baseline_type": "verified_snapshot_with_open_position",
        },
        "trades": [
            # mirrored v3 rows (3 rows) — intentionally not including terminal DHR
            {"execution_id": "9ab93335faff4e3293d24ebe0bad4e87", "accounting_epoch_id": "stable-paper-v3-20260825-successor01", "action": "exit", "symbol": "SLS", "side": "long", "price": 13.62, "canonical_ledger_event_hash": "d4564210ff39029aeea4727ccc121a18445fe7c79c21fa96bc5f4a8874e4b725"},
            {"execution_id": "26702f252870490c8f1ddab86ce794f5", "accounting_epoch_id": "stable-paper-v3-20260825-successor01", "action": "partial_exit", "symbol": "DHR", "side": "long", "price": 242.4872, "canonical_ledger_event_hash": "f29532b852bca42c7ee690643e167d9c2a1229a8b44d6dcc9eb1089a1939ddd2"},
            {"execution_id": "90b22aad76074031906e0c6459dfa0bc", "accounting_epoch_id": "stable-paper-v3-20260825-successor01", "action": "partial_exit", "symbol": "SLS", "side": "long", "price": 16.04, "canonical_ledger_event_hash": "d39e877f34bcf9d5a720a8bfd94a66ebace9d8cfa30987bedce29a1112db8774"},
        ],
    }


def test_production_alias_shape_passes():
    pf = base_portfolio()
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf)
    assert ok, f"Expected production alias shape to pass, got payload: {payload}"


def test_wrong_baseline_qty_fails():
    pf = base_portfolio()
    pf = copy.deepcopy(pf)
    # change qty beyond tolerance
    pf["paper_accounting_epoch"]["verified_snapshot_baseline"]["positions"]["DHR"]["qty"] = EXPECTED_BASELINE_DHR_QTY + (QTY_TOLERANCE * 10)
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf)
    assert not ok
    assert "dhr_qty_mismatch_from_expected_baseline" in payload["issues"]


def test_wrong_remainder_shares_fails():
    pf = base_portfolio()
    pf = copy.deepcopy(pf)
    # change shares beyond tolerance
    pf["paper_accounting_epoch"]["verified_snapshot_baseline"]["positions"]["DHR"]["shares"] = EXPECTED_DHR_REMAINDER + (QTY_TOLERANCE * 10)
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf)
    assert not ok
    assert "dhr_shares_mismatch_from_expected_remainder" in payload["issues"]


def test_terminal_dhr_present_in_trades_fails():
    pf = base_portfolio()
    pf = copy.deepcopy(pf)
    # Insert the terminal DHR execution id into state trades (should fail)
    pf["trades"].append({"execution_id": TERMINAL_DHR_EXECUTION_ID, "accounting_epoch_id": "stable-paper-v3-20260825-successor01"})
    payload, ok = canonical_only_terminal_dhr_state_shape_exact(pf)
    assert not ok
    assert "terminal_dhr_execution_present_in_state_trades" in payload["issues"]
