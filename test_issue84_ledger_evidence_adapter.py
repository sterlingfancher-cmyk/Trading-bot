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
from trading.ledger_writer import SandboxLedgerIntentWriter
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
from trading.transaction_journal import (
    AppendIntentJournalRecord,
    SandboxAppendIntentJournal,
    SandboxTransactionJournal,
)
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
    assert descriptor["sandbox_durable_intent_writer_ready"] is True


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


def _intent_record(intent, *, transaction_id="transaction-84"):
    return AppendIntentJournalRecord(
        transaction_id=transaction_id,
        phase="intent_prepared",
        intent_sha256=intent.intent_sha256,
        previous_state_sha256=intent.previous_state_payload_sha256,
        previous_total_rows=intent.previous.total_rows,
        previous_epoch_rows=intent.previous.epoch_rows,
        previous_ledger_sha256=intent.previous.ledger_sha256,
        previous_terminal_event_hash=intent.previous.terminal_event_hash,
        execution_ids=tuple(row.execution_id for row in intent.executions),
        created_at="2026-10-10 09:00:30 CDT",
        updated_at="2026-10-10 09:00:30 CDT",
    )


def _durable_intent_fixture(tmp_path, *, executions=None):
    path = tmp_path / "ledger.jsonl"
    first = _row("", "execution-1", "entry")
    _write(path, (first,))
    adapter = CanonicalLedgerEvidenceAdapter(path)
    state = _state(total_rows=1, epoch_rows=1)
    intent = adapter.prepare_intent(
        previous=adapter.observe(epoch_id="stable-paper-v5-test"),
        current_state=state,
        executions=executions or (_intended_execution(),),
    )
    return path, state, intent, _intent_record(intent)


def test_durable_intent_writer_appends_exact_identity_and_restarts_idempotently(
    tmp_path,
):
    path, state, intent, record = _durable_intent_fixture(tmp_path)
    prefix = path.read_bytes()
    writer = SandboxLedgerIntentWriter(path, sandbox_io_enabled=True)

    observation = writer.append_intent(intent, record, state)
    settled = path.read_bytes()

    assert settled.startswith(prefix)
    assert observation.executions == intent.executions
    assert observation.proof.appended_execution_ids == ("execution-2",)
    assert observation.current.total_rows == 2

    restarted = SandboxLedgerIntentWriter(
        path,
        sandbox_io_enabled=True,
    ).append_intent(intent, record, state)
    assert restarted == observation
    assert path.read_bytes() == settled


def test_durable_intent_writer_recovers_partial_append(tmp_path, monkeypatch):
    executions = (
        _intended_execution(),
        _intended_execution(
            sequence=3,
            event="entry",
            price=102.0,
            execution_id="execution-3",
        ),
    )
    path, state, intent, record = _durable_intent_fixture(
        tmp_path,
        executions=executions,
    )
    writer = SandboxLedgerIntentWriter(path, sandbox_io_enabled=True)
    original = writer._append_row_locked
    calls = 0

    def fail_second(row):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated crash after one durable row")
        original(row)

    monkeypatch.setattr(writer, "_append_row_locked", fail_second)
    with pytest.raises(RuntimeError, match="simulated crash"):
        writer.append_intent(intent, record, state)

    assert CanonicalLedgerEvidenceAdapter(path).observe(
        epoch_id="stable-paper-v5-test"
    ).total_rows == 2

    recovered = SandboxLedgerIntentWriter(
        path,
        sandbox_io_enabled=True,
    ).append_intent(intent, record, state)
    assert recovered.executions == executions
    assert recovered.current.total_rows == 3


def test_durable_intent_writer_rejects_substitution_before_mutation(tmp_path):
    path, state, intent, record = _durable_intent_fixture(tmp_path)
    original = path.read_bytes()
    writer = SandboxLedgerIntentWriter(path, sandbox_io_enabled=True)
    substituted = replace(record, intent_sha256="a" * 64, record_sha256="")

    with pytest.raises(CanonicalLedgerInvariantError, match="does not exactly bind"):
        writer.append_intent(intent, substituted, state)
    with pytest.raises(CanonicalLedgerInvariantError, match="StateStore changed"):
        writer.append_intent(
            intent,
            record,
            _state(total_rows=0, epoch_rows=0),
        )

    assert path.read_bytes() == original


