"""Shadow-only canonical StateStore for Stable Paper Core v3 Stage D.

This module defines the future single persistence boundary without registering it
with the production runtime. Production writes remain disabled. The store can be
exercised only against an explicit caller-provided sandbox path so restart and
atomic-commit invariants can be proven before any authoritative cutover.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
from types import MappingProxyType
from typing import Any, Mapping

from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    PositionSnapshot,
    RiskStateSnapshot,
)

VERSION = "stable-paper-core-v3-stage-d-rollback-receipt-2026-09-20-v3"
AUTHORITY = "shadow_only"
SCHEMA_VERSION = 1


class StateStoreInvariantError(ValueError):
    """Raised when a canonical state envelope cannot be trusted."""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    """Recursively detach and freeze canonical envelope payloads."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _plain(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_payload(payload: Mapping[str, Any]) -> str:
    return sha256(_canonical_bytes(payload)).hexdigest()


def _snapshot_payload(snapshot: CanonicalStateSnapshot) -> dict[str, Any]:
    epoch = snapshot.portfolio.accounting_epoch
    return {
        "portfolio": {
            "cash": snapshot.portfolio.cash,
            "equity": snapshot.portfolio.equity,
            "realized_total": snapshot.portfolio.realized_total,
            "realized_today": snapshot.portfolio.realized_today,
            "unrealized_pnl": snapshot.portfolio.unrealized_pnl,
            "positions": [
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "entry_price": row.entry_price,
                    "mark_price": row.mark_price,
                }
                for row in snapshot.portfolio.positions
            ],
            "accounting_epoch": (
                {
                    "epoch_id": epoch.epoch_id,
                    "baseline_type": epoch.baseline_type,
                    "historical_evidence_archived": epoch.historical_evidence_archived,
                    "validation_hold": epoch.validation_hold,
                }
                if epoch is not None
                else None
            ),
        },
        "risk": {
            "date": snapshot.risk.date,
            "day_start_equity": snapshot.risk.day_start_equity,
            "day_peak_equity": snapshot.risk.day_peak_equity,
            "daily_loss_fraction": snapshot.risk.daily_loss_fraction,
            "intraday_drawdown_fraction": snapshot.risk.intraday_drawdown_fraction,
            "halted": snapshot.risk.halted,
            "halt_reason": snapshot.risk.halt_reason,
        },
        "execution_ledger_rows": snapshot.execution_ledger_rows,
        "execution_epoch_rows": snapshot.execution_epoch_rows,
        "execution_chain_valid": bool(snapshot.execution_chain_valid),
        "source_version": snapshot.source_version,
    }


def _snapshot_from_payload(payload: Mapping[str, Any]) -> CanonicalStateSnapshot:
    portfolio_raw = payload.get("portfolio")
    risk_raw = payload.get("risk")
    if not isinstance(portfolio_raw, Mapping) or not isinstance(risk_raw, Mapping):
        raise StateStoreInvariantError("canonical payload requires portfolio and risk mappings")

    positions_raw = portfolio_raw.get("positions", [])
    if not isinstance(positions_raw, list):
        raise StateStoreInvariantError("positions must be a list")
    positions = tuple(
        PositionSnapshot(
            symbol=row.get("symbol"),
            side=row.get("side"),
            quantity=row.get("quantity"),
            entry_price=row.get("entry_price"),
            mark_price=row.get("mark_price"),
        )
        for row in positions_raw
        if isinstance(row, Mapping)
    )
    if len(positions) != len(positions_raw):
        raise StateStoreInvariantError("every position row must be a mapping")

    epoch_raw = portfolio_raw.get("accounting_epoch")
    epoch = None
    if epoch_raw is not None:
        if not isinstance(epoch_raw, Mapping):
            raise StateStoreInvariantError("accounting_epoch must be a mapping or null")
        epoch = AccountingEpochSnapshot(
            epoch_id=epoch_raw.get("epoch_id"),
            baseline_type=epoch_raw.get("baseline_type"),
            historical_evidence_archived=bool(epoch_raw.get("historical_evidence_archived")),
            validation_hold=bool(epoch_raw.get("validation_hold")),
        )

    portfolio = PortfolioSnapshot(
        cash=portfolio_raw.get("cash"),
        equity=portfolio_raw.get("equity"),
        realized_total=portfolio_raw.get("realized_total"),
        realized_today=portfolio_raw.get("realized_today"),
        unrealized_pnl=portfolio_raw.get("unrealized_pnl"),
        positions=positions,
        accounting_epoch=epoch,
    )
    risk = RiskStateSnapshot(
        date=risk_raw.get("date"),
        day_start_equity=risk_raw.get("day_start_equity"),
        day_peak_equity=risk_raw.get("day_peak_equity"),
        daily_loss_fraction=risk_raw.get("daily_loss_fraction"),
        intraday_drawdown_fraction=risk_raw.get("intraday_drawdown_fraction"),
        halted=bool(risk_raw.get("halted")),
        halt_reason=str(risk_raw.get("halt_reason") or ""),
    )
    return CanonicalStateSnapshot(
        portfolio=portfolio,
        risk=risk,
        execution_ledger_rows=int(payload.get("execution_ledger_rows", -1)),
        execution_epoch_rows=int(
            payload.get("execution_epoch_rows", payload.get("execution_ledger_rows", -1))
        ),
        execution_chain_valid=bool(payload.get("execution_chain_valid")),
        source_version=str(payload.get("source_version") or ""),
    )


