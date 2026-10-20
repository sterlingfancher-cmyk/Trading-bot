from dataclasses import replace

import pytest

from trading.ledger_writer import SandboxLedgerIntentWriter
from trading.ledger_writer_contract import (
    LedgerIntentWriter,
    ProductionWriterContractError,
    ProductionWriterCutoverContract,
)


def test_sandbox_writer_implements_exact_interface_without_production_authority(
    tmp_path,
):
    writer = SandboxLedgerIntentWriter(
        tmp_path / "ledger.jsonl",
        sandbox_io_enabled=True,
    )
    assert isinstance(writer, LedgerIntentWriter)

    contract = ProductionWriterCutoverContract.inspect(writer)
    payload = contract.to_dict()
    assert payload["state"] == "blocked"
    assert payload["current_owner"] == "canonical_execution_ledger.append_execution"
    assert payload["candidate_interface"].endswith("SandboxLedgerIntentWriter")
    assert payload["independent_review_completed"] is False
    assert payload["activation_performed"] is False
    assert payload["runtime_registration"] is False
    assert payload["production_writes"] is False
    assert payload["state_store_commit"] is False
    assert payload["order_authority"] is False
    assert payload["live_authority"] is False
    assert payload["ml_execution_authority"] is False


def test_contract_inspection_is_observational_and_never_calls_writer(tmp_path):
    class ExplodingWriter(SandboxLedgerIntentWriter):
        def append_intent(self, *args, **kwargs):
            raise AssertionError("contract inspection invoked the writer")

    writer = ExplodingWriter(tmp_path / "ledger.jsonl", sandbox_io_enabled=True)
    contract = ProductionWriterCutoverContract.inspect(writer)
    assert contract.state == "blocked"
    assert not (tmp_path / "ledger.jsonl").exists()


def test_contract_is_deterministic_and_digest_bound(tmp_path):
    writer = SandboxLedgerIntentWriter(
        tmp_path / "ledger.jsonl",
        sandbox_io_enabled=True,
    )
    first = ProductionWriterCutoverContract.inspect(writer)
    second = ProductionWriterCutoverContract.inspect(writer)
    assert first == second
    assert first.contract_sha256 == second.contract_sha256
    assert first.candidate_descriptor_sha256 == second.candidate_descriptor_sha256
    with pytest.raises(ProductionWriterContractError, match="digest mismatch"):
        replace(first, contract_sha256="f" * 64)


@pytest.mark.parametrize(
    "field",
    (
        "independent_review_completed",
        "activation_performed",
        "runtime_registration",
        "production_writes",
        "state_store_commit",
        "order_authority",
        "live_authority",
        "ml_execution_authority",
    ),
)
def test_contract_cannot_self_grant_authority(tmp_path, field):
    contract = ProductionWriterCutoverContract.inspect(
        SandboxLedgerIntentWriter(
            tmp_path / "ledger.jsonl",
            sandbox_io_enabled=True,
        )
    )
    with pytest.raises(ProductionWriterContractError, match="runtime authority"):
        replace(contract, **{field: True}, contract_sha256="")


def test_contract_cannot_drop_a_mandatory_cutover_blocker(tmp_path):
    contract = ProductionWriterCutoverContract.inspect(
        SandboxLedgerIntentWriter(
            tmp_path / "ledger.jsonl",
            sandbox_io_enabled=True,
        )
    )
    with pytest.raises(ProductionWriterContractError, match="mandatory.*blockers"):
        replace(
            contract,
            blockers=contract.blockers[1:],
            contract_sha256="",
        )


def test_contract_rejects_candidate_capability_or_authority_drift(tmp_path):
    class DriftedWriter(SandboxLedgerIntentWriter):
        @classmethod
        def descriptor(cls):
            return {
                **SandboxLedgerIntentWriter.descriptor(),
                "append_call_can_override_intent_identity": True,
            }

    with pytest.raises(ProductionWriterContractError, match="failed contract"):
        ProductionWriterCutoverContract.inspect(
            DriftedWriter(tmp_path / "ledger.jsonl", sandbox_io_enabled=True)
        )


def test_contract_descriptor_declares_observational_boundary():
    descriptor = ProductionWriterCutoverContract.descriptor()
    assert descriptor["observational_only"] is True
    assert descriptor["independent_cutover_review_required"] is True
    assert descriptor["runtime_registration"] is False
    assert descriptor["production_writes"] is False
    assert descriptor["state_store_commit"] is False
    assert descriptor["activation_performed"] is False
