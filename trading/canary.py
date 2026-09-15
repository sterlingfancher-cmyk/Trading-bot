"""Shadow-only canary readiness planner for Stable Paper Core v3 Stage F.

This module does not register with the trading runtime and cannot mutate state,
place orders, clear risk halts, or switch production authority. It only evaluates
explicitly supplied acceptance evidence and emits an immutable canary plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from trading.accounting import AccountingProjection
from trading.risk import RiskEvaluation
from trading.state_store import CanonicalStateEnvelope
from trading.valuation import ValuationSnapshot

VERSION = "stable-paper-core-v3-stage-f-canary-readiness-2026-08-20-v1"
AUTHORITY = "shadow_only"
MAX_CANARY_FRACTION = 0.05


class CanaryInvariantError(ValueError):
    """Raised when a canary-readiness request violates the Stage F contract."""


@dataclass(frozen=True)
class SnapshotBindingProof:
    revision: int
    payload_sha256: str
    verified: bool
    blockers: Tuple[str, ...]
    accounting_version: str
    valuation_version: str
    risk_version: str
    rollback_default_armed: bool = True
    runtime_registration: bool = False
    production_state_writes: bool = False
    risk_mutation_authority: bool = False
    order_authority: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        blockers = tuple(self.blockers)
        if self.verified != (len(blockers) == 0):
            raise CanaryInvariantError("snapshot binding must exactly match blockers")
        if self.authority != AUTHORITY:
            raise CanaryInvariantError("snapshot binding proof must remain shadow-only")
        if not self.rollback_default_armed:
            raise CanaryInvariantError("snapshot binding proof requires armed rollback")
        if any(
            (
                self.runtime_registration,
                self.production_state_writes,
                self.risk_mutation_authority,
                self.order_authority,
            )
        ):
            raise CanaryInvariantError("snapshot binding proof cannot hold runtime authority")
        object.__setattr__(self, "revision", int(self.revision))
        object.__setattr__(self, "blockers", blockers)

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "authority": self.authority,
                "version": self.version,
                "revision": self.revision,
                "payload_sha256": self.payload_sha256,
                "verified": self.verified,
                "blockers": self.blockers,
                "accounting_version": self.accounting_version,
                "valuation_version": self.valuation_version,
                "risk_version": self.risk_version,
                "rollback_default_armed": self.rollback_default_armed,
                "runtime_registration": self.runtime_registration,
                "production_state_writes": self.production_state_writes,
                "risk_mutation_authority": self.risk_mutation_authority,
                "order_authority": self.order_authority,
            }
        )


@dataclass(frozen=True)
class CanaryEvidence:
    issue_82_fresh_risk_day_pass: bool
    issue_82_forward_session_pass: bool
    clean_active_accounting_audit: bool
    canonical_ledger_chain_valid: bool
    protected_valuation_sane: bool
    stage_b_valuation_parity: bool
    stage_c_risk_parity: bool
    stage_d_restart_parity: bool
    stage_e_accounting_parity: bool
    single_revision_snapshot_binding: bool
    repository_validation_green: bool
    architecture_debt_gate_green: bool
    refactor_startup_audit_green: bool

    def blockers(self) -> Tuple[str, ...]:
        checks = (
            ("issue_82_fresh_risk_day_pass", self.issue_82_fresh_risk_day_pass),
            ("issue_82_forward_session_pass", self.issue_82_forward_session_pass),
            ("clean_active_accounting_audit", self.clean_active_accounting_audit),
            ("canonical_ledger_chain_valid", self.canonical_ledger_chain_valid),
            ("protected_valuation_sane", self.protected_valuation_sane),
            ("stage_b_valuation_parity", self.stage_b_valuation_parity),
            ("stage_c_risk_parity", self.stage_c_risk_parity),
            ("stage_d_restart_parity", self.stage_d_restart_parity),
            ("stage_e_accounting_parity", self.stage_e_accounting_parity),
            (
                "single_revision_snapshot_binding",
                self.single_revision_snapshot_binding,
            ),
            ("repository_validation_green", self.repository_validation_green),
            ("architecture_debt_gate_green", self.architecture_debt_gate_green),
            ("refactor_startup_audit_green", self.refactor_startup_audit_green),
        )
        return tuple(name for name, passed in checks if not bool(passed))


@dataclass(frozen=True)
class CanaryPlan:
    requested_fraction: float
    eligible_for_future_canary: bool
    blockers: Tuple[str, ...]
    rollback_switch_required: bool = True
    rollback_default_armed: bool = True
    runtime_registration: bool = False
    production_state_writes: bool = False
    order_authority: bool = False
    risk_mutation_authority: bool = False
    live_authority: bool = False
    ml_execution_authority: bool = False
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        fraction = float(self.requested_fraction)
        if not 0.0 < fraction <= MAX_CANARY_FRACTION:
            raise CanaryInvariantError(
                f"requested canary fraction must be > 0 and <= {MAX_CANARY_FRACTION}"
            )
        if self.authority != AUTHORITY:
            raise CanaryInvariantError("Stage F planner must remain shadow-only")
        if any(
            (
                self.runtime_registration,
                self.production_state_writes,
                self.order_authority,
                self.risk_mutation_authority,
                self.live_authority,
                self.ml_execution_authority,
            )
        ):
            raise CanaryInvariantError("Stage F readiness plan cannot hold runtime authority")
        if self.eligible_for_future_canary != (len(self.blockers) == 0):
            raise CanaryInvariantError("eligibility must exactly match blocker state")
        object.__setattr__(self, "requested_fraction", fraction)
        object.__setattr__(self, "blockers", tuple(self.blockers))

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "authority": self.authority,
                "version": self.version,
                "requested_fraction": self.requested_fraction,
                "eligible_for_future_canary": self.eligible_for_future_canary,
                "blockers": self.blockers,
                "rollback_switch_required": self.rollback_switch_required,
                "rollback_default_armed": self.rollback_default_armed,
                "runtime_registration": self.runtime_registration,
                "production_state_writes": self.production_state_writes,
                "order_authority": self.order_authority,
                "risk_mutation_authority": self.risk_mutation_authority,
                "live_authority": self.live_authority,
                "ml_execution_authority": self.ml_execution_authority,
            }
        )


class CanaryReadinessPlanner:
    """Pure readiness evaluation; never performs a production canary cutover."""

    authority = AUTHORITY
    max_canary_fraction = MAX_CANARY_FRACTION
    runtime_registration = False
    production_state_writes = False
    order_authority = False
    risk_mutation_authority = False

    @classmethod
    def plan(
        cls,
        *,
        evidence: CanaryEvidence,
        requested_fraction: float = 0.01,
    ) -> CanaryPlan:
        blockers = evidence.blockers()
        return CanaryPlan(
            requested_fraction=requested_fraction,
            eligible_for_future_canary=not blockers,
            blockers=blockers,
        )

    @classmethod
    def verify_snapshot_binding(
        cls,
        *,
        envelope: CanonicalStateEnvelope,
        accounting: AccountingProjection,
        valuation: ValuationSnapshot,
        risk: RiskEvaluation,
    ) -> SnapshotBindingProof:
        """Prove all shadow core results describe one immutable revision."""
        snapshot = envelope.snapshot()
        portfolio = snapshot.portfolio
        accounting_portfolio = accounting.portfolio
        valuation_positions = tuple(
            (
                row.symbol,
                row.side,
                row.quantity,
                row.entry_price,
                row.mark_price,
            )
            for row in valuation.positions
        )
        canonical_positions = tuple(
            (
                row.symbol,
                row.side,
                row.quantity,
                row.entry_price,
                row.mark_price,
            )
            for row in portfolio.positions
        )
        checks = (
            ("positive_state_revision", envelope.revision > 0),
            ("canonical_chain_valid", snapshot.execution_chain_valid),
            (
                "ledger_projection_row_count",
                snapshot.execution_ledger_rows == accounting.execution_rows,
            ),
            ("accounting_portfolio", portfolio == accounting_portfolio),
            ("valuation_cash", portfolio.cash == valuation.cash),
            ("valuation_equity", portfolio.equity == valuation.equity),
            (
                "valuation_unrealized_pnl",
                portfolio.unrealized_pnl == valuation.total_unrealized_pnl,
            ),
            ("valuation_positions", canonical_positions == valuation_positions),
            ("risk_state", snapshot.risk == risk.state),
            ("risk_valuation_version", risk.valuation_version == valuation.version),
        )
        blockers = tuple(name for name, passed in checks if not bool(passed))
        return SnapshotBindingProof(
            revision=envelope.revision,
            payload_sha256=envelope.payload_sha256,
            verified=not blockers,
            blockers=blockers,
            accounting_version=accounting.version,
            valuation_version=valuation.version,
            risk_version=risk.version,
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.canary.CanaryReadinessPlanner",
                "authority": cls.authority,
                "max_canary_fraction": cls.max_canary_fraction,
                "runtime_registration": cls.runtime_registration,
                "production_state_writes": cls.production_state_writes,
                "order_authority": cls.order_authority,
                "risk_mutation_authority": cls.risk_mutation_authority,
                "single_revision_snapshot_binding_required": True,
                "version": VERSION,
            }
        )