@dataclass(frozen=True)
class CanonicalStateEnvelope:
    revision: int
    created_at: str
    payload: Mapping[str, Any]
    payload_sha256: str
    schema_version: int = SCHEMA_VERSION
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        if int(self.revision) < 0:
            raise StateStoreInvariantError("revision must be non-negative")
        if int(self.schema_version) != SCHEMA_VERSION:
            raise StateStoreInvariantError("unexpected state schema version")
        if self.authority != AUTHORITY:
            raise StateStoreInvariantError("Stage D envelope must remain shadow-only")
        if not str(self.created_at or "").strip():
            raise StateStoreInvariantError("created_at is required")
        plain_payload = _plain(self.payload)
        expected = _digest_payload(plain_payload)
        if str(self.payload_sha256) != expected:
            raise StateStoreInvariantError("payload digest mismatch")
        object.__setattr__(self, "revision", int(self.revision))
        object.__setattr__(self, "payload", _freeze(plain_payload))

    @classmethod
    def build(
        cls,
        *,
        snapshot: CanonicalStateSnapshot,
        revision: int,
        created_at: str,
    ) -> "CanonicalStateEnvelope":
        payload = _snapshot_payload(snapshot)
        return cls(
            revision=revision,
            created_at=created_at,
            payload=payload,
            payload_sha256=_digest_payload(payload),
        )

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "authority": self.authority,
                "version": self.version,
                "revision": self.revision,
                "created_at": self.created_at,
                "payload_sha256": self.payload_sha256,
                "payload": _plain(self.payload),
            }
        )

    def snapshot(self) -> CanonicalStateSnapshot:
        return _snapshot_from_payload(_plain(self.payload))


@dataclass(frozen=True)
class RollbackDrillReceipt:
    """Typed proof emitted only after a complete sandbox rollback drill."""

    baseline_revision: int
    canary_revision: int
    restored_revision: int
    baseline_payload_sha256: str
    canary_payload_sha256: str
    restored_payload_sha256: str
    archived_baseline_revision: int
    archived_baseline_payload_sha256: str
    backup_canary_revision: int
    backup_canary_payload_sha256: str
    archive_immutable: bool
    restart_parity_passed: bool
    single_writer_exclusivity_passed: bool
    runtime_registration: bool = False
    production_state_writes: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        revisions = (
            self.baseline_revision,
            self.canary_revision,
            self.restored_revision,
            self.archived_baseline_revision,
            self.backup_canary_revision,
        )
        if any(isinstance(value, bool) for value in revisions):
            raise StateStoreInvariantError("rollback receipt revisions must be integers")
        try:
            baseline, canary, restored, archived, backup = map(int, revisions)
        except (TypeError, ValueError) as exc:
            raise StateStoreInvariantError(
                "rollback receipt revisions must be integers"
            ) from exc
        if baseline < 0 or canary != baseline + 1 or restored != canary + 1:
            raise StateStoreInvariantError("rollback receipt revision lineage mismatch")
        if archived != baseline or backup != canary:
            raise StateStoreInvariantError(
                "rollback receipt archive/backup lineage mismatch"
            )
        object.__setattr__(self, "baseline_revision", baseline)
        object.__setattr__(self, "canary_revision", canary)
        object.__setattr__(self, "restored_revision", restored)
        object.__setattr__(self, "archived_baseline_revision", archived)
        object.__setattr__(self, "backup_canary_revision", backup)

        digest_names = (
            "baseline_payload_sha256",
            "canary_payload_sha256",
            "restored_payload_sha256",
            "archived_baseline_payload_sha256",
            "backup_canary_payload_sha256",
        )
        digests = {}
        for name in digest_names:
            value = str(getattr(self, name) or "").lower().strip()
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise StateStoreInvariantError(
                    f"{name} must be an exact SHA-256 digest"
                )
            object.__setattr__(self, name, value)
            digests[name] = value
        if not (
            digests["baseline_payload_sha256"]
            == digests["archived_baseline_payload_sha256"]
            == digests["restored_payload_sha256"]
        ):
            raise StateStoreInvariantError("rollback receipt restored payload mismatch")
        if not (
            digests["canary_payload_sha256"]
            == digests["backup_canary_payload_sha256"]
        ):
            raise StateStoreInvariantError("rollback receipt canary backup mismatch")
        if digests["canary_payload_sha256"] == digests["baseline_payload_sha256"]:
            raise StateStoreInvariantError("rollback drill requires a distinct canary payload")
        if not all(
            (
                self.archive_immutable,
                self.restart_parity_passed,
                self.single_writer_exclusivity_passed,
            )
        ):
            raise StateStoreInvariantError("rollback receipt requires complete drill proof")
        if (
            self.authority != AUTHORITY
            or self.runtime_registration
            or self.production_state_writes
        ):
            raise StateStoreInvariantError("rollback receipt must remain shadow-only")


