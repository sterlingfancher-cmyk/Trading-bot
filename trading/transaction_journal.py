"""Sandbox-only write-ahead journal for the Issue #84 cutover transaction.

The canonical ledger is append-only, so a crash after its append cannot be
repaired by deleting the row.  This journal proves the safe recovery rule:
before the append, abandon the prepared transaction; after the append, finish
exactly one bound StateStore revision.  It is deliberately unregistered and
requires explicit sandbox I/O.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from trading.state_store import CanonicalStateStore
from trading.transaction import CanonicalTransactionReceipt

VERSION = "stable-paper-core-v3-transaction-journal-2026-10-01-v1"
AUTHORITY = "shadow_only"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PHASES = frozenset(
    {"prepared", "ledger_settled", "state_committed", "aborted_before_append"}
)


class TransactionJournalInvariantError(ValueError):
    """Raised when journal, ledger, or StateStore evidence is inconsistent."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _exact_sha(value: object, name: str) -> str:
    normalized = str(value or "").lower().strip()
    if not _SHA256.fullmatch(normalized):
        raise TransactionJournalInvariantError(f"{name} must be an exact SHA-256")
    return normalized


@dataclass(frozen=True)
class ObservedLedgerState:
    total_rows: int
    epoch_rows: int
    ledger_sha256: str
    chain_valid: bool
    execution_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("total_rows", "epoch_rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TransactionJournalInvariantError(
                    f"{name} must be a non-negative integer"
                )
        if self.epoch_rows > self.total_rows:
            raise TransactionJournalInvariantError(
                "epoch rows cannot exceed total ledger rows"
            )
        object.__setattr__(
            self, "ledger_sha256", _exact_sha(self.ledger_sha256, "ledger_sha256")
        )
        ids = tuple(str(value or "").strip() for value in self.execution_ids)
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise TransactionJournalInvariantError(
                "observed execution ids must be non-empty and unique"
            )
        if self.chain_valid is not True:
            raise TransactionJournalInvariantError("observed ledger chain must be valid")
        object.__setattr__(self, "execution_ids", ids)


