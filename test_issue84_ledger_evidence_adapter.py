from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from trading.ledger import (
    CanonicalLedgerEvidenceAdapter,
    CanonicalLedgerInvariantError,
)
from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    RiskStateSnapshot,
)
from trading.state_store import CanonicalStateStore


def _canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _row(previous_hash, execution_id, action, *, epoch="stable-paper-v5-test"):
    body = {
        "execution_id": execution_id,
        "ledger_version": "test-ledger-v1",
        "recorded_local": "2026-10-10 09:00:00 CDT",
        "accounting_epoch_id": epoch,
        "action": action,
        "symbol": "SPY",
        "side": "long",
        "price": 100.0 if action == "entry" else 101.0,
        "shares": 1.0,
    }
    event_hash = sha256(
        (previous_hash + "|" + _canonical_json(body)).encode("utf-8")
    ).hexdigest()
    return {
        **body,
        "previous_event_hash": previous_hash,
        "event_hash": event_hash,
    }


def _write(path, rows):
    path.write_text(
        "".join(_canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _state(*, total_rows, epoch_rows, epoch_id="stable-paper-v5-test"):
    snapshot = CanonicalStateSnapshot(
        portfolio=PortfolioSnapshot(
            cash=1_000.0,
            equity=1_000.0,
            realized_total=0.0,
            realized_today=0.0,
            unrealized_pnl=0.0,
            positions=(),
            accounting_epoch=AccountingEpochSnapshot(
                epoch_id=epoch_id,
                baseline_type="verified_flat_successor",
                historical_evidence_archived=True,
                validation_hold=False,
            ),
        ),
        risk=RiskStateSnapshot(
            date="2026-10-10",
            day_start_equity=1_000.0,
            day_peak_equity=1_000.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        ),
        execution_ledger_rows=total_rows,
        execution_epoch_rows=epoch_rows,
        execution_chain_valid=True,
    )
    return CanonicalStateStore.prepare(
        snapshot=snapshot,
        revision=7,
        created_at="2026-10-10 09:00:00 CDT",
    )


def test_adapter_derives_exact_typed_append_proof_without_writes(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    original_prefix = path.read_bytes()

    second = _row(first["event_hash"], "execution-2", "partial_exit")
    _write(path, (first, second))
    observation = adapter.prove_append(
        previous=previous,
        current_state=_state(total_rows=1, epoch_rows=1),
    )

    assert observation.proof.previous_total_rows == 1
    assert observation.proof.next_total_rows == 2
    assert observation.proof.appended_execution_ids == ("execution-2",)
    assert observation.executions[0].sequence == 2
    assert observation.executions[0].event == "exit"
    assert observation.current.ledger_sha256 == sha256(path.read_bytes()).hexdigest()
    assert path.read_bytes().startswith(original_prefix)
    assert observation.production_writes is False
    assert observation.runtime_registration is False
    assert observation.order_authority is False


def test_adapter_rejects_state_or_prefix_boundary_drift(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    second = _row(first["event_hash"], "execution-2", "exit")
    _write(path, (first, second))

    with pytest.raises(
        CanonicalLedgerInvariantError,
        match="current StateStore revision",
    ):
        adapter.prove_append(
            previous=previous,
            current_state=_state(total_rows=0, epoch_rows=0),
        )

    with pytest.raises(CanonicalLedgerInvariantError, match="prefix changed"):
        adapter.prove_append(
            previous=replace(previous, ledger_sha256="a" * 64),
            current_state=_state(total_rows=1, epoch_rows=1),
        )

    with pytest.raises(
        CanonicalLedgerInvariantError,
        match="current StateStore revision",
    ):
        adapter.prove_append(
            previous=previous,
            current_state=_state(
                total_rows=1,
                epoch_rows=1,
                epoch_id="stable-paper-v6-other",
            ),
        )


def test_adapter_rejects_tamper_duplicate_and_cross_epoch_append(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")

    tampered = {**first, "price": 999.0}
    _write(path, (tampered,))
    with pytest.raises(CanonicalLedgerInvariantError, match="event hash mismatch"):
        adapter.observe(epoch_id="stable-paper-v5-test")

    duplicate = _row(first["event_hash"], "execution-1", "exit")
    _write(path, (first, duplicate))
    with pytest.raises(CanonicalLedgerInvariantError, match="duplicated"):
        adapter.prove_append(
            previous=previous,
            current_state=_state(total_rows=1, epoch_rows=1),
        )

    other_epoch = _row(
        first["event_hash"],
        "execution-2",
        "exit",
        epoch="stable-paper-v6-other",
    )
    _write(path, (first, other_epoch))
    with pytest.raises(CanonicalLedgerInvariantError, match="crossed"):
        adapter.prove_append(
            previous=previous,
            current_state=_state(total_rows=1, epoch_rows=1),
        )


def test_adapter_rejects_missing_or_empty_append(tmp_path):
    missing = CanonicalLedgerEvidenceAdapter(tmp_path / "missing.jsonl")
    with pytest.raises(CanonicalLedgerInvariantError, match="missing"):
        missing.observe(epoch_id="stable-paper-v5-test")

    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    with pytest.raises(CanonicalLedgerInvariantError, match="no new settled append"):
        adapter.prove_append(
            previous=previous,
            current_state=_state(total_rows=1, epoch_rows=1),
        )


def test_adapter_descriptor_has_no_runtime_or_mutation_authority():
    descriptor = CanonicalLedgerEvidenceAdapter.descriptor()
    assert descriptor["authority"] == "shadow_only"
    assert descriptor["runtime_registered"] is False
    assert descriptor["production_writes"] is False
    assert descriptor["reads_environment"] is False
    assert descriptor["places_orders"] is False
    assert descriptor["validates_full_hash_chain"] is True
    assert descriptor["proves_immutable_prefix"] is True
