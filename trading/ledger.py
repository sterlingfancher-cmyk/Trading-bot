"""Read-only canonical-ledger evidence adapter for Issue #84.

The production JSONL ledger remains owned by ``canonical_execution_ledger``.
This module only validates an explicit caller-provided ledger path and derives
the typed append proof consumed by the shadow single-owner transaction.  It
does not append, rewrite, register with the runtime, read environment state, or
hold order authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from trading.accounting import ExecutionSnapshot
from trading.state_store import CanonicalStateEnvelope
from trading.transaction import LedgerAppendProof

VERSION = "stable-paper-core-v3-ledger-evidence-adapter-2026-10-10-v1"
AUTHORITY = "shadow_only"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CanonicalLedgerInvariantError(ValueError):
    """Raised when an observed ledger cannot prove one exact append."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _rows_sha256(rows: Tuple[Mapping[str, Any], ...]) -> str:
    payload = "".join(_canonical_json(row) + "\n" for row in rows)
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerBoundary:
    epoch_id: str
    total_rows: int
    epoch_rows: int
    ledger_sha256: str
    terminal_event_hash: str
    chain_valid: bool = True
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        epoch_id = str(self.epoch_id or "").strip()
        if not epoch_id:
            raise CanonicalLedgerInvariantError("ledger boundary requires an epoch id")
        for name in ("total_rows", "epoch_rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CanonicalLedgerInvariantError(
                    f"{name} must be a non-negative integer"
                )
        if self.epoch_rows > self.total_rows:
            raise CanonicalLedgerInvariantError(
                "epoch rows cannot exceed total ledger rows"
            )
        digest = str(self.ledger_sha256 or "").lower().strip()
        terminal = str(self.terminal_event_hash or "").lower().strip()
        if not _SHA256.fullmatch(digest):
            raise CanonicalLedgerInvariantError(
                "ledger boundary requires an exact SHA-256 digest"
            )
        if self.total_rows == 0:
            if terminal:
                raise CanonicalLedgerInvariantError(
                    "empty ledger boundary cannot have a terminal event hash"
                )
        elif not _SHA256.fullmatch(terminal):
            raise CanonicalLedgerInvariantError(
                "non-empty ledger boundary requires an exact terminal event hash"
            )
        if self.chain_valid is not True:
            raise CanonicalLedgerInvariantError("ledger boundary must be chain-valid")
        if self.authority != AUTHORITY or self.version != VERSION:
            raise CanonicalLedgerInvariantError(
                "ledger boundary must remain shadow-only"
            )
        object.__setattr__(self, "epoch_id", epoch_id)
        object.__setattr__(self, "ledger_sha256", digest)
        object.__setattr__(self, "terminal_event_hash", terminal)


@dataclass(frozen=True)
class LedgerAppendObservation:
    previous: LedgerBoundary
    current: LedgerBoundary
    executions: Tuple[ExecutionSnapshot, ...]
    proof: LedgerAppendProof
    runtime_registration: bool = False
    production_writes: bool = False
    order_authority: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        executions = tuple(self.executions)
        if self.previous.epoch_id != self.current.epoch_id:
            raise CanonicalLedgerInvariantError("append observation changed epoch")
        if (
            self.proof.previous_total_rows != self.previous.total_rows
            or self.proof.previous_epoch_rows != self.previous.epoch_rows
            or self.proof.previous_sha256 != self.previous.ledger_sha256
            or self.proof.next_total_rows != self.current.total_rows
            or self.proof.next_epoch_rows != self.current.epoch_rows
            or self.proof.next_sha256 != self.current.ledger_sha256
        ):
            raise CanonicalLedgerInvariantError(
                "append observation boundary does not match its typed proof"
            )
        if tuple(row.execution_id for row in executions) != (
            self.proof.appended_execution_ids
        ):
            raise CanonicalLedgerInvariantError(
                "append observation execution identity mismatch"
            )
        if self.authority != AUTHORITY or any(
            (self.runtime_registration, self.production_writes, self.order_authority)
        ):
            raise CanonicalLedgerInvariantError(
                "ledger evidence adapter cannot hold runtime authority"
            )
        object.__setattr__(self, "executions", executions)