@dataclass(frozen=True)
class TransactionJournalRecord:
    transaction_id: str
    phase: str
    previous_revision: int
    next_revision: int
    previous_state_sha256: str
    next_state_sha256: str
    previous_total_rows: int
    next_total_rows: int
    previous_epoch_rows: int
    next_epoch_rows: int
    previous_ledger_sha256: str
    next_ledger_sha256: str
    execution_ids: Tuple[str, ...]
    created_at: str
    updated_at: str
    record_sha256: str = ""
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        transaction_id = str(self.transaction_id or "").strip()
        phase = str(self.phase or "").strip()
        if not transaction_id:
            raise TransactionJournalInvariantError("transaction_id is required")
        if phase not in _PHASES:
            raise TransactionJournalInvariantError("unexpected transaction phase")
        if self.authority != AUTHORITY or self.version != VERSION:
            raise TransactionJournalInvariantError("journal must remain shadow-only")
        for name in (
            "previous_revision",
            "next_revision",
            "previous_total_rows",
            "next_total_rows",
            "previous_epoch_rows",
            "next_epoch_rows",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TransactionJournalInvariantError(
                    f"{name} must be a non-negative integer"
                )
        if self.next_revision != self.previous_revision + 1:
            raise TransactionJournalInvariantError("journal revision lineage mismatch")
        execution_ids = tuple(str(value or "").strip() for value in self.execution_ids)
        if not execution_ids or any(not value for value in execution_ids):
            raise TransactionJournalInvariantError("journal execution ids are required")
        if self.next_total_rows - self.previous_total_rows != len(execution_ids):
            raise TransactionJournalInvariantError("journal total-row lineage mismatch")
        if self.next_epoch_rows - self.previous_epoch_rows != len(execution_ids):
            raise TransactionJournalInvariantError("journal epoch-row lineage mismatch")
        for name in (
            "previous_state_sha256",
            "next_state_sha256",
            "previous_ledger_sha256",
            "next_ledger_sha256",
        ):
            object.__setattr__(self, name, _exact_sha(getattr(self, name), name))
        if not str(self.created_at or "").strip() or not str(self.updated_at or "").strip():
            raise TransactionJournalInvariantError("journal timestamps are required")
        object.__setattr__(self, "transaction_id", transaction_id)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "execution_ids", execution_ids)
        expected = self.digest()
        supplied = str(self.record_sha256 or "").lower().strip()
        if supplied and supplied != expected:
            raise TransactionJournalInvariantError("journal record digest mismatch")
        object.__setattr__(self, "record_sha256", expected)

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "phase": self.phase,
            "previous_revision": self.previous_revision,
            "next_revision": self.next_revision,
            "previous_state_sha256": self.previous_state_sha256,
            "next_state_sha256": self.next_state_sha256,
            "previous_total_rows": self.previous_total_rows,
            "next_total_rows": self.next_total_rows,
            "previous_epoch_rows": self.previous_epoch_rows,
            "next_epoch_rows": self.next_epoch_rows,
            "previous_ledger_sha256": self.previous_ledger_sha256,
            "next_ledger_sha256": self.next_ledger_sha256,
            "execution_ids": list(self.execution_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "authority": self.authority,
            "version": self.version,
        }

    def digest(self) -> str:
        return sha256(_canonical_bytes(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType({**self.unsigned_dict(), "record_sha256": self.record_sha256})

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TransactionJournalRecord":
        return cls(
            transaction_id=raw.get("transaction_id"),
            phase=raw.get("phase"),
            previous_revision=raw.get("previous_revision"),
            next_revision=raw.get("next_revision"),
            previous_state_sha256=raw.get("previous_state_sha256"),
            next_state_sha256=raw.get("next_state_sha256"),
            previous_total_rows=raw.get("previous_total_rows"),
            next_total_rows=raw.get("next_total_rows"),
            previous_epoch_rows=raw.get("previous_epoch_rows"),
            next_epoch_rows=raw.get("next_epoch_rows"),
            previous_ledger_sha256=raw.get("previous_ledger_sha256"),
            next_ledger_sha256=raw.get("next_ledger_sha256"),
            execution_ids=tuple(raw.get("execution_ids") or ()),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
            record_sha256=raw.get("record_sha256"),
            authority=raw.get("authority"),
            version=raw.get("version"),
        )


@dataclass(frozen=True)
class TransactionRecoveryReceipt:
    transaction_id: str
    action: str
    phase: str
    previous_revision: int
    current_revision: int
    ledger_sha256: str
    state_payload_sha256: str
    replayed_state_commit: bool
    production_state_writes: bool = False
    runtime_registration: bool = False
    order_authority: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        if self.action not in {
            "aborted_before_append",
            "state_commit_replayed",
            "already_committed",
        }:
            raise TransactionJournalInvariantError("unexpected recovery action")
        if self.phase not in {"aborted_before_append", "state_committed"}:
            raise TransactionJournalInvariantError("recovery did not reach a terminal phase")
        if self.authority != AUTHORITY or any(
            (self.production_state_writes, self.runtime_registration, self.order_authority)
        ):
            raise TransactionJournalInvariantError("recovery receipt exceeds shadow authority")
        _exact_sha(self.ledger_sha256, "ledger_sha256")
        _exact_sha(self.state_payload_sha256, "state_payload_sha256")


class SandboxTransactionJournal:
    """Serialize and recover one sandbox transaction without ledger rewrites."""

    authority = AUTHORITY
    runtime_registered = False
    production_write_enabled = False
    places_orders = False

    def __init__(self, path: Path | str, *, sandbox_io_enabled: bool = False):
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self.sandbox_io_enabled = bool(sandbox_io_enabled)
        self._lock = threading.RLock()

    def _assert_sandbox(self) -> None:
        if not self.sandbox_io_enabled:
            raise PermissionError("transaction journal requires explicit sandbox I/O")

    @contextmanager
    def _process_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(str(path), os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_locked(self, record: TransactionJournalRecord) -> None:
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with temporary.open("wb") as handle:
                handle.write(_canonical_bytes(record.to_dict()))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self._fsync_directory(self.path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_locked(self) -> TransactionJournalRecord:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise TransactionJournalInvariantError("journal root must be an object")
        return TransactionJournalRecord.from_dict(raw)

    @staticmethod
    def _record_for(
        receipt: CanonicalTransactionReceipt,
        *,
        transaction_id: str,
        phase: str,
        created_at: str,
        updated_at: str,
    ) -> TransactionJournalRecord:
        return TransactionJournalRecord(
            transaction_id=transaction_id,
            phase=phase,
            previous_revision=receipt.previous_revision,
            next_revision=receipt.next_envelope.revision,
            previous_state_sha256=receipt.ledger.previous_state_payload_sha256,
            next_state_sha256=receipt.next_envelope.payload_sha256,
            previous_total_rows=receipt.ledger.previous_total_rows,
            next_total_rows=receipt.ledger.next_total_rows,
            previous_epoch_rows=receipt.ledger.previous_epoch_rows,
            next_epoch_rows=receipt.ledger.next_epoch_rows,
            previous_ledger_sha256=receipt.ledger.previous_sha256,
            next_ledger_sha256=receipt.ledger.next_sha256,
            execution_ids=receipt.ledger.appended_execution_ids,
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _assert_bound(
        record: TransactionJournalRecord, receipt: CanonicalTransactionReceipt
    ) -> None:
        expected = SandboxTransactionJournal._record_for(
            receipt,
            transaction_id=record.transaction_id,
            phase=record.phase,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        if expected.unsigned_dict() != record.unsigned_dict():
            raise TransactionJournalInvariantError(
                "journal is not bound to the supplied canonical transaction"
            )

    @staticmethod
    def _ledger_phase(
        record: TransactionJournalRecord, observed: ObservedLedgerState
    ) -> str:
        previous = (
            observed.total_rows == record.previous_total_rows
            and observed.epoch_rows == record.previous_epoch_rows
            and observed.ledger_sha256 == record.previous_ledger_sha256
            and not observed.execution_ids
        )
        following = (
            observed.total_rows == record.next_total_rows
            and observed.epoch_rows == record.next_epoch_rows
            and observed.ledger_sha256 == record.next_ledger_sha256
            and observed.execution_ids == record.execution_ids
        )
        if previous:
            return "previous"
        if following:
            return "next"
        raise TransactionJournalInvariantError(
            "observed ledger does not match either transaction boundary"
        )

    def begin(
        self,
        receipt: CanonicalTransactionReceipt,
        *,
        transaction_id: str,
        recorded_at: str,
    ) -> TransactionJournalRecord:
        self._assert_sandbox()
        candidate = self._record_for(
            receipt,
            transaction_id=transaction_id,
            phase="prepared",
            created_at=recorded_at,
            updated_at=recorded_at,
        )
        with self._lock, self._process_lock():
            if self.path.exists():
                current = self._read_locked()
                self._assert_bound(current, receipt)
                if current.transaction_id != candidate.transaction_id:
                    raise TransactionJournalInvariantError(
                        "another transaction already owns the journal"
                    )
                return current
            self._write_locked(candidate)
            return self._read_locked()

    def settle_ledger(
        self,
        receipt: CanonicalTransactionReceipt,
        observed: ObservedLedgerState,
        *,
        recorded_at: str,
    ) -> TransactionJournalRecord:
        self._assert_sandbox()
        with self._lock, self._process_lock():
            current = self._read_locked()
            self._assert_bound(current, receipt)
            if current.phase not in {"prepared", "ledger_settled"}:
                raise TransactionJournalInvariantError(
                    "ledger cannot settle from the current journal phase"
                )
            if self._ledger_phase(current, observed) != "next":
                raise TransactionJournalInvariantError("ledger append is not settled")
            settled = replace(current, phase="ledger_settled", updated_at=recorded_at, record_sha256="")
            self._write_locked(settled)
            return self._read_locked()

    def recover(
        self,
        receipt: CanonicalTransactionReceipt,
        observed: ObservedLedgerState,
        store: CanonicalStateStore,
        *,
        recorded_at: str,
    ) -> TransactionRecoveryReceipt:
        self._assert_sandbox()
        if not isinstance(store, CanonicalStateStore) or not store.sandbox_io_enabled:
            raise PermissionError("recovery requires an explicit sandbox StateStore")
        with self._lock, self._process_lock():
            current = self._read_locked()
            self._assert_bound(current, receipt)
            ledger_phase = self._ledger_phase(current, observed)
            state = store.read_sandbox()

            if current.phase == "prepared" and ledger_phase == "previous":
                if (
                    state.revision != current.previous_revision
                    or state.payload_sha256 != current.previous_state_sha256
                ):
                    raise TransactionJournalInvariantError(
                        "pre-append abort requires the exact previous StateStore revision"
                    )
                terminal = replace(
                    current,
                    phase="aborted_before_append",
                    updated_at=recorded_at,
                    record_sha256="",
                )
                self._write_locked(terminal)
                return TransactionRecoveryReceipt(
                    transaction_id=current.transaction_id,
                    action="aborted_before_append",
                    phase=terminal.phase,
                    previous_revision=current.previous_revision,
                    current_revision=state.revision,
                    ledger_sha256=observed.ledger_sha256,
                    state_payload_sha256=state.payload_sha256,
                    replayed_state_commit=False,
                )

            if current.phase == "aborted_before_append":
                raise TransactionJournalInvariantError(
                    "an aborted transaction cannot later acquire a ledger append"
                )
            if ledger_phase != "next":
                raise TransactionJournalInvariantError(
                    "StateStore commit requires the exact settled append"
                )

            replayed = False
            if (
                state.revision == current.previous_revision
                and state.payload_sha256 == current.previous_state_sha256
            ):
                store.commit_sandbox(receipt.next_envelope)
                state = store.read_sandbox()
                replayed = True
            elif not (
                state.revision == current.next_revision
                and state.payload_sha256 == current.next_state_sha256
            ):
                raise TransactionJournalInvariantError(
                    "StateStore is outside the transaction recovery boundary"
                )

            terminal = replace(
                current,
                phase="state_committed",
                updated_at=recorded_at,
                record_sha256="",
            )
            self._write_locked(terminal)
            return TransactionRecoveryReceipt(
                transaction_id=current.transaction_id,
                action="state_commit_replayed" if replayed else "already_committed",
                phase=terminal.phase,
                previous_revision=current.previous_revision,
                current_revision=state.revision,
                ledger_sha256=observed.ledger_sha256,
                state_payload_sha256=state.payload_sha256,
                replayed_state_commit=replayed,
            )

    def read_sandbox(self) -> TransactionJournalRecord:
        self._assert_sandbox()
        with self._lock, self._process_lock():
            return self._read_locked()

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.transaction_journal.SandboxTransactionJournal",
                "authority": cls.authority,
                "runtime_registered": cls.runtime_registered,
                "production_write_enabled": cls.production_write_enabled,
                "places_orders": cls.places_orders,
                "preappend_recovery": "abort_without_mutation",
                "postappend_recovery": "roll_forward_one_bound_state_revision",
                "rewrites_canonical_ledger": False,
                "interprocess_locking": True,
                "version": VERSION,
            }
        )
