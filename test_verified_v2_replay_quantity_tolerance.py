from __future__ import annotations

import verified_v2_successor_replay_status as replay


def _row(execution_id, action, symbol, side, price, shares, recorded_local, exit_reason=None):
    return {
        "execution_id": execution_id,
        "accounting_epoch_id": replay.TARGET_EPOCH_ID,
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": price,
        "shares": shares,
        "recorded_local": recorded_local,
        "exit_reason": exit_reason,
        "event_hash": f"hash-{execution_id}",
    }


def test_sub_micro_share_exit_residue_is_reconciled_only_in_replay_arithmetic():
    rows = [
        _row(
            "qqq-entry",
            "entry",
            "QQQ",
            "long",
            700.0,
            2.218802876,
            "2026-08-19 09:30:00 CDT",
        ),
        _row(
            "qqq-exit",
            "exit",
            "QQQ",
            "long",
            718.015015,
            2.218803,
            "2026-08-19 10:07:22 CDT",
            "market_regime_protection",
        ),
    ]

    projection = replay._project(rows)

    assert projection["projection_complete"] is True
    assert projection["errors"] == []
    assert projection["quantity_residue_adjustment_count"] == 1
    adjustment = projection["quantity_residue_adjustments"][0]
    assert adjustment["execution_id"] == "qqq-exit"
    assert 0 < adjustment["unmatched_qty"] < replay.REPLAY_QTY_TOLERANCE
    assert adjustment["disposition"] == "accepted_as_canonical_quantity_serialization_residue_only"
    assert all(row["symbol"] != "QQQ" for row in projection["candidate_positions"])


def test_material_exit_quantity_gap_still_fails_closed():
    rows = [
        _row(
            "qqq-entry",
            "entry",
            "QQQ",
            "long",
            700.0,
            2.21879,
            "2026-08-19 09:30:00 CDT",
        ),
        _row(
            "qqq-exit",
            "exit",
            "QQQ",
            "long",
            718.015015,
            2.218803,
            "2026-08-19 10:07:22 CDT",
            "market_regime_protection",
        ),
    ]

    projection = replay._project(rows)

    assert projection["projection_complete"] is False
    assert projection["errors"][0]["reason"] == "exit_exceeds_projected_position"
    assert projection["errors"][0]["unmatched_qty"] > replay.REPLAY_QTY_TOLERANCE


def test_known_invalid_signature_quantity_tolerance_remains_strict():
    expected = dict(replay.KNOWN_INVALID_EXECUTIONS[0])
    observed = dict(expected)
    observed["shares"] = float(expected["shares"]) + 1e-7

    checks = replay._signature_checks(observed, expected)

    assert replay.QTY_TOLERANCE == 5e-9
    assert replay.REPLAY_QTY_TOLERANCE == 5e-6
    assert replay.QTY_TOLERANCE < replay.REPLAY_QTY_TOLERANCE
    assert checks["shares"] is False
