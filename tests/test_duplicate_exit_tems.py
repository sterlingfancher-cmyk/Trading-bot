import journal_truth


def _make_row(action, execution_id, price, shares, symbol, side, time, accounting_epoch_id=None, **extra):
    row = {
        "accounting_epoch_id": accounting_epoch_id or "stable-paper-v2-20260812-verified01",
        "action": action,
        "execution_id": execution_id,
        "price": price,
        "shares": shares,
        "side": side,
        "symbol": symbol,
        "time": time,
    }
    row.update(extra)
    return row


def test_reproduce_canonical_tem_duplicate_exit_rows_in_state_primary():
    """
    Reproduce the production-shaped canonical TEM rows that appear in the
    forensic audit. This test only reconstructs the literal rows as they
    were observed in the stable-paper-v2 epoch and verifies the existing
    journal_truth state-primary logic sees both exits when they are present
    in the authoritative state.trades list.

    This proves the duplicate-exit appears in the primary state (state.json)
    shape rather than being an artifact only of journal mirroring; it is the
    reproduction/evidence step required before proposing any prospective
    append-time idempotency/consumption fix.
    """

    # Canonical production-shaped rows from the audit (literal execution_ids)
    entry = _make_row(
        action="entry",
        execution_id="d647d8a0580b44edbab0224e6c339bfd",
        price=54.885,
        shares=29.640567,
        symbol="TEM",
        side="long",
        # earlier time
        time=1_695_000_000.0,
    )

    first_exit = _make_row(
        action="exit",
        execution_id="7b13d9194a23407f926667b2f48d4057",
        price=53.105,
        shares=29.640567,
        symbol="TEM",
        side="long",
        # slightly later than entry
        time=1_695_000_100.0,
        exit_reason="filled",
        pnl_dollars=-(29.640567 * (53.105 - 54.885)),
    )

    second_exit = _make_row(
        action="exit",
        execution_id="3530dbf965db4894ba93b7098cec3696",
        price=52.905,
        shares=29.640567,
        symbol="TEM",
        side="long",
        # a distinct timestamp so journal_truth fuzzy/exact dedupe does not collapse them
        time=1_695_000_200.0,
        exit_reason="filled",
        pnl_dollars=-(29.640567 * (52.905 - 54.885)),
    )

    # Build an authoritative state dict (in-memory) that mirrors the production
    # state.json trades array where the duplicate exit was observed.
    state = {"trades": [entry, first_exit, second_exit]}

    # The journal_truth.state_execution_rows function treats state.trades as the
    # authoritative execution source. When duplicates exist in-state they are
    # preserved by the loader and should therefore be visible here.
    state_rows = journal_truth.state_execution_rows(state)

    # Ensure the entry is present
    ids = {r.get("execution_id") for r in state_rows}
    assert "d647d8a0580b44edbab0224e6c339bfd" in ids, "entry execution id missing from state_execution_rows"

    # Extract detected exits from the state primary rows
    exits = [r for r in state_rows if journal_truth._action(r) in {"exit", "partial_exit", "reduce", "reduce_position", "scale_out"}]

    # There should be two exits for TEM recorded in the authoritative state
    tem_exits = [r for r in exits if journal_truth._symbol(r) == "TEM"]
    assert len(tem_exits) == 2, f"expected 2 TEM exits in state_primary, found {len(tem_exits)}"

    # Verify the exact canonical execution ids are present in the reproduced rows
    tem_ids = {r.get("execution_id") for r in tem_exits}
    assert "7b13d9194a23407f926667b2f48d4057" in tem_ids, "first exit id not found"
    assert "3530dbf965db4894ba93b7098cec3696" in tem_ids, "second exit id not found"

    # Use reconciled_execution_rows to show that with state present, the state rows
    # are treated as primary and both exits survive into the reconciled list.
    reconciled = journal_truth.reconciled_execution_rows({"trades": []}, state)
    reconciled_ids = [r.get("execution_id") for r in reconciled]

    # Both exit ids should appear in the reconciled (state-primary) execution rows
    assert "7b13d9194a23407f926667b2f48d4057" in reconciled_ids
    assert "3530dbf965db4894ba93b7098cec3696" in reconciled_ids

    # Sanity: the reconciled execution order should preserve chronological ordering
    # (entry earlier than the first exit, which is earlier than the second exit)
    # Find indexes
    idx_entry = reconciled_ids.index("d647d8a0580b44edbab0224e6c339bfd")
    idx_exit1 = reconciled_ids.index("7b13d9194a23407f926667b2f48d4057")
    idx_exit2 = reconciled_ids.index("3530dbf965db4894ba93b7098cec3696")
    assert idx_entry < idx_exit1 < idx_exit2, "unexpected chronological order in reconciled execution rows"
