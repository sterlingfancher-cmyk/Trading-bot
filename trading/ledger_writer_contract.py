"""Read-only production-writer interface contract for Issue #84.

The accepted sandbox writer proves exact durable-intent mechanics.  This module
defines the interface a later production adapter must implement and records why
cutover is still blocked.  Inspection is observational: it never calls the
writer, registers runtime authority, commits StateStore, or approves cutover.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from trading.ledger import LedgerAppendIntent, LedgerAppendObservation
from trading.state_store import CanonicalStateEnvelope
from trading.transaction_journal import AppendIntentJournalRecord


VERSION = "stable-paper-core-v3-production-writer-contract-2026-10-20-v1"
AUTHORITY = "shadow_only"
CURRENT_OWNER = "canonical_execution_ledger.append_execution"
TARGET_INTERFACE = "trading.ledger_writer_contract.LedgerIntentWriter"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ProductionWriterContractError(ValueError):
    """Raised when a writer candidate could weaken the cutover boundary."""


@runtime_checkable
class LedgerIntentWriter(Protocol):
    """Exact append interface required from any future production adapter."""

    authority: str
    runtime_registered: bool
    production_write_enabled: bool
    places_orders: bool

    def append_intent(
        self,
        intent: LedgerAppendIntent,
        record: AppendIntentJournalRecord,
        current_state: CanonicalStateEnvelope,
    ) -> LedgerAppendObservation: ...

    def descriptor(self) -> Mapping[str, Any]: ...


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ProductionWriterCutoverContract:
    """Digest-bound inspection result that cannot activate a writer."""

    candidate_interface: str
    candidate_descriptor_sha256: str
    blockers: tuple[str, ...]
    current_owner: str = CURRENT_OWNER
    target_interface: str = TARGET_INTERFACE
    state: str = "blocked"
    independent_review_completed: bool = False
    activation_performed: bool = False
    runtime_registration: bool = False
    production_writes: bool = False
    state_store_commit: bool = False
    order_authority: bool = False
    live_authority: bool = False
    ml_execution_authority: bool = False
    contract_sha256: str = ""
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        descriptor_digest = str(self.candidate_descriptor_sha256 or "").lower()
        if not _SHA256.fullmatch(descriptor_digest):
            raise ProductionWriterContractError(
                "candidate descriptor requires an exact SHA-256 digest"
            )
        object.__setattr__(self, "candidate_descriptor_sha256", descriptor_digest)
        blockers = tuple(str(value) for value in self.blockers)
        if self.state != "blocked" or not blockers:
            raise ProductionWriterContractError(
                "unreviewed production-writer cutover must remain blocked"
            )
        required = {
            "independent_cutover_review",
            "production_adapter_implementation",
            "runtime_single_writer_registration",
            "state_store_commit_coordinator",
            "rollback_switch_default_armed",
        }
        if not required.issubset(blockers):
            raise ProductionWriterContractError(
                "production-writer contract omitted mandatory cutover blockers"
            )
        if self.authority != AUTHORITY or any(
            (
                self.independent_review_completed,
                self.activation_performed,
                self.runtime_registration,
                self.production_writes,
                self.state_store_commit,
                self.order_authority,
                self.live_authority,
                self.ml_execution_authority,
            )
        ):
            raise ProductionWriterContractError(
                "production-writer contract cannot hold runtime authority"
            )
        object.__setattr__(self, "blockers", blockers)
        expected = sha256(_canonical_json(self._digest_payload()).encode()).hexdigest()
        supplied = str(self.contract_sha256 or "").lower()
        if supplied and supplied != expected:
            raise ProductionWriterContractError("cutover contract digest mismatch")
        object.__setattr__(self, "contract_sha256", expected)

    def _digest_payload(self) -> Mapping[str, Any]:
        return {
            "authority": self.authority,
            "version": self.version,
            "state": self.state,
            "blockers": self.blockers,
            "current_owner": self.current_owner,
            "target_interface": self.target_interface,
            "candidate_interface": self.candidate_interface,
            "candidate_descriptor_sha256": self.candidate_descriptor_sha256,
            "independent_review_completed": self.independent_review_completed,
            "activation_performed": self.activation_performed,
            "runtime_registration": self.runtime_registration,
            "production_writes": self.production_writes,
            "state_store_commit": self.state_store_commit,
            "order_authority": self.order_authority,
            "live_authority": self.live_authority,
            "ml_execution_authority": self.ml_execution_authority,
        }

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {**self._digest_payload(), "contract_sha256": self.contract_sha256}
        )

    @classmethod
    def inspect(cls, candidate: LedgerIntentWriter) -> "ProductionWriterCutoverContract":
        """Inspect one inactive candidate without invoking its append method."""
        if not isinstance(candidate, LedgerIntentWriter):
            raise ProductionWriterContractError(
                "candidate does not implement the durable-intent writer interface"
            )
        descriptor = candidate.descriptor()
        if not isinstance(descriptor, Mapping):
            raise ProductionWriterContractError("writer descriptor must be a mapping")
        required_true = (
            "accepts_durable_append_intent",
            "durable_intent_record_required",
            "unchanged_state_required",
            "validates_full_hash_chain",
            "idempotent_partial_append_recovery",
            "interprocess_locking",
        )
        required_false = (
            "append_call_can_override_intent_identity",
            "commits_state_store",
            "production_writer_connected",
            "runtime_registered",
            "production_write_enabled",
            "places_orders",
        )
        failed = tuple(
            f"candidate_capability:{name}"
            for name in required_true
            if descriptor.get(name) is not True
        ) + tuple(
            f"candidate_authority:{name}"
            for name in required_false
            if descriptor.get(name) is not False
        )
        if failed:
            raise ProductionWriterContractError(
                "writer candidate failed contract inspection: " + ",".join(failed)
            )
        normalized = dict(descriptor)
        digest = sha256(_canonical_json(normalized).encode()).hexdigest()
        return cls(
            candidate_interface=str(descriptor.get("target_interface") or ""),
            candidate_descriptor_sha256=digest,
            blockers=(
                "independent_cutover_review",
                "production_adapter_implementation",
                "runtime_single_writer_registration",
                "state_store_commit_coordinator",
                "rollback_switch_default_armed",
            ),
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": TARGET_INTERFACE,
                "current_owner": CURRENT_OWNER,
                "authority": AUTHORITY,
                "observational_only": True,
                "independent_cutover_review_required": True,
                "runtime_registration": False,
                "production_writes": False,
                "state_store_commit": False,
                "activation_performed": False,
                "order_authority": False,
                "live_authority": False,
                "ml_execution_authority": False,
                "version": VERSION,
            }
        )
