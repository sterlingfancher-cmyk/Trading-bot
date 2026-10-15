from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from trading.ledger import (
    CanonicalLedgerEvidenceAdapter,
    CanonicalLedgerInvariantError,
    LedgerAppendIntent,
    LedgerProjectionObservation,
)
from trading.accounting import ExecutionSnapshot
from trading.risk import RiskLimits
from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    RiskStateSnapshot,
)
from trading.state_store import CanonicalStateStore
from trading.transaction import CanonicalTransactionInvariantError
from trading.valuation import ProtectedMarkSnapshot


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
    assert descriptor["prepares_exact_projection"] is True
    assert descriptor["prepares_preappend_intent"] is True
    assert descriptor["binds_settled_append_to_intent"] is True
    assert descriptor["production_writer_accepts_intent"] is False
    assert descriptor["write_ahead_journal_ready"] is False


def _intended_execution(
    sequence=2,
    *,
    event="exit",
    price=101.0,
    execution_id="execution-2",
):
    return ExecutionSnapshot(
        sequence=sequence,
        symbol="SPY",
        event=event,
        side="long",
        quantity=1.0,
        price=price,
        timestamp="2026-10-10 09:00:00 CDT",
        execution_id=execution_id,
    )


def test_preappend_intent_binds_exact_boundary_and_settled_identity(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    state = _state(total_rows=1, epoch_rows=1)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    original = path.read_bytes()

    intent = adapter.prepare_intent(
        previous=previous,
        current_state=state,
        executions=(_intended_execution(),),
    )

    assert isinstance(intent, LedgerAppendIntent)
    assert len(intent.intent_sha256) == 64
    assert intent.previous_state_payload_sha256 == state.payload_sha256
    assert intent.production_writes is False
    assert path.read_bytes() == original

    second = _row(first["event_hash"], "execution-2", "exit")
    _write(path, (first, second))
    settled = adapter.prove_intent(intent=intent, current_state=state)

    assert settled.executions == intent.executions
    assert settled.proof.appended_execution_ids == ("execution-2",)
    assert settled.current.total_rows == 2


def test_preappend_intent_rejects_sequence_boundary_and_preparation_drift(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    state = _state(total_rows=1, epoch_rows=1)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")

    with pytest.raises(CanonicalLedgerInvariantError, match="sequences"):
        adapter.prepare_intent(
            previous=previous,
            current_state=state,
            executions=(_intended_execution(sequence=3),),
        )

    second = _row(first["event_hash"], "execution-2", "exit")
    _write(path, (first, second))
    with pytest.raises(CanonicalLedgerInvariantError, match="changed before"):
        adapter.prepare_intent(
            previous=previous,
            current_state=state,
            executions=(_intended_execution(),),
        )


def test_preappend_intent_rejects_substituted_or_changed_append(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    state = _state(total_rows=1, epoch_rows=1)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    intent = adapter.prepare_intent(
        previous=previous,
        current_state=state,
        executions=(_intended_execution(),),
    )

    substituted = _row(first["event_hash"], "execution-other", "exit")
    _write(path, (first, substituted))
    with pytest.raises(CanonicalLedgerInvariantError, match="does not exactly match"):
        adapter.prove_intent(intent=intent, current_state=state)

    with pytest.raises(CanonicalLedgerInvariantError, match="StateStore changed"):
        adapter.prove_intent(
            intent=intent,
            current_state=_state(total_rows=0, epoch_rows=0),
        )


def test_preappend_intent_projection_requires_exact_fulfillment(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    state = _state(total_rows=1, epoch_rows=1)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    intent = adapter.prepare_intent(
        previous=previous,
        current_state=state,
        executions=(_intended_execution(event="entry", price=100.0),),
    )
    second = _row(first["event_hash"], "execution-2", "entry")
    _write(path, (first, second))

    result = adapter.prepare_intent_projection(
        intent=intent,
        current_state=state,
        protected_marks=(
            ProtectedMarkSnapshot(
                symbol="SPY",
                price=101.0,
                source="protected-test-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-10-10 09:00:30 CDT",
            ),
        ),
        risk_date="2026-10-10",
        risk_limits=RiskLimits(
            max_daily_loss_fraction=0.03,
            max_intraday_drawdown_fraction=0.03,
            hard_realized_loss_fraction=0.02,
        ),
        created_at="2026-10-10 09:01:00 CDT",
    )

    assert isinstance(result, LedgerProjectionObservation)
    assert result.append.executions == intent.executions
    assert result.transaction.ledger == result.append.proof


def test_adapter_binds_observed_append_to_exact_projection(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    second = _row(first["event_hash"], "execution-2", "entry")
    _write(path, (first, second))

    result = adapter.prepare_projection(
        previous=previous,
        current_state=_state(total_rows=1, epoch_rows=1),
        protected_marks=(
            ProtectedMarkSnapshot(
                symbol="SPY",
                price=101.0,
                source="protected-test-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-10-10 09:00:30 CDT",
            ),
        ),
        risk_date="2026-10-10",
        risk_limits=RiskLimits(
            max_daily_loss_fraction=0.03,
            max_intraday_drawdown_fraction=0.03,
            hard_realized_loss_fraction=0.02,
        ),
        created_at="2026-10-10 09:01:00 CDT",
    )

    assert isinstance(result, LedgerProjectionObservation)
    assert result.transaction.ledger == result.append.proof
    assert result.transaction.next_envelope.revision == 8
    snapshot = result.transaction.next_envelope.snapshot()
    assert snapshot.execution_ledger_rows == 2
    assert snapshot.execution_epoch_rows == 2
    assert snapshot.portfolio.positions[0].symbol == "SPY"
    assert snapshot.portfolio.cash == pytest.approx(900.0)
    assert snapshot.portfolio.equity == pytest.approx(1_001.0)
    assert result.runtime_registration is False
    assert result.production_writes is False
    assert result.order_authority is False


def test_adapter_projection_fails_closed_without_exact_marks(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    previous = adapter.observe(epoch_id="stable-paper-v5-test")
    second = _row(first["event_hash"], "execution-2", "entry")
    _write(path, (first, second))

    with pytest.raises(
        CanonicalTransactionInvariantError,
        match="protected marks",
    ):
        adapter.prepare_projection(
            previous=previous,
            current_state=_state(total_rows=1, epoch_rows=1),
            protected_marks=(),
            risk_date="2026-10-10",
            risk_limits=RiskLimits(
                max_daily_loss_fraction=0.03,
                max_intraday_drawdown_fraction=0.03,
                hard_realized_loss_fraction=0.02,
            ),
            created_at="2026-10-10 09:01:00 CDT",
        )
