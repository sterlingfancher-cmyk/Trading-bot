"""Shadow-only canonical StateStore for Stable Paper Core v3 Stage D.

This module defines the future single persistence boundary without registering it
with the production runtime. Production writes remain disabled. The store can be
exercised only against an explicit caller-provided sandbox path so restart and
atomic-commit invariants can be proven before any authoritative cutover.
"""
from __future__ import annotations

from dataclasses import dataclass
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

VERSION = "stable-paper-core-v3-stage-d-state-store-2026-08-20-v1"
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
        object.__setattr__(self, "payload", MappingProxyType(plain_payload))

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
        return _snapshot_from_payload(self.payload)


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

    def read_sandbox(self) -> CanonicalStateEnvelope:
        self._assert_sandbox()
        with self._lock:
            return self._read_envelope_file(self.path)

    def commit_sandbox(self, envelope: CanonicalStateEnvelope) -> None:
        self._assert_sandbox()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                current = self._read_envelope_file(self.path)
                if envelope.revision <= current.revision:
                    raise StateStoreInvariantError(
                        "canonical revision must increase monotonically"
                    )
                backup_tmp = self.backup_path.with_name(
                    f".{self.backup_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
                )
                backup_tmp.write_bytes(self.path.read_bytes())
                with backup_tmp.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(backup_tmp, self.backup_path)

            temp_path = self.path.with_name(
                f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with temp_path.open("wb") as handle:
                handle.write(_canonical_bytes(envelope.to_dict()))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            try:
                directory_fd = os.open(str(self.path.parent), os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except (AttributeError, OSError):
                pass

            persisted = self._read_envelope_file(self.path)
            if persisted.payload_sha256 != envelope.payload_sha256:
                raise StateStoreInvariantError("post-commit digest mismatch")
            if persisted.revision != envelope.revision:
                raise StateStoreInvariantError("post-commit revision mismatch")

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.state_store.CanonicalStateStore",
                "authority": cls.authority,
                "production_write_enabled": cls.production_write_enabled,
                "runtime_registered": cls.runtime_registered,
                "reads_environment": cls.reads_environment,
                "places_orders": cls.places_orders,
                "schema_version": SCHEMA_VERSION,
                "version": VERSION,
            }
        )
