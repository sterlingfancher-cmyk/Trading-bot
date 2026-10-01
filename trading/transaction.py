"""Fail-closed single-owner canonical transaction preparation for Issue #84.

This module composes the existing shadow accounting, protected valuation, risk,
and StateStore boundaries into one deterministic next-revision candidate.  It
does not append a ledger row, write a state file, register with the runtime, or
hold order/live/ML authority.  A caller must first provide proof that the
canonical ledger append already settled; production writer activation remains a
separate reviewed cutover.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Tuple

from trading.accounting import (
    BaselineSnapshot,
    CanonicalAccountingProjector,
    ExecutionSnapshot,
)
from trading.risk import RiskLimits, ShadowRiskEngine
from trading.state import CanonicalStateSnapshot, PortfolioSnapshot
from trading.state_store import CanonicalStateEnvelope, CanonicalStateStore
from trading.valuation import DeterministicValuationService, ProtectedMarkSnapshot

VERSION = "stable-paper-core-v3-single-owner-transaction-2026-10-01-v1"
AUTHORITY = "shadow_only"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CanonicalTransactionInvariantError(ValueError):
    """Raised when a candidate transaction is not bound to exact evidence."""


@dataclass(frozen=True)
class LedgerAppendProof:
    previous_total_rows: int
    next_total_rows: int
    previous_epoch_rows: int
    next_epoch_rows: int
    previous_state_payload_sha256: str
    previous_sha256: str
    next_sha256: str
    appended_execution_ids: Tuple[str, ...]
    chain_valid: bool

    def __post_init__(self) -> None:
        integer_fields = (
            "previous_total_rows",
            "next_total_rows",
            "previous_epoch_rows",
            "next_epoch_rows",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CanonicalTransactionInvariantError(
                    f"{name} must be a non-negative integer"
                )
        execution_ids = tuple(str(row or "").strip() for row in self.appended_execution_ids)
        if not execution_ids or any(not row for row in execution_ids):
            raise CanonicalTransactionInvariantError(
                "ledger append proof requires execution ids"
            )
        if len(execution_ids) != len(set(execution_ids)):
            raise CanonicalTransactionInvariantError(
                "ledger append proof contains duplicate execution ids"
            )
        if self.next_total_rows - self.previous_total_rows != len(execution_ids):
            raise CanonicalTransactionInvariantError(
                "total ledger row delta must equal appended execution count"
            )
        if self.next_epoch_rows - self.previous_epoch_rows != len(execution_ids):
            raise CanonicalTransactionInvariantError(
                "epoch ledger row delta must equal appended execution count"
            )
        state_payload = str(self.previous_state_payload_sha256 or "").lower().strip()
        previous = str(self.previous_sha256 or "").lower().strip()
        following = str(self.next_sha256 or "").lower().strip()
        if (
            not _SHA256.fullmatch(state_payload)
            or not _SHA256.fullmatch(previous)
            or not _SHA256.fullmatch(following)
        ):
            raise CanonicalTransactionInvariantError(
                "ledger append proof requires exact state and ledger SHA-256 digests"
            )
        if previous == following:
            raise CanonicalTransactionInvariantError(
                "an appended ledger must have a new digest"
            )
        if self.chain_valid is not True:
            raise CanonicalTransactionInvariantError(
                "canonical ledger chain must be valid after append"
            )
        object.__setattr__(self, "previous_state_payload_sha256", state_payload)
        object.__setattr__(self, "previous_sha256", previous)
        object.__setattr__(self, "next_sha256", following)
        object.__setattr__(self, "appended_execution_ids", execution_ids)


@dataclass(frozen=True)
class CanonicalTransactionReceipt:
    previous_revision: int
    next_envelope: CanonicalStateEnvelope
    ledger: LedgerAppendProof
    accounting_version: str
    valuation_version: str
    risk_version: str
    runtime_registration: bool = False
    production_state_writes: bool = False
    order_authority: bool = False
    live_authority: bool = False
    ml_execution_authority: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        if self.next_envelope.revision != self.previous_revision + 1:
            raise CanonicalTransactionInvariantError(
                "canonical transaction must prepare exactly one next revision"
            )
        snapshot = self.next_envelope.snapshot()
        if (
            snapshot.execution_ledger_rows != self.ledger.next_total_rows
            or snapshot.execution_epoch_rows != self.ledger.next_epoch_rows
            or snapshot.execution_chain_valid is not True
        ):
            raise CanonicalTransactionInvariantError(
                "next StateStore revision must bind the settled ledger append"
            )
        if self.authority != AUTHORITY or any(
            (
                self.runtime_registration,
                self.production_state_writes,
                self.order_authority,
                self.live_authority,
                self.ml_execution_authority,
            )
        ):
            raise CanonicalTransactionInvariantError(
                "transaction preparation cannot hold runtime authority"
            )

    def to_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "authority": self.authority,
                "version": self.version,
                "previous_revision": self.previous_revision,
                "next_revision": self.next_envelope.revision,
                "next_payload_sha256": self.next_envelope.payload_sha256,
                "previous_state_payload_sha256": (
                    self.ledger.previous_state_payload_sha256
                ),
                "previous_ledger_sha256": self.ledger.previous_sha256,
                "next_ledger_sha256": self.ledger.next_sha256,
                "previous_total_rows": self.ledger.previous_total_rows,
                "next_total_rows": self.ledger.next_total_rows,
                "previous_epoch_rows": self.ledger.previous_epoch_rows,
                "next_epoch_rows": self.ledger.next_epoch_rows,
                "appended_execution_ids": self.ledger.appended_execution_ids,
                "accounting_version": self.accounting_version,
                "valuation_version": self.valuation_version,
                "risk_version": self.risk_version,
                "runtime_registration": self.runtime_registration,
                "production_state_writes": self.production_state_writes,
                "order_authority": self.order_authority,
                "live_authority": self.live_authority,
                "ml_execution_authority": self.ml_execution_authority,
            }
        )


class SingleOwnerProjectionTransaction:
    """Prepare one canonical revision after an independently settled append."""

    authority = AUTHORITY
    runtime_registered = False
    production_state_writes = False
    places_orders = False
    changes_strategy = False
    changes_risk_limits = False

    @classmethod
    def prepare(
        cls,
        *,
        current: CanonicalStateEnvelope,
        executions: Iterable[ExecutionSnapshot],
        protected_marks: Iterable[ProtectedMarkSnapshot],
        ledger: LedgerAppendProof,
        risk_date: str,
        risk_limits: RiskLimits,
        created_at: str,
    ) -> CanonicalTransactionReceipt:
        if not isinstance(current, CanonicalStateEnvelope):
            raise CanonicalTransactionInvariantError(
                "current state must be a canonical StateStore envelope"
            )
        if not isinstance(ledger, LedgerAppendProof):
            raise CanonicalTransactionInvariantError(
                "transaction requires a typed ledger append proof"
            )
        before = current.snapshot()
        if (
            ledger.previous_total_rows != before.execution_ledger_rows
            or ledger.previous_epoch_rows != before.execution_epoch_rows
            or ledger.previous_state_payload_sha256 != current.payload_sha256
        ):
            raise CanonicalTransactionInvariantError(
                "ledger append proof does not start at the current StateStore revision"
            )

        execution_rows = tuple(executions)
        execution_ids = tuple(row.execution_id for row in execution_rows)
        if execution_ids != ledger.appended_execution_ids:
            raise CanonicalTransactionInvariantError(
                "projected executions must exactly match the settled ledger append"
            )
        expected_sequences = tuple(
            range(ledger.previous_total_rows + 1, ledger.next_total_rows + 1)
        )
        if tuple(row.sequence for row in execution_rows) != expected_sequences:
            raise CanonicalTransactionInvariantError(
                "execution sequences must continue the canonical ledger without gaps"
            )

        marks = tuple(protected_marks)
        mark_prices = {row.symbol: row.price for row in marks}
        if len(mark_prices) != len(marks):
            raise CanonicalTransactionInvariantError("protected marks must be unique")
        portfolio_before = before.portfolio
        projection = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(
                cash=portfolio_before.cash,
                positions=portfolio_before.positions,
                realized_total=portfolio_before.realized_total,
                realized_today=portfolio_before.realized_today,
                accounting_epoch=portfolio_before.accounting_epoch,
            ),
            executions=execution_rows,
            marks=mark_prices,
            today=str(risk_date or ""),
        )

        open_symbols = {row.symbol for row in projection.portfolio.positions}
        valuation_marks = tuple(row for row in marks if row.symbol in open_symbols)
        if {row.symbol for row in marks} != open_symbols:
            raise CanonicalTransactionInvariantError(
                "protected marks must exactly cover projected open positions"
            )
        valuation = DeterministicValuationService.value(
            cash=projection.portfolio.cash,
            positions=projection.portfolio.positions,
            marks=valuation_marks,
        )
        if (
            abs(valuation.equity - projection.portfolio.equity) > 0.005
            or abs(
                valuation.total_unrealized_pnl
                - projection.portfolio.unrealized_pnl
            )
            > 0.005
        ):
            raise CanonicalTransactionInvariantError(
                "accounting projection and protected valuation diverged"
            )
        portfolio = PortfolioSnapshot(
            cash=projection.portfolio.cash,
            equity=valuation.equity,
            realized_total=projection.portfolio.realized_total,
            realized_today=projection.portfolio.realized_today,
            unrealized_pnl=valuation.total_unrealized_pnl,
            positions=projection.portfolio.positions,
            accounting_epoch=projection.portfolio.accounting_epoch,
        )
        risk = ShadowRiskEngine.evaluate(
            date=risk_date,
            valuation=valuation,
            realized_today=portfolio.realized_today,
            limits=risk_limits,
            previous=before.risk,
        )
        next_snapshot = CanonicalStateSnapshot(
            portfolio=portfolio,
            risk=risk.state,
            execution_ledger_rows=ledger.next_total_rows,
            execution_epoch_rows=ledger.next_epoch_rows,
            execution_chain_valid=True,
            source_version=VERSION,
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=next_snapshot,
            revision=current.revision + 1,
            created_at=created_at,
        )
        return CanonicalTransactionReceipt(
            previous_revision=current.revision,
            next_envelope=envelope,
            ledger=ledger,
            accounting_version=projection.version,
            valuation_version=valuation.version,
            risk_version=risk.version,
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "target_interface": "trading.transaction.SingleOwnerProjectionTransaction",
                "authority": cls.authority,
                "runtime_registered": cls.runtime_registered,
                "production_state_writes": cls.production_state_writes,
                "places_orders": cls.places_orders,
                "changes_strategy": cls.changes_strategy,
                "changes_risk_limits": cls.changes_risk_limits,
                "ledger_append_must_settle_before_projection": True,
                "single_next_revision": True,
                "version": VERSION,
            }
        )
