from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from trading.accounting import ExecutionSnapshot
from trading.risk import RiskLimits
from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    RiskStateSnapshot,
)
from trading.state_store import CanonicalStateStore
from trading.transaction import LedgerAppendProof, SingleOwnerProjectionTransaction
from trading.transaction_journal import (
    ObservedLedgerState,
    SandboxTransactionJournal,
    TransactionJournalInvariantError,
)
from trading.valuation import ProtectedMarkSnapshot


def _current():
    snapshot = CanonicalStateSnapshot(
        portfolio=PortfolioSnapshot(
            cash=1_000.0,
            equity=1_000.0,
            realized_total=0.0,
            realized_today=0.0,
            unrealized_pnl=0.0,
            positions=(),
            accounting_epoch=AccountingEpochSnapshot(
                epoch_id="stable-paper-v5-test",
                baseline_type="verified_flat_successor",
                historical_evidence_archived=True,
                validation_hold=False,
            ),
        ),
        risk=RiskStateSnapshot(
            date="2026-10-01",
            day_start_equity=1_000.0,
            day_peak_equity=1_000.0,
            daily_loss_fraction=0.0,
            intraday_drawdown_fraction=0.0,
            halted=False,
        ),
        execution_ledger_rows=88,
        execution_epoch_rows=0,
        execution_chain_valid=True,
    )
    envelope = CanonicalStateStore.prepare(
        snapshot=snapshot,
        revision=7,
        created_at="2026-10-01 08:00:00 CDT",
    )
    assert envelope.snapshot().execution_ledger_rows == 88
    return envelope


def _receipt():
    current = _current()
    execution = ExecutionSnapshot(
        sequence=89,
        symbol="SPY",
        event="entry",
        side="long",
        quantity=1.0,
        price=100.0,
        timestamp="2026-10-01 08:01:00 CDT",
        execution_id="execution-89",
    )
    proof = LedgerAppendProof(
        previous_total_rows=88,
        next_total_rows=89,
        previous_epoch_rows=0,
        next_epoch_rows=1,
        previous_state_payload_sha256=current.payload_sha256,
        previous_sha256="a" * 64,
        next_sha256="b" * 64,
        appended_execution_ids=("execution-89",),
        chain_valid=True,
    )
    return SingleOwnerProjectionTransaction.prepare(
        current=current,
        executions=(execution,),
        protected_marks=(
            ProtectedMarkSnapshot(
                symbol="SPY",
                price=101.0,
                source="protected-test-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-10-01 08:01:01 CDT",
            ),
        ),
        ledger=proof,
        risk_date="2026-10-01",
        risk_limits=RiskLimits(
            max_daily_loss_fraction=0.03,
            max_intraday_drawdown_fraction=0.03,
            hard_realized_loss_fraction=0.02,
        ),
        created_at="2026-10-01 08:01:02 CDT",
    )


def _next_receipt(current):
    execution = ExecutionSnapshot(
        sequence=90,
        symbol="SPY",
        event="exit",
        side="long",
        quantity=1.0,
        price=102.0,
        timestamp="2026-10-01 08:02:00 CDT",
        execution_id="execution-90",
    )
    proof = LedgerAppendProof(
        previous_total_rows=89,
        next_total_rows=90,
        previous_epoch_rows=1,
        next_epoch_rows=2,
        previous_state_payload_sha256=current.payload_sha256,
        previous_sha256="b" * 64,
        next_sha256="c" * 64,
        appended_execution_ids=("execution-90",),
        chain_valid=True,
    )
    return SingleOwnerProjectionTransaction.prepare(
        current=current,
        executions=(execution,),
        protected_marks=(),
        ledger=proof,
        risk_date="2026-10-01",
        risk_limits=RiskLimits(
            max_daily_loss_fraction=0.03,
            max_intraday_drawdown_fraction=0.03,
            hard_realized_loss_fraction=0.02,
        ),
        created_at="2026-10-01 08:02:02 CDT",
    )