def test_durable_intent_writer_rejects_precision_drift_before_mutation(tmp_path):
    path, state, intent, record = _durable_intent_fixture(
        tmp_path,
        executions=(_intended_execution(price=101.0000001),),
    )
    original = path.read_bytes()

    with pytest.raises(CanonicalLedgerInvariantError, match="price.*precision"):
        SandboxLedgerIntentWriter(
            path,
            sandbox_io_enabled=True,
        ).append_intent(intent, record, state)

    assert path.read_bytes() == original


def test_durable_intent_writer_rejects_divergent_partial_append(tmp_path):
    path, state, intent, record = _durable_intent_fixture(tmp_path)
    rows = CanonicalLedgerEvidenceAdapter(path)._read_rows()
    divergent = _row(rows[-1]["event_hash"], "execution-other", "exit")
    _write(path, (*(dict(row) for row in rows), divergent))
    original = path.read_bytes()

    with pytest.raises(CanonicalLedgerInvariantError, match="partial.*diverged"):
        SandboxLedgerIntentWriter(
            path,
            sandbox_io_enabled=True,
        ).append_intent(intent, record, state)

    assert path.read_bytes() == original


def test_durable_intent_writer_serializes_duplicate_callers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path, state, intent, record = _durable_intent_fixture(tmp_path)

    def append(_):
        return SandboxLedgerIntentWriter(
            path,
            sandbox_io_enabled=True,
        ).append_intent(intent, record, state)

    with ThreadPoolExecutor(max_workers=2) as pool:
        observations = list(pool.map(append, range(2)))

    assert observations[0] == observations[1]
    assert observations[0].current.total_rows == 2


def test_durable_intent_writer_completes_journal_handoff_chain(tmp_path):
    intended = _intended_execution(event="entry", price=100.0)
    path, state, intent, _ = _durable_intent_fixture(
        tmp_path,
        executions=(intended,),
    )
    intent_journal = SandboxAppendIntentJournal(
        tmp_path / "append-intent-journal.json",
        sandbox_io_enabled=True,
    )
    record = intent_journal.begin(
        intent,
        transaction_id="transaction-84",
        recorded_at="2026-10-10 09:00:30 CDT",
    )

    SandboxLedgerIntentWriter(
        path,
        sandbox_io_enabled=True,
    ).append_intent(intent, record, state)
    projection = CanonicalLedgerEvidenceAdapter(path).prepare_intent_projection(
        intent=intent,
        current_state=state,
        protected_marks=(
            ProtectedMarkSnapshot(
                symbol="SPY",
                price=101.0,
                source="protected-test-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-10-10 09:00:45 CDT",
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
    transaction_journal = SandboxTransactionJournal(
        tmp_path / "transaction-journal.json",
        sandbox_io_enabled=True,
    )
    handoff = intent_journal.handoff_projection(
        intent,
        projection,
        transaction_journal,
        transaction_id="transaction-84",
        recorded_at="2026-10-10 09:01:01 CDT",
    )

    assert handoff.intent_sha256 == intent.intent_sha256
    assert handoff.execution_ids == ("execution-2",)
    assert intent_journal.read_sandbox().phase == "append_bound"
    assert transaction_journal.read_sandbox().phase == "ledger_settled"
    assert state.revision == 7


def test_durable_intent_writer_declares_sandbox_only_authority(tmp_path):
    descriptor = SandboxLedgerIntentWriter.descriptor()
    assert descriptor["authority"] == "shadow_only"
    assert descriptor["runtime_registered"] is False
    assert descriptor["production_write_enabled"] is False
    assert descriptor["sandbox_write_enabled"] is True
    assert descriptor["places_orders"] is False
    assert descriptor["accepts_durable_append_intent"] is True
    assert descriptor["idempotent_partial_append_recovery"] is True
    assert descriptor["append_call_can_override_intent_identity"] is False
    assert descriptor["commits_state_store"] is False
    assert descriptor["production_writer_connected"] is False

    with pytest.raises(PermissionError):
        SandboxLedgerIntentWriter(tmp_path / "ledger.jsonl").append_intent(
            object(),
            object(),
            object(),
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
