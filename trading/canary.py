"""Shadow-only canary readiness planner for Stable Paper Core v3 Stage F.

This module does not register with the trading runtime and cannot mutate state,
place orders, clear risk halts, or switch production authority. It only evaluates
explicitly supplied acceptance evidence and emits an immutable canary plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from trading.accounting import AccountingProjection
from trading.risk import RiskEvaluation
from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    RiskStateSnapshot,
)
from trading.state_store import CanonicalStateEnvelope
from trading.state_store import CanonicalStateStore
from trading.valuation import MONEY_SERIALIZATION_TOLERANCE, ValuationSnapshot

VERSION = "stable-paper-core-v3-stage-f-canary-readiness-2026-08-20-v1"
AUTHORITY = "shadow_only"
MAX_CANARY_FRACTION = 0.05
AUTHORITATIVE_RUNTIME_URL = "https://web-production-e1796.up.railway.app"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class CanaryInvariantError(ValueError):
    """Raised when a canary-readiness request violates the Stage F contract."""


def _evidence_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanaryInvariantError(f"{name} must be a mapping")
    return value


def _evidence_float(value: Any, *, name: str) -> float:
    if value is None or isinstance(value, bool):
        raise CanaryInvariantError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CanaryInvariantError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise CanaryInvariantError(f"{name} must be finite")
    return result


def _evidence_int(value: Any, *, name: str) -> int:
    if value is None or isinstance(value, bool):
        raise CanaryInvariantError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CanaryInvariantError(f"{name} must be an integer") from exc
    if result < 0:
        raise CanaryInvariantError(f"{name} must be non-negative")
    return result


def _require_evidence(condition: Any, blocker: str) -> None:
    if not bool(condition):
        raise CanaryInvariantError(f"runtime evidence blocked: {blocker}")


def _bind_v5_epoch_and_ledger(
    audit: Mapping[str, Any],
) -> tuple[AccountingEpochSnapshot, int, int, str]:
    epoch = _evidence_mapping(
        audit.get("accounting_epoch"), name="daily_audit.accounting_epoch"
    )
    ledger = _evidence_mapping(
        audit.get("execution_ledger"), name="daily_audit.execution_ledger"
    )
    integrity = _evidence_mapping(
        audit.get("accounting_integrity"),
        name="daily_audit.accounting_integrity",
    )
    epoch_id = str(epoch.get("epoch_id") or "").strip()
    _require_evidence(epoch_id.startswith("stable-paper-v5-"), "v5_epoch")
    _require_evidence(
        str(ledger.get("current_epoch_id") or "") == epoch_id,
        "epoch_lineage_match",
    )
    _require_evidence(epoch.get("validation_hold") is True, "validation_hold")
    _require_evidence(
        epoch.get("historical_evidence_archived") is True,
        "historical_evidence_archived",
    )
    _require_evidence(epoch.get("zero_trade_baseline") is True, "zero_trade_baseline")

    total_rows = _evidence_int(ledger.get("row_count"), name="ledger.row_count")
    ledger_sha256 = str(ledger.get("ledger_sha256") or "").lower().strip()
    _require_evidence(
        re.fullmatch(_SHA256_PATTERN, ledger_sha256),
        "observed_ledger_sha256",
    )
    epoch_rows = _evidence_int(
        ledger.get("current_epoch_rows"), name="ledger.current_epoch_rows"
    )
    state_rows = _evidence_int(
        ledger.get("state_current_epoch_rows"),
        name="ledger.state_current_epoch_rows",
    )
    _require_evidence(ledger.get("chain_valid") is True, "canonical_chain_valid")
    _require_evidence(
        ledger.get("state_projection_parity") is True,
        "canonical_state_projection_parity",
    )
    _require_evidence(epoch_rows == 0, "verified_flat_epoch_rows")
    _require_evidence(state_rows == epoch_rows, "state_epoch_row_count")
    _require_evidence(
        _evidence_int(
            ledger.get("missing_from_state_count"),
            name="ledger.missing_from_state_count",
        )
        == 0,
        "missing_from_state",
    )
    _require_evidence(
        _evidence_int(
            ledger.get("missing_from_ledger_count"),
            name="ledger.missing_from_ledger_count",
        )
        == 0,
        "missing_from_ledger",
    )

    _require_evidence(
        str(integrity.get("status") or "").lower() in ("ok", "pass"),
        "accounting_integrity",
    )
    _require_evidence(integrity.get("coverage_complete") is True, "accounting_coverage")
    _require_evidence(
        _evidence_int(
            integrity.get("coverage_issue_count"),
            name="accounting.coverage_issue_count",
        )
        == 0,
        "accounting_coverage_issues",
    )
    _require_evidence(
        _evidence_int(
            integrity.get("economic_issue_count"),
            name="accounting.economic_issue_count",
        )
        == 0,
        "accounting_economic_issues",
    )
    return (
        AccountingEpochSnapshot(
            epoch_id=epoch_id,
            baseline_type=str(epoch.get("baseline_type") or ""),
            historical_evidence_archived=True,
            validation_hold=True,
        ),
        total_rows,
        epoch_rows,
        ledger_sha256,
    )


def _bind_v5_flat_portfolio(
    audit: Mapping[str, Any],
    status: Mapping[str, Any],
    epoch: AccountingEpochSnapshot,
) -> PortfolioSnapshot:
    account = _evidence_mapping(audit.get("account"), name="daily_audit.account")
    _require_evidence(account.get("positions") in ({}, [], ()), "verified_flat_positions")
    _require_evidence(status.get("positions") in ({}, [], ()), "status_flat_positions")
    _require_evidence(status.get("recent_trades") in (None, [], ()), "zero_state_trades")
    cash = _evidence_float(account.get("cash"), name="account.cash")
    equity = _evidence_float(account.get("equity"), name="account.equity")
    _require_evidence(cash > 0.0 and equity > 0.0, "positive_account_value")
    _require_evidence(
        abs(cash - equity) <= MONEY_SERIALIZATION_TOLERANCE,
        "flat_cash_equity_parity",
    )
    _require_evidence(
        _evidence_float(status.get("cash"), name="paper_status.cash")
        == round(cash, 2),
        "status_cash_provenance",
    )
    _require_evidence(
        _evidence_float(status.get("equity"), name="paper_status.equity")
        == round(equity, 2),
        "status_equity_provenance",
    )

    realized = _evidence_mapping(
        status.get("realized_pnl"), name="paper_status.realized_pnl"
    )
    realized_today = _evidence_float(
        account.get("realized_today"), name="account.realized_today"
    )
    unrealized = _evidence_float(
        account.get("unrealized_pnl"), name="account.unrealized_pnl"
    )
    _require_evidence(unrealized == 0.0, "verified_flat_unrealized_pnl")
    if realized.get("today") is not None:
        _require_evidence(
            _evidence_float(realized.get("today"), name="realized.today")
            == realized_today,
            "realized_today_provenance",
        )
    return PortfolioSnapshot(
        cash=cash,
        equity=equity,
        realized_total=_evidence_float(realized.get("total"), name="realized.total"),
        realized_today=realized_today,
        unrealized_pnl=unrealized,
        positions=(),
        accounting_epoch=epoch,
    )


def _bind_v5_risk(
    audit: Mapping[str, Any],
    day: Mapping[str, Any],
    *,
    portfolio: PortfolioSnapshot,
    valuation: ValuationSnapshot,
) -> RiskEvaluation:
    audit_risk = _evidence_mapping(audit.get("risk"), name="daily_audit.risk")
    risk_date = str(day.get("date") or "").strip()
    start_equity = _evidence_float(
        day.get("day_start_equity"), name="fresh_day.day_start_equity"
    )
    peak_equity = _evidence_float(
        day.get("day_peak_equity"), name="fresh_day.day_peak_equity"
    )
    _require_evidence(day.get("baseline_status") == "pass", "fresh_day_baseline")
    _require_evidence(day.get("fresh_day_reset_pending") is False, "fresh_day_reset")
    _require_evidence(bool(risk_date), "risk_date")
    _require_evidence(
        bool(audit_risk.get("halted")) == bool(day.get("halted")),
        "risk_halt_provenance",
    )
    halt_reason = str(audit_risk.get("halt_reason") or "")
    _require_evidence(
        halt_reason == str(day.get("halt_reason") or ""),
        "risk_halt_reason_provenance",
    )
    state = RiskStateSnapshot(
        date=risk_date,
        day_start_equity=start_equity,
        day_peak_equity=peak_equity,
        daily_loss_fraction=_evidence_float(
            audit_risk.get("net_daily_loss_pct") or 0.0,
            name="risk.net_daily_loss_pct",
        )
        / 100.0,
        intraday_drawdown_fraction=_evidence_float(
            audit_risk.get("intraday_drawdown_pct") or 0.0,
            name="risk.intraday_drawdown_pct",
        )
        / 100.0,
        halted=bool(audit_risk.get("halted")),
        halt_reason=halt_reason,
    )
    return RiskEvaluation(
        state=state,
        day_pnl_fraction=(portfolio.equity - start_equity) / start_equity,
        realized_loss_fraction=max(0.0, -portfolio.realized_today / start_equity),
        daily_loss_triggered=False,
        intraday_drawdown_triggered=False,
        realized_loss_triggered=False,
        fresh_day=False,
        valuation_version=valuation.version,
    )


@dataclass(frozen=True)
class SnapshotBindingProof:
    revision: int
    payload_sha256: str
    verified: bool
    blockers: Tuple[str, ...]
    accounting_version: str
    valuation_version: str
    risk_version: str
    ledger_total_rows: int
    ledger_epoch_rows: int
    epoch_id: str = ""
    ledger_sha256: str = ""
    evidence_captured_at: str = ""
    evidence_source: str = ""
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
        if self.ledger_sha256 and not re.fullmatch(
            _SHA256_PATTERN, str(self.ledger_sha256).lower()
        ):
            raise CanaryInvariantError("ledger_sha256 must be an exact SHA-256 digest")

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
                "ledger_total_rows": self.ledger_total_rows,
                "ledger_epoch_rows": self.ledger_epoch_rows,
                "epoch_id": self.epoch_id,
                "ledger_sha256": self.ledger_sha256,
                "evidence_captured_at": self.evidence_captured_at,
                "evidence_source": self.evidence_source,
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
class RuntimeV5Binding:
    """Typed, shadow-only proof derived from one settled v5 evidence capture."""

    envelope: CanonicalStateEnvelope
    accounting: AccountingProjection
    valuation: ValuationSnapshot
    risk: RiskEvaluation
    proof: SnapshotBindingProof
    runtime_registration: bool = False
    production_state_writes: bool = False
    risk_mutation_authority: bool = False
    order_authority: bool = False
    authority: str = AUTHORITY

    def __post_init__(self) -> None:
        if self.authority != AUTHORITY or any(
            (
                self.runtime_registration,
                self.production_state_writes,
                self.risk_mutation_authority,
                self.order_authority,
            )
        ):
            raise CanaryInvariantError("runtime evidence binding must remain shadow-only")
        if not self.proof.verified:
            raise CanaryInvariantError("runtime evidence binding requires a verified proof")


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
        epoch_id: str = "",
        ledger_sha256: str = "",
        evidence_captured_at: str = "",
        evidence_source: str = "",
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
                "ledger_total_not_below_epoch",
                snapshot.execution_ledger_rows >= snapshot.execution_epoch_rows,
            ),
            (
                "ledger_projection_row_count",
                snapshot.execution_epoch_rows == accounting.execution_rows,
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
            ledger_total_rows=snapshot.execution_ledger_rows,
            ledger_epoch_rows=snapshot.execution_epoch_rows,
            epoch_id=str(epoch_id or ""),
            ledger_sha256=str(ledger_sha256 or "").lower(),
            evidence_captured_at=str(evidence_captured_at or ""),
            evidence_source=str(evidence_source or ""),
        )

    @classmethod
    def bind_verified_flat_v5_runtime_evidence(
        cls,
        *,
        daily_audit: Mapping[str, Any],
        paper_status: Mapping[str, Any],
        fresh_day: Mapping[str, Any],
        ledger_sha256: str,
        revision: int,
        captured_at: str,
        source_url: str = AUTHORITATIVE_RUNTIME_URL,
    ) -> RuntimeV5Binding:
        """Bind a settled, verified-flat v5 runtime capture without authority."""
        audit = _evidence_mapping(daily_audit, name="daily_audit")
        status = _evidence_mapping(paper_status, name="paper_status")
        day = _evidence_mapping(fresh_day, name="fresh_day")
        source = str(source_url or "").rstrip("/")
        captured = str(captured_at or "").strip()
        digest = str(ledger_sha256 or "").lower().strip()
        _require_evidence(source == AUTHORITATIVE_RUNTIME_URL, "authoritative_source")
        _require_evidence(bool(captured), "capture_timestamp")
        _require_evidence(re.fullmatch(_SHA256_PATTERN, digest), "ledger_sha256")
        try:
            state_revision = int(revision)
        except (TypeError, ValueError) as exc:
            raise CanaryInvariantError("revision must be an integer") from exc
        _require_evidence(state_revision > 0, "positive_state_revision")

        epoch, total_rows, epoch_rows, observed_digest = _bind_v5_epoch_and_ledger(
            audit
        )
        _require_evidence(digest == observed_digest, "ledger_sha256_provenance")
        portfolio = _bind_v5_flat_portfolio(audit, status, epoch)
        accounting = AccountingProjection(
            portfolio=portfolio,
            execution_rows=epoch_rows,
            last_sequence=0,
            execution_ids=(),
        )
        valuation = ValuationSnapshot(
            cash=portfolio.cash,
            equity=portfolio.equity,
            total_cost_basis=0.0,
            total_position_value=0.0,
            total_unrealized_pnl=0.0,
            gross_market_exposure=0.0,
            net_market_exposure=0.0,
            positions=(),
        )
        risk = _bind_v5_risk(
            audit,
            day,
            portfolio=portfolio,
            valuation=valuation,
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=portfolio,
                risk=risk.state,
                execution_ledger_rows=total_rows,
                execution_epoch_rows=epoch_rows,
                execution_chain_valid=True,
            ),
            revision=state_revision,
            created_at=captured,
        )
        proof = cls.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
            epoch_id=epoch.epoch_id,
            ledger_sha256=digest,
            evidence_captured_at=captured,
            evidence_source=source,
        )
        _require_evidence(proof.verified, "single_revision_snapshot_binding")
        return RuntimeV5Binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
            proof=proof,
        )
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
