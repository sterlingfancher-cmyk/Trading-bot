from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile

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
from trading.transaction import (
    CanonicalTransactionInvariantError,
    LedgerAppendProof,
    SingleOwnerProjectionTransaction,
)
from trading.valuation import ProtectedMarkSnapshot, ValuationInvariantError


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
    return CanonicalStateStore.prepare(
        snapshot=snapshot,
        revision=7,
        created_at="2026-10-01 08:00:00 CDT",
    )


def _execution():
    return ExecutionSnapshot(
        sequence=89,
        symbol="SPY",
        event="entry",
        side="long",
        quantity=1.0,
        price=100.0,
        timestamp="2026-10-01 08:01:00 CDT",
        execution_id="execution-89",
    )


def _proof():
    current = _current()
    return LedgerAppendProof(
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


def _mark(*, fresh=True):
    return ProtectedMarkSnapshot(
        symbol="SPY",
        price=101.0,
        source="protected-test-mark",
        fresh=fresh,
        plausible=True,
        observed_at="2026-10-01 08:01:01 CDT",
    )


def _limits():
    return RiskLimits(
        max_daily_loss_fraction=0.03,
        max_intraday_drawdown_fraction=0.03,
        hard_realized_loss_fraction=0.02,
    )


def _prepare(**overrides):
    values = {
        "current": _current(),
        "executions": (_execution(),),
        "protected_marks": (_mark(),),
        "ledger": _proof(),
        "risk_date": "2026-10-01",
        "risk_limits": _limits(),
        "created_at": "2026-10-01 08:01:02 CDT",
    }
    values.update(overrides)
    return SingleOwnerProjectionTransaction.prepare(**values)


def test_single_owner_transaction_binds_append_projection_valuation_and_risk():
    receipt = _prepare()
    snapshot = receipt.next_envelope.snapshot()

    assert receipt.previous_revision == 7
    assert receipt.next_envelope.revision == 8
    assert snapshot.execution_ledger_rows == 89
    assert snapshot.execution_epoch_rows == 1
    assert snapshot.execution_chain_valid is True
    assert snapshot.portfolio.cash == pytest.approx(900.0)
    assert snapshot.portfolio.equity == pytest.approx(1_001.0)
    assert snapshot.portfolio.unrealized_pnl == pytest.approx(1.0)
    assert snapshot.portfolio.positions[0].symbol == "SPY"
    assert snapshot.portfolio.positions[0].mark_price == pytest.approx(101.0)
    assert snapshot.risk.date == "2026-10-01"
    assert snapshot.risk.day_start_equity == pytest.approx(1_000.0)
    assert snapshot.risk.day_peak_equity == pytest.approx(1_001.0)
    assert snapshot.risk.halted is False
    assert receipt.to_dict()["appended_execution_ids"] == ("execution-89",)
    assert receipt.runtime_registration is False
    assert receipt.production_state_writes is False
    assert receipt.order_authority is False


def test_preparation_does_not_write_and_candidate_restarts_deterministically():
    receipt = _prepare()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "canonical-state.json"
        assert not path.exists()
        receipt_again = _prepare()
        assert receipt_again.next_envelope.payload_sha256 == receipt.next_envelope.payload_sha256
        assert not path.exists()

        sandbox = CanonicalStateStore(path, sandbox_io_enabled=True)
        sandbox.commit_sandbox(receipt.next_envelope)
        restarted = CanonicalStateStore(
            path, sandbox_io_enabled=True
        ).read_sandbox()
        assert restarted.revision == receipt.next_envelope.revision
        assert restarted.payload_sha256 == receipt.next_envelope.payload_sha256


@pytest.mark.parametrize(
    "drift",
    (
        {"next_total_rows": 90},
        {"next_epoch_rows": 2},
        {"next_sha256": "a" * 64},
        {"chain_valid": False},
    ),
)
def test_ledger_append_proof_rejects_incomplete_or_drifted_evidence(drift):
    with pytest.raises(CanonicalTransactionInvariantError):
        replace(_proof(), **drift)


def test_transaction_rejects_state_start_or_execution_identity_drift():
    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(ledger=replace(_proof(), previous_total_rows=87, next_total_rows=88))

    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(ledger=replace(_proof(), previous_state_payload_sha256="c" * 64))

    different = replace(_execution(), execution_id="other-execution")
    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(executions=(different,))

    skipped = replace(_execution(), sequence=90)
    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(executions=(skipped,))


def test_transaction_rejects_unprotected_or_duplicate_marks():
    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(protected_marks=())

    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(protected_marks=(_mark(), _mark()))

    extra = ProtectedMarkSnapshot(
        symbol="QQQ",
        price=100.0,
        source="protected-test-mark",
        fresh=True,
        plausible=True,
    )
    with pytest.raises(CanonicalTransactionInvariantError):
        _prepare(protected_marks=(_mark(), extra))

    with pytest.raises(ValuationInvariantError):
        _mark(fresh=False)


def test_transaction_descriptor_proves_no_runtime_authority():
    descriptor = SingleOwnerProjectionTransaction.descriptor()
    assert descriptor["ledger_append_must_settle_before_projection"] is True
    assert descriptor["single_next_revision"] is True
    assert descriptor["runtime_registered"] is False
    assert descriptor["production_state_writes"] is False
    assert descriptor["places_orders"] is False
    assert descriptor["changes_strategy"] is False
    assert descriptor["changes_risk_limits"] is False