class CanonicalLedgerEvidenceAdapter:
    """Prove a settled append from an explicit immutable ledger boundary."""

    authority = AUTHORITY
    runtime_registered = False
    production_writes = False
    reads_environment = False
    places_orders = False

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _read_rows(self) -> Tuple[Mapping[str, Any], ...]:
        if not self.path.is_file():
            raise CanonicalLedgerInvariantError("canonical ledger file is missing")
        rows = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    text = line.strip()
                    if not text:
                        raise CanonicalLedgerInvariantError(
                            f"canonical ledger line {line_number} is empty"
                        )
                    row = json.loads(text)
                    if not isinstance(row, dict):
                        raise CanonicalLedgerInvariantError(
                            f"canonical ledger line {line_number} is not an object"
                        )
                    rows.append(MappingProxyType(dict(row)))
        except CanonicalLedgerInvariantError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CanonicalLedgerInvariantError(
                f"canonical ledger is unreadable: {type(exc).__name__}"
            ) from exc
        return tuple(rows)

    @staticmethod
    def _verify_rows(rows: Tuple[Mapping[str, Any], ...]) -> None:
        previous_hash = ""
        execution_ids = set()
        for sequence, row in enumerate(rows, start=1):
            observed_previous = str(row.get("previous_event_hash") or "")
            if observed_previous != previous_hash:
                raise CanonicalLedgerInvariantError(
                    f"ledger row {sequence} previous hash mismatch"
                )
            body = dict(row)
            event_hash = str(body.pop("event_hash", "") or "").lower().strip()
            body.pop("previous_event_hash", None)
            expected = sha256(
                (previous_hash + "|" + _canonical_json(body)).encode("utf-8")
            ).hexdigest()
            if event_hash != expected:
                raise CanonicalLedgerInvariantError(
                    f"ledger row {sequence} event hash mismatch"
                )
            execution_id = str(row.get("execution_id") or "").strip()
            if not execution_id or execution_id in execution_ids:
                raise CanonicalLedgerInvariantError(
                    f"ledger row {sequence} execution id is missing or duplicated"
                )
            execution_ids.add(execution_id)
            previous_hash = event_hash

    @staticmethod
    def _boundary_for(
        rows: Tuple[Mapping[str, Any], ...], *, epoch_id: str
    ) -> LedgerBoundary:
        epoch_rows = sum(
            1
            for row in rows
            if str(row.get("accounting_epoch_id") or "").strip() == epoch_id
        )
        return LedgerBoundary(
            epoch_id=epoch_id,
            total_rows=len(rows),
            epoch_rows=epoch_rows,
            ledger_sha256=_rows_sha256(rows),
            terminal_event_hash=(
                str(rows[-1].get("event_hash") or "") if rows else ""
            ),
        )

    def observe(self, *, epoch_id: str) -> LedgerBoundary:
        normalized_epoch = str(epoch_id or "").strip()
        if not normalized_epoch:
            raise CanonicalLedgerInvariantError("epoch_id is required")
        rows = self._read_rows()
        self._verify_rows(rows)
        return self._boundary_for(rows, epoch_id=normalized_epoch)

    def prove_append(
        self,
        *,
        previous: LedgerBoundary,
        current_state: CanonicalStateEnvelope,
    ) -> LedgerAppendObservation:
        if not isinstance(previous, LedgerBoundary):
            raise CanonicalLedgerInvariantError(
                "append proof requires a typed previous boundary"
            )
        if not isinstance(current_state, CanonicalStateEnvelope):
            raise CanonicalLedgerInvariantError(
                "append proof requires a canonical StateStore envelope"
            )
        snapshot = current_state.snapshot()
        accounting_epoch = snapshot.portfolio.accounting_epoch
        if (
            snapshot.execution_ledger_rows != previous.total_rows
            or snapshot.execution_epoch_rows != previous.epoch_rows
            or snapshot.execution_chain_valid is not True
            or accounting_epoch is None
            or accounting_epoch.epoch_id != previous.epoch_id
        ):
            raise CanonicalLedgerInvariantError(
                "previous boundary does not match the current StateStore revision"
            )

        rows = self._read_rows()
        self._verify_rows(rows)
        if len(rows) <= previous.total_rows:
            raise CanonicalLedgerInvariantError(
                "canonical ledger has no new settled append"
            )
        prefix = rows[: previous.total_rows]
        if _rows_sha256(prefix) != previous.ledger_sha256:
            raise CanonicalLedgerInvariantError(
                "canonical ledger prefix changed after the previous boundary"
            )
        terminal = str(prefix[-1].get("event_hash") or "") if prefix else ""
        if terminal != previous.terminal_event_hash:
            raise CanonicalLedgerInvariantError(
                "canonical ledger terminal boundary changed"
            )
        if self._boundary_for(prefix, epoch_id=previous.epoch_id).epoch_rows != (
            previous.epoch_rows
        ):
            raise CanonicalLedgerInvariantError(
                "canonical ledger epoch prefix changed"
            )

        appended = rows[previous.total_rows :]
        executions = []
        for sequence, row in enumerate(appended, start=previous.total_rows + 1):
            if str(row.get("accounting_epoch_id") or "").strip() != previous.epoch_id:
                raise CanonicalLedgerInvariantError(
                    "settled append crossed the accounting epoch boundary"
                )
            action = str(row.get("action") or "").lower().strip()
            if action == "partial_exit":
                action = "exit"
            if action not in {"entry", "exit"}:
                raise CanonicalLedgerInvariantError(
                    f"unsupported canonical execution action at row {sequence}"
                )
            executions.append(
                ExecutionSnapshot(
                    sequence=sequence,
                    symbol=row.get("symbol"),
                    event=action,
                    side=row.get("side"),
                    quantity=row.get("shares"),
                    price=row.get("price"),
                    timestamp=str(row.get("recorded_local") or ""),
                    execution_id=row.get("execution_id"),
                )
            )

        current = self._boundary_for(rows, epoch_id=previous.epoch_id)
        proof = LedgerAppendProof(
            previous_total_rows=previous.total_rows,
            next_total_rows=current.total_rows,
            previous_epoch_rows=previous.epoch_rows,
            next_epoch_rows=current.epoch_rows,
            previous_state_payload_sha256=current_state.payload_sha256,
            previous_sha256=previous.ledger_sha256,
            next_sha256=current.ledger_sha256,
            appended_execution_ids=tuple(row.execution_id for row in executions),
            chain_valid=True,
        )
        return LedgerAppendObservation(
            previous=previous,
            current=current,
            executions=tuple(executions),
            proof=proof,
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.ledger.CanonicalLedgerEvidenceAdapter",
                "authority": cls.authority,
                "runtime_registered": cls.runtime_registered,
                "production_writes": cls.production_writes,
                "reads_environment": cls.reads_environment,
                "places_orders": cls.places_orders,
                "validates_full_hash_chain": True,
                "proves_immutable_prefix": True,
                "version": VERSION,
            }
        )
