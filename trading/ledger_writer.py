
The production canonical ledger remains owned by ``canonical_execution_ledger``.
This module proves that a durable pre-append intent can drive an exact,
restart-safe append without caller-selected identity.  It is deliberately not
registered with the runtime and cannot target production without a later,
separately reviewed adapter and cutover decision.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import fcntl
import os
from pathlib import Path
import threading
from types import MappingProxyType
from typing import Any, Mapping

from trading.accounting import ExecutionSnapshot
from trading.ledger import (
    AUTHORITY,
    CanonicalLedgerEvidenceAdapter,
    CanonicalLedgerInvariantError,
    LedgerAppendIntent,
    LedgerAppendObservation,
    _canonical_json,
    _rows_sha256,
)
from trading.state_store import CanonicalStateEnvelope
from trading.transaction_journal import AppendIntentJournalRecord


VERSION = "stable-paper-core-v3-durable-intent-writer-2026-10-19-v1"
CANONICAL_ROW_VERSION = "canonical-execution-ledger-2026-09-25-v6-fail-closed-append"


class SandboxLedgerIntentWriter:
    """Append only rows fixed by one durable intent, in an explicit sandbox."""

    authority = AUTHORITY
    runtime_registered = False
    production_write_enabled = False
    places_orders = False

    def __init__(self, path: Path | str, *, sandbox_io_enabled: bool = False):
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.intent-writer.lock")
        self.sandbox_io_enabled = bool(sandbox_io_enabled)
        self._lock = threading.RLock()

    def _assert_sandbox(self) -> None:
        if not self.sandbox_io_enabled:
            raise PermissionError("durable intent writer requires explicit sandbox I/O")

    @contextmanager
    def _process_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _assert_record(
        intent: LedgerAppendIntent,
        record: AppendIntentJournalRecord,
    ) -> None:
        if not isinstance(intent, LedgerAppendIntent):
            raise CanonicalLedgerInvariantError(
                "durable intent writer requires a typed append intent"
            )
        if not isinstance(record, AppendIntentJournalRecord):
            raise CanonicalLedgerInvariantError(
                "durable intent writer requires a typed journal record"
            )
        expected = {
            "phase": "intent_prepared",
            "intent_sha256": intent.intent_sha256,
            "previous_state_sha256": intent.previous_state_payload_sha256,
            "previous_total_rows": intent.previous.total_rows,
            "previous_epoch_rows": intent.previous.epoch_rows,
            "previous_ledger_sha256": intent.previous.ledger_sha256,
            "previous_terminal_event_hash": intent.previous.terminal_event_hash,
            "execution_ids": tuple(row.execution_id for row in intent.executions),
        }
        observed = {
            "phase": record.phase,
            "intent_sha256": record.intent_sha256,
            "previous_state_sha256": record.previous_state_sha256,
            "previous_total_rows": record.previous_total_rows,
            "previous_epoch_rows": record.previous_epoch_rows,
            "previous_ledger_sha256": record.previous_ledger_sha256,
            "previous_terminal_event_hash": record.previous_terminal_event_hash,
            "execution_ids": record.execution_ids,
        }
        if observed != expected:
            raise CanonicalLedgerInvariantError(
                "durable journal record does not exactly bind the append intent"
            )

    @staticmethod
    def _row_for(execution: ExecutionSnapshot) -> Mapping[str, Any]:
        if round(execution.price, 6) != execution.price:
            raise CanonicalLedgerInvariantError(
                "intent price exceeds canonical ledger precision"
            )
        if round(execution.quantity, 9) != execution.quantity:
            raise CanonicalLedgerInvariantError(
                "intent quantity exceeds canonical ledger precision"
            )
        body = {
            "execution_id": execution.execution_id,
            "ledger_version": CANONICAL_ROW_VERSION,
            "recorded_local": execution.timestamp,
            "accounting_epoch_id": None,
            "action": execution.event,
            "symbol": execution.symbol,
            "side": execution.side,
            "price": round(execution.price, 6),
            "shares": round(execution.quantity, 9),
        }
        return body

    @staticmethod
    def _materialize_row(
        execution: ExecutionSnapshot,
        *,
        epoch_id: str,
        previous_hash: str,
    ) -> Mapping[str, Any]:
        body = dict(SandboxLedgerIntentWriter._row_for(execution))
        body["accounting_epoch_id"] = epoch_id
        event_hash = sha256(
            (previous_hash + "|" + _canonical_json(body)).encode("utf-8")
        ).hexdigest()
        return MappingProxyType(
            {
                **body,
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
            }
        )

    def _append_row_locked(self, row: Mapping[str, Any]) -> None:
        line = (_canonical_json(row) + "\n").encode("utf-8")
        with self.path.open("ab") as handle:
            written = handle.write(line)
            if written != len(line):
                raise OSError("canonical intent row append was incomplete")
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(str(self.path.parent), os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def append_intent(
        self,
        intent: LedgerAppendIntent,
        record: AppendIntentJournalRecord,
        current_state: CanonicalStateEnvelope,
    ) -> LedgerAppendObservation:
        """Append or resume exactly the rows fixed by one durable intent."""
        self._assert_sandbox()
        self._assert_record(intent, record)
        if not isinstance(current_state, CanonicalStateEnvelope):
            raise CanonicalLedgerInvariantError(
                "durable intent writer requires a canonical StateStore envelope"
            )
        if current_state.payload_sha256 != intent.previous_state_payload_sha256:
            raise CanonicalLedgerInvariantError(
                "StateStore changed after durable intent preparation"
            )
        # Reject precision drift before any append can occur.
        for execution in intent.executions:
            self._row_for(execution)

        adapter = CanonicalLedgerEvidenceAdapter(self.path)
        with self._lock, self._process_lock():
            rows = adapter._read_rows() if self.path.exists() else ()
            adapter._verify_rows(rows)
            previous = intent.previous
            if len(rows) < previous.total_rows:
                raise CanonicalLedgerInvariantError(
                    "canonical ledger is behind the durable intent boundary"
                )
            prefix = rows[: previous.total_rows]
            if (
                _rows_sha256(prefix) != previous.ledger_sha256
                or (
                    str(prefix[-1].get("event_hash") or "") if prefix else ""
                )
                != previous.terminal_event_hash
            ):
                raise CanonicalLedgerInvariantError(
                    "canonical ledger prefix diverged from the durable intent"
                )
            if adapter._boundary_for(prefix, epoch_id=previous.epoch_id) != previous:
                raise CanonicalLedgerInvariantError(
                    "canonical ledger boundary diverged from the durable intent"
                )

            appended = rows[previous.total_rows :]
            if len(appended) > len(intent.executions):
                raise CanonicalLedgerInvariantError(
                    "canonical ledger advanced beyond the durable intent"
                )
            expected_previous_hash = previous.terminal_event_hash
            for row, execution in zip(appended, intent.executions):
                expected_row = self._materialize_row(
                    execution,
                    epoch_id=previous.epoch_id,
                    previous_hash=expected_previous_hash,
                )
                if dict(row) != dict(expected_row):
                    raise CanonicalLedgerInvariantError(
                        "partial canonical append diverged from the durable intent"
                    )
                expected_previous_hash = str(expected_row["event_hash"])

            previous_hash = expected_previous_hash
            for execution in intent.executions[len(appended) :]:
                row = self._materialize_row(
                    execution,
                    epoch_id=previous.epoch_id,
                    previous_hash=previous_hash,
                )
                self._append_row_locked(row)
                previous_hash = str(row["event_hash"])

            return adapter.prove_intent(
                intent=intent,
                current_state=current_state,
            )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.ledger_writer.SandboxLedgerIntentWriter",
                "authority": cls.authority,
                "runtime_registered": cls.runtime_registered,
                "production_write_enabled": cls.production_write_enabled,
                "sandbox_write_enabled": True,
                "places_orders": cls.places_orders,
                "accepts_durable_append_intent": True,
                "idempotent_partial_append_recovery": True,
                "append_call_can_override_intent_identity": False,
                "commits_state_store": False,
                "production_writer_connected": False,
                "version": VERSION,
            }
        )