def _observed_previous():
    return ObservedLedgerState(
        total_rows=88,
        epoch_rows=0,
        ledger_sha256="a" * 64,
        chain_valid=True,
    )


def _observed_next():
    return ObservedLedgerState(
        total_rows=89,
        epoch_rows=1,
        ledger_sha256="b" * 64,
        chain_valid=True,
        execution_ids=("execution-89",),
    )


def _sandbox(tmp_path):
    state = CanonicalStateStore(
        tmp_path / "canonical-state.json", sandbox_io_enabled=True
    )
    state.commit_sandbox(_current())
    journal = SandboxTransactionJournal(
        tmp_path / "transaction-journal.json", sandbox_io_enabled=True
    )
    return state, journal


def test_preappend_recovery_aborts_without_ledger_or_state_mutation(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    baseline_bytes = state.path.read_bytes()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )

    recovery = journal.recover(
        receipt,
        _observed_previous(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )

    assert recovery.action == "aborted_before_append"
    assert recovery.replayed_state_commit is False
    assert state.path.read_bytes() == baseline_bytes
    assert state.read_sandbox().revision == 7
    assert journal.read_sandbox().phase == "aborted_before_append"


def test_crash_after_append_rolls_forward_exactly_one_state_revision(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )

    recovery = journal.recover(
        receipt,
        _observed_next(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )

    persisted = state.read_sandbox()
    assert recovery.action == "state_commit_replayed"
    assert recovery.replayed_state_commit is True
    assert persisted.revision == 8
    assert persisted.payload_sha256 == receipt.next_envelope.payload_sha256
    assert persisted.snapshot().execution_ledger_rows == 89
    assert journal.read_sandbox().phase == "state_committed"


def test_restart_after_commit_is_idempotent_and_does_not_create_revision_nine(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.settle_ledger(
        receipt,
        _observed_next(),
        recorded_at="2026-10-01 08:01:02 CDT",
    )
    state.commit_sandbox(receipt.next_envelope)

    restarted_state = CanonicalStateStore(state.path, sandbox_io_enabled=True)
    restarted_journal = SandboxTransactionJournal(
        journal.path, sandbox_io_enabled=True
    )
    recovery = restarted_journal.recover(
        receipt,
        _observed_next(),
        restarted_state,
        recorded_at="2026-10-01 08:01:04 CDT",
    )

    assert recovery.action == "already_committed"
    assert recovery.replayed_state_commit is False
    assert restarted_state.read_sandbox().revision == 8
    assert restarted_journal.read_sandbox().phase == "state_committed"


def test_repeated_ledger_settlement_preserves_record_bytes_and_digest(tmp_path):
    _, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    settled = journal.settle_ledger(
        receipt,
        _observed_next(),
        recorded_at="2026-10-01 08:01:02 CDT",
    )
    settled_bytes = journal.path.read_bytes()

    repeated = SandboxTransactionJournal(
        journal.path, sandbox_io_enabled=True
    ).settle_ledger(
        receipt,
        _observed_next(),
        recorded_at="2026-10-01 08:05:00 CDT",
    )

    assert repeated == settled
    assert journal.path.read_bytes() == settled_bytes


def test_repeated_ledger_settlement_rejects_boundary_drift_without_mutation(tmp_path):
    _, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.settle_ledger(
        receipt,
        _observed_next(),
        recorded_at="2026-10-01 08:01:02 CDT",
    )
    settled_bytes = journal.path.read_bytes()

    with pytest.raises(TransactionJournalInvariantError):
        journal.settle_ledger(
            receipt,
            ObservedLedgerState(
                total_rows=89,
                epoch_rows=1,
                ledger_sha256="c" * 64,
                chain_valid=True,
                execution_ids=("execution-89",),
            ),
            recorded_at="2026-10-01 08:05:00 CDT",
        )

    assert journal.path.read_bytes() == settled_bytes


def test_repeated_recovery_preserves_terminal_record_bytes_and_digest(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    first = journal.recover(
        receipt,
        _observed_next(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )
    terminal = journal.read_sandbox()
    terminal_bytes = journal.path.read_bytes()

    repeated = SandboxTransactionJournal(
        journal.path, sandbox_io_enabled=True
    ).recover(
        receipt,
        _observed_next(),
        CanonicalStateStore(state.path, sandbox_io_enabled=True),
        recorded_at="2026-10-01 08:05:00 CDT",
    )

    assert first.action == "state_commit_replayed"
    assert repeated.action == "already_committed"
    assert repeated.replayed_state_commit is False
    assert journal.path.read_bytes() == terminal_bytes
    assert journal.read_sandbox() == terminal


def test_repeated_terminal_recovery_rejects_stale_state_without_mutation(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    previous_state_bytes = state.path.read_bytes()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.recover(
        receipt,
        _observed_next(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )
    terminal_bytes = journal.path.read_bytes()
    stale_state_path = tmp_path / "stale-state.json"
    stale_state_path.write_bytes(previous_state_bytes)

    with pytest.raises(
        TransactionJournalInvariantError,
        match="committed recovery requires the exact terminal boundary",
    ):
        journal.recover(
            receipt,
            _observed_next(),
            CanonicalStateStore(stale_state_path, sandbox_io_enabled=True),
            recorded_at="2026-10-01 08:05:00 CDT",
        )

    assert journal.path.read_bytes() == terminal_bytes


@pytest.mark.parametrize(
    "observed",
    (
        ObservedLedgerState(89, 1, "c" * 64, True, ("execution-89",)),
        ObservedLedgerState(90, 2, "b" * 64, True, ("execution-89",)),
        ObservedLedgerState(89, 1, "b" * 64, True, ("other",)),
    ),
)
def test_recovery_rejects_ledger_boundary_drift(tmp_path, observed):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )

    with pytest.raises(TransactionJournalInvariantError):
        journal.recover(
            receipt,
            observed,
            state,
            recorded_at="2026-10-01 08:01:03 CDT",
        )
    assert state.read_sandbox().revision == 7


def test_recovery_rejects_unrelated_state_revision(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    unrelated = CanonicalStateStore.prepare(
        snapshot=_current().snapshot(),
        revision=9,
        created_at="2026-10-01 08:01:02 CDT",
    )
    state.commit_sandbox(unrelated)

    with pytest.raises(TransactionJournalInvariantError):
        journal.recover(
            receipt,
            _observed_next(),
            state,
            recorded_at="2026-10-01 08:01:03 CDT",
        )


def test_journal_digest_detects_tampering(tmp_path):
    _, journal = _sandbox(tmp_path)
    journal.begin(
        _receipt(),
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    raw = json.loads(journal.path.read_text(encoding="utf-8"))
    raw["next_revision"] = 99
    journal.path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(TransactionJournalInvariantError):
        journal.read_sandbox()


def test_process_lock_allows_only_one_transaction_identity(tmp_path):
    _, journal = _sandbox(tmp_path)
    receipt = _receipt()

    def begin(transaction_id):
        process_peer = SandboxTransactionJournal(
            journal.path, sandbox_io_enabled=True
        )
        try:
            return process_peer.begin(
                receipt,
                transaction_id=transaction_id,
                recorded_at="2026-10-01 08:01:01 CDT",
            ).transaction_id
        except TransactionJournalInvariantError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = set(pool.map(begin, ("transaction-a", "transaction-b")))

    assert "rejected" in results
    assert len(results) == 2
    assert journal.read_sandbox().transaction_id in {"transaction-a", "transaction-b"}


def test_terminal_record_is_archived_before_next_transaction_reuses_slot(tmp_path):
    state, journal = _sandbox(tmp_path)
    first = _receipt()
    journal.begin(
        first,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.recover(
        first,
        _observed_next(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )
    terminal = journal.read_sandbox()
    terminal_bytes = journal.path.read_bytes()
    second = _next_receipt(state.read_sandbox())

    active = journal.begin(
        second,
        transaction_id="transaction-90",
        recorded_at="2026-10-01 08:02:01 CDT",
    )

    archives = list(tmp_path.glob(".transaction-journal.json.*.terminal.json"))
    assert active.phase == "prepared"
    assert active.transaction_id == "transaction-90"
    assert len(archives) == 1
    assert archives[0].name == (
        f".transaction-journal.json.{terminal.record_sha256}.terminal.json"
    )
    assert archives[0].read_bytes() == terminal_bytes
    assert json.loads(archives[0].read_text(encoding="utf-8"))["phase"] == (
        "state_committed"
    )

    restarted = SandboxTransactionJournal(journal.path, sandbox_io_enabled=True)
    assert restarted.begin(
        second,
        transaction_id="transaction-90",
        recorded_at="2026-10-01 08:02:01 CDT",
    ) == active


def test_terminal_rollover_rejects_tampered_existing_archive(tmp_path):
    state, journal = _sandbox(tmp_path)
    receipt = _receipt()
    journal.begin(
        receipt,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.recover(
        receipt,
        _observed_previous(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )
    terminal = journal.read_sandbox()
    archive = journal._terminal_archive_path(terminal)
    archive.write_bytes(b"tampered")

    with pytest.raises(
        TransactionJournalInvariantError,
        match="terminal journal archive is not immutable",
    ):
        journal.begin(
            receipt,
            transaction_id="transaction-90",
            recorded_at="2026-10-01 08:02:01 CDT",
        )
    assert journal.read_sandbox() == terminal


def test_process_lock_allows_only_one_successor_after_terminal_rollover(tmp_path):
    state, journal = _sandbox(tmp_path)
    first = _receipt()
    journal.begin(
        first,
        transaction_id="transaction-89",
        recorded_at="2026-10-01 08:01:01 CDT",
    )
    journal.recover(
        first,
        _observed_next(),
        state,
        recorded_at="2026-10-01 08:01:03 CDT",
    )
    second = _next_receipt(state.read_sandbox())

    def begin(transaction_id):
        process_peer = SandboxTransactionJournal(
            journal.path, sandbox_io_enabled=True
        )
        try:
            return process_peer.begin(
                second,
                transaction_id=transaction_id,
                recorded_at="2026-10-01 08:02:01 CDT",
            ).transaction_id
        except TransactionJournalInvariantError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = set(pool.map(begin, ("transaction-90-a", "transaction-90-b")))

    assert "rejected" in results
    assert len(results) == 2
    assert journal.read_sandbox().transaction_id in {
        "transaction-90-a",
        "transaction-90-b",
    }
    assert len(
        list(tmp_path.glob(".transaction-journal.json.*.terminal.json"))
    ) == 1


def test_journal_has_no_runtime_or_order_authority(tmp_path):
    descriptor = SandboxTransactionJournal.descriptor()
    assert descriptor["authority"] == "shadow_only"
    assert descriptor["runtime_registered"] is False
    assert descriptor["production_write_enabled"] is False
    assert descriptor["places_orders"] is False
    assert descriptor["rewrites_canonical_ledger"] is False
    assert descriptor["ledger_settlement"] == "immutable_idempotent_record"
    assert descriptor["terminal_rollover"] == (
        "immutable_digest_archive_before_reuse"
    )
    assert descriptor["terminal_recovery"] == "immutable_idempotent_receipt"

    with pytest.raises(PermissionError):
        SandboxTransactionJournal(tmp_path / "journal.json").begin(
            _receipt(),
            transaction_id="transaction-89",
            recorded_at="2026-10-01 08:01:01 CDT",
        )