class CanonicalStateStore:
    """Future single-owner StateStore; production authority is intentionally off."""

    authority = AUTHORITY
    production_write_enabled = False
    runtime_registered = False
    reads_environment = False
    places_orders = False

    def __init__(self, path: Path | str, *, sandbox_io_enabled: bool = False):
        self.path = Path(path)
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self.sandbox_io_enabled = bool(sandbox_io_enabled)
        self._lock = threading.RLock()

    @staticmethod
    def prepare(
        *, snapshot: CanonicalStateSnapshot, revision: int, created_at: str
    ) -> CanonicalStateEnvelope:
        return CanonicalStateEnvelope.build(
            snapshot=snapshot,
            revision=revision,
            created_at=created_at,
        )

    def _assert_sandbox(self) -> None:
        if not self.sandbox_io_enabled:
            raise PermissionError(
                "Stage D production writes are disabled; explicit sandbox_io_enabled=True is required"
            )

    def _read_envelope_file(self, path: Path) -> CanonicalStateEnvelope:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise StateStoreInvariantError("state envelope root must be an object")
        return CanonicalStateEnvelope(
            schema_version=raw.get("schema_version"),
            authority=raw.get("authority"),
            version=raw.get("version"),
            revision=raw.get("revision"),
            created_at=raw.get("created_at"),
            payload_sha256=raw.get("payload_sha256"),
            payload=raw.get("payload") if isinstance(raw.get("payload"), Mapping) else {},
        )

    @contextmanager
    def _process_lock(self, *, exclusive: bool):
        """Serialize sandbox access across store instances and processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
            )
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def read_sandbox(self) -> CanonicalStateEnvelope:
        self._assert_sandbox()
        with self._lock:
            with self._process_lock(exclusive=False):
                return self._read_envelope_file(self.path)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            directory_fd = os.open(str(path), os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (AttributeError, OSError):
            pass

    def _write_bytes_atomic(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with temp_path.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(path.parent)
        finally:
            temp_path.unlink(missing_ok=True)

    def _commit_locked(
        self,
        envelope: CanonicalStateEnvelope,
        *,
        current: CanonicalStateEnvelope | None = None,
    ) -> None:
        if self.path.exists():
            current = current or self._read_envelope_file(self.path)
            if envelope.revision <= current.revision:
                raise StateStoreInvariantError(
                    "canonical revision must increase monotonically"
                )
            self._write_bytes_atomic(self.backup_path, self.path.read_bytes())

        self._write_bytes_atomic(self.path, _canonical_bytes(envelope.to_dict()))
        persisted = self._read_envelope_file(self.path)
        if persisted.payload_sha256 != envelope.payload_sha256:
            raise StateStoreInvariantError("post-commit digest mismatch")
        if persisted.revision != envelope.revision:
            raise StateStoreInvariantError("post-commit revision mismatch")

    def commit_sandbox(self, envelope: CanonicalStateEnvelope) -> None:
        self._assert_sandbox()
        with self._lock:
            with self._process_lock(exclusive=True):
                self._commit_locked(envelope)

    def archive_sandbox(self, archive_path: Path | str) -> CanonicalStateEnvelope:
        """Create one immutable rollback archive from the current sandbox state."""
        self._assert_sandbox()
        archive = Path(archive_path)
        if archive in {self.path, self.backup_path, self.lock_path}:
            raise StateStoreInvariantError("rollback archive path must be distinct")
        with self._lock:
            with self._process_lock(exclusive=True):
                if archive.exists():
                    raise FileExistsError("rollback archive is immutable")
                current = self._read_envelope_file(self.path)
                self._write_bytes_atomic(archive, _canonical_bytes(current.to_dict()))
                persisted = self._read_envelope_file(archive)
                if persisted.revision != current.revision:
                    raise StateStoreInvariantError("rollback archive revision mismatch")
                if persisted.payload_sha256 != current.payload_sha256:
                    raise StateStoreInvariantError("rollback archive digest mismatch")
                return persisted

    def restore_sandbox(
        self,
        archive_path: Path | str,
        *,
        expected_current_revision: int,
        created_at: str,
    ) -> CanonicalStateEnvelope:
        """Restore archived payload as a new monotonic sandbox revision."""
        self._assert_sandbox()
        if isinstance(expected_current_revision, bool) or not isinstance(
            expected_current_revision, int
        ):
            raise StateStoreInvariantError("expected_current_revision must be an integer")
        archive = Path(archive_path)
        if archive in {self.path, self.backup_path, self.lock_path}:
            raise StateStoreInvariantError("rollback archive path must be distinct")
        with self._lock:
            with self._process_lock(exclusive=True):
                current = self._read_envelope_file(self.path)
                if current.revision != expected_current_revision:
                    raise StateStoreInvariantError(
                        "current revision changed before rollback restore"
                    )
                archived = self._read_envelope_file(archive)
                restored = CanonicalStateEnvelope(
                    revision=current.revision + 1,
                    created_at=created_at,
                    payload=archived.payload,
                    payload_sha256=archived.payload_sha256,
                )
                self._commit_locked(restored, current=current)
                persisted = self._read_envelope_file(self.path)
                if persisted.payload_sha256 != archived.payload_sha256:
                    raise StateStoreInvariantError("rollback restore payload mismatch")
                return persisted

    def run_rollback_drill_sandbox(
        self,
        archive_path: Path | str,
        *,
        canary_envelope: CanonicalStateEnvelope,
        restored_created_at: str,
    ) -> RollbackDrillReceipt:
        """Archive, canary, and restore one sandbox under a single writer lock."""
        self._assert_sandbox()
        archive = Path(archive_path)
        if archive in {self.path, self.backup_path, self.lock_path}:
            raise StateStoreInvariantError("rollback archive path must be distinct")
        with self._lock:
            with self._process_lock(exclusive=True):
                if archive.exists():
                    raise FileExistsError("rollback archive is immutable")
                baseline = self._read_envelope_file(self.path)
                if canary_envelope.revision != baseline.revision + 1:
                    raise StateStoreInvariantError(
                        "rollback canary must be the next canonical revision"
                    )
                if canary_envelope.payload_sha256 == baseline.payload_sha256:
                    raise StateStoreInvariantError(
                        "rollback canary payload must differ from baseline"
                    )

                self._write_bytes_atomic(archive, _canonical_bytes(baseline.to_dict()))
                archive_bytes = archive.read_bytes()
                archived = self._read_envelope_file(archive)
                self._commit_locked(canary_envelope, current=baseline)
                restored = CanonicalStateEnvelope(
                    revision=canary_envelope.revision + 1,
                    created_at=restored_created_at,
                    payload=archived.payload,
                    payload_sha256=archived.payload_sha256,
                )
                self._commit_locked(restored, current=canary_envelope)
                persisted = self._read_envelope_file(self.path)
                backup = self._read_envelope_file(self.backup_path)
                archive_after = self._read_envelope_file(archive)
                archive_immutable = archive.read_bytes() == archive_bytes

        restarted = CanonicalStateStore(
            self.path, sandbox_io_enabled=True
        ).read_sandbox()
        return RollbackDrillReceipt(
            baseline_revision=baseline.revision,
            canary_revision=canary_envelope.revision,
            restored_revision=persisted.revision,
            baseline_payload_sha256=baseline.payload_sha256,
            canary_payload_sha256=canary_envelope.payload_sha256,
            restored_payload_sha256=persisted.payload_sha256,
            archived_baseline_revision=archive_after.revision,
            archived_baseline_payload_sha256=archive_after.payload_sha256,
            backup_canary_revision=backup.revision,
            backup_canary_payload_sha256=backup.payload_sha256,
            archive_immutable=archive_immutable,
            restart_parity_passed=(
                restarted.revision == persisted.revision
                and restarted.payload_sha256 == persisted.payload_sha256
            ),
            single_writer_exclusivity_passed=True,
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.state_store.CanonicalStateStore",
                "authority": cls.authority,
                "production_write_enabled": cls.production_write_enabled,
                "runtime_registered": cls.runtime_registered,
                "interprocess_locking": True,
                "reads_environment": cls.reads_environment,
                "places_orders": cls.places_orders,
                "schema_version": SCHEMA_VERSION,
                "version": VERSION,
            }
        )
