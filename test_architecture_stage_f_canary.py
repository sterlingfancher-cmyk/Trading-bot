from __future__ import annotations

import ast
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from test_issue126_successor_accounting_reconcile_boundary import (
    Issue126SuccessorAccountingBoundaryTests,
)
from test_issue126_successor_compatibility import Issue126SuccessorCompatibilityTests
from test_verified_v3_successor_epoch_migration import Issue126V3V4SuccessorMigrationTests
from trading.canary import (
    CanaryEvidence,
    CanaryInvariantError,
    CanaryReadinessPlanner,
    RollbackReadinessEvidence,
)
from trading.accounting import (
    BaselineSnapshot,
    CanonicalAccountingProjector,
    ExecutionSnapshot,
)
from trading.risk import RiskLimits, ShadowRiskEngine
from trading.state import CanonicalStateSnapshot
from trading.state_store import CanonicalStateStore
from trading.valuation import DeterministicValuationService, ProtectedMarkSnapshot

ROOT = Path(__file__).resolve().parent


class StablePaperCoreStageFCanaryTests(unittest.TestCase):
    def _all_green(self) -> CanaryEvidence:
        return CanaryEvidence(
            issue_82_fresh_risk_day_pass=True,
            issue_82_forward_session_pass=True,
            clean_active_accounting_audit=True,
            canonical_ledger_chain_valid=True,
            protected_valuation_sane=True,
            stage_b_valuation_parity=True,
            stage_c_risk_parity=True,
            stage_d_restart_parity=True,
            stage_e_accounting_parity=True,
            single_revision_snapshot_binding=True,
            repository_validation_green=True,
            architecture_debt_gate_green=True,
            refactor_startup_audit_green=True,
        )

    def test_contract_remains_shadow_only(self) -> None:
        contract = json.loads((ROOT / "stable_paper_core_v3_stage_f_contract.json").read_text())
        self.assertEqual(contract["authority"], "shadow_only")
        constraints = contract["constraints"]
        self.assertFalse(constraints["runtime_registration"])
        self.assertFalse(constraints["production_state_writes"])
        self.assertFalse(constraints["order_authority"])
        self.assertTrue(constraints["rollback_switch_required"])
        self.assertTrue(constraints["rollback_default_armed"])
        self.assertTrue(constraints["single_revision_snapshot_binding_required"])
        self.assertTrue(
            constraints["ledger_total_and_epoch_row_provenance_required"]
        )
        self.assertTrue(constraints["ledger_sha256_provenance_required_for_runtime_evidence"])
        self.assertTrue(constraints["authoritative_v5_runtime_evidence_adapter_required"])
        self.assertTrue(constraints["explicit_cutover_state_machine_required"])
        self.assertTrue(constraints["reviewed_cutover_decision_required"])
        self.assertTrue(constraints["rollback_baseline_digest_required"])
        self.assertTrue(constraints["rollback_restore_drill_required"])
        self.assertTrue(constraints["rollback_restart_parity_required"])
        self.assertTrue(constraints["single_active_writer_required"])
        self.assertTrue(constraints["typed_stage_d_rollback_receipt_required"])
        self.assertTrue(constraints["readiness_cannot_activate_or_rollback"])

    def test_current_issue_82_missing_proof_blocks_canary(self) -> None:
        evidence = CanaryEvidence(
            issue_82_fresh_risk_day_pass=False,
            issue_82_forward_session_pass=False,
            clean_active_accounting_audit=False,
            canonical_ledger_chain_valid=True,
            protected_valuation_sane=True,
            stage_b_valuation_parity=True,
            stage_c_risk_parity=True,
            stage_d_restart_parity=True,
            stage_e_accounting_parity=False,
            single_revision_snapshot_binding=False,
            repository_validation_green=True,
            architecture_debt_gate_green=True,
            refactor_startup_audit_green=True,
        )
        plan = CanaryReadinessPlanner.plan(evidence=evidence, requested_fraction=0.01)
        self.assertFalse(plan.eligible_for_future_canary)
        self.assertIn("issue_82_fresh_risk_day_pass", plan.blockers)
        self.assertIn("issue_82_forward_session_pass", plan.blockers)
        self.assertIn("clean_active_accounting_audit", plan.blockers)
        self.assertIn("stage_e_accounting_parity", plan.blockers)
        self.assertIn("single_revision_snapshot_binding", plan.blockers)
        self.assertTrue(plan.rollback_default_armed)
        self.assertFalse(plan.production_state_writes)
        self.assertFalse(plan.order_authority)

    def test_all_required_evidence_only_marks_future_eligibility(self) -> None:
        plan = CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.01)
        self.assertTrue(plan.eligible_for_future_canary)
        self.assertEqual(plan.blockers, ())
        self.assertFalse(plan.runtime_registration)
        self.assertFalse(plan.production_state_writes)
        self.assertFalse(plan.order_authority)
        self.assertFalse(plan.risk_mutation_authority)

    def test_canary_fraction_is_bounded(self) -> None:
        with self.assertRaises(CanaryInvariantError):
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.0)
        with self.assertRaises(CanaryInvariantError):
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.051)
        self.assertEqual(
            CanaryReadinessPlanner.plan(evidence=self._all_green(), requested_fraction=0.05).requested_fraction,
            0.05,
        )

    def test_one_immutable_revision_binds_accounting_valuation_and_risk(self) -> None:
        accounting = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(cash=10000.0),
            executions=(
                ExecutionSnapshot(
                    1,
                    "QQQ",
                    "entry",
                    "long",
                    2,
                    100,
                    "2026-08-20 10:00",
                    "entry-1",
                ),
            ),
            marks={"QQQ": 105.0},
            today="2026-08-20",
        )
        marks = (
            ProtectedMarkSnapshot(
                "QQQ",
                105.0,
                "test-protected-mark",
                fresh=True,
                plausible=True,
                observed_at="2026-08-20 10:01",
            ),
        )
        valuation = DeterministicValuationService.value(
            cash=accounting.portfolio.cash,
            positions=accounting.portfolio.positions,
            marks=marks,
        )
        risk = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation,
            realized_today=accounting.portfolio.realized_today,
            limits=RiskLimits(0.03, 0.03, 0.03),
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=accounting.portfolio,
                risk=risk.state,
                execution_ledger_rows=accounting.execution_rows,
                execution_chain_valid=True,
            ),
            revision=7,
            created_at="2026-08-20 10:02",
        )

        proof = CanaryReadinessPlanner.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
        )
        self.assertTrue(proof.verified)
        self.assertEqual(proof.blockers, ())
        self.assertEqual(proof.revision, 7)
        self.assertEqual(proof.payload_sha256, envelope.payload_sha256)
        self.assertEqual(proof.ledger_total_rows, 1)
        self.assertEqual(proof.ledger_epoch_rows, 1)
        self.assertTrue(proof.rollback_default_armed)
        self.assertFalse(proof.production_state_writes)
        self.assertFalse(proof.risk_mutation_authority)
        self.assertFalse(proof.order_authority)

    def test_snapshot_binding_fails_closed_on_ledger_revision_drift(self) -> None:
        accounting = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(cash=10000.0),
            executions=(),
        )
        valuation = DeterministicValuationService.value(
            cash=accounting.portfolio.cash,
            positions=(),
            marks=(),
        )
        risk = ShadowRiskEngine.evaluate(
            date="2026-08-20",
            valuation=valuation,
            realized_today=0.0,
            limits=RiskLimits(0.03, 0.03, 0.03),
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=accounting.portfolio,
                risk=risk.state,
                execution_ledger_rows=1,
                execution_chain_valid=True,
            ),
            revision=8,
            created_at="2026-08-20 10:02",
        )

        proof = CanaryReadinessPlanner.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
        )
        self.assertFalse(proof.verified)
        self.assertEqual(proof.blockers, ("ledger_projection_row_count",))

    def test_successor_baseline_binds_total_and_zero_epoch_rows(self) -> None:
        accounting = CanonicalAccountingProjector.project(
            baseline=BaselineSnapshot(cash=13429.13048559457),
            executions=(),
        )
        valuation = DeterministicValuationService.value(
            cash=accounting.portfolio.cash,
            positions=(),
            marks=(),
        )
        risk = ShadowRiskEngine.evaluate(
            date="2026-09-16",
            valuation=valuation,
            realized_today=0.0,
            limits=RiskLimits(0.03, 0.03, 0.03),
        )
        envelope = CanonicalStateStore.prepare(
            snapshot=CanonicalStateSnapshot(
                portfolio=accounting.portfolio,
                risk=risk.state,
                execution_ledger_rows=88,
                execution_epoch_rows=0,
                execution_chain_valid=True,
            ),
            revision=9,
            created_at="2026-09-16 08:00",
        )

        proof = CanaryReadinessPlanner.verify_snapshot_binding(
            envelope=envelope,
            accounting=accounting,
            valuation=valuation,
            risk=risk,
        )
        self.assertTrue(proof.verified)
        self.assertEqual(proof.ledger_total_rows, 88)
        self.assertEqual(proof.ledger_epoch_rows, 0)

    def _v5_runtime_evidence(self):
        daily_audit = {
            "account": {
                "cash": 13429.13048559457,
                "equity": 13429.13,
                "positions": [],
                "realized_today": 0.0,
                "unrealized_pnl": 0.0,
            },
            "accounting_epoch": {
                "epoch_id": "stable-paper-v5-20260914-issue222-flat-successor01",
                "baseline_type": "verified_flat_snapshot_unresolved_prior_projection",
                "historical_evidence_archived": True,
                "validation_hold": True,
                "zero_trade_baseline": True,
            },
            "accounting_integrity": {
                "status": "ok",
                "coverage_complete": True,
                "coverage_issue_count": 0,
                "economic_issue_count": 0,
            },
            "execution_ledger": {
                "chain_valid": True,
                "ledger_sha256": "a" * 64,
                "row_count": 88,
                "current_epoch_id": "stable-paper-v5-20260914-issue222-flat-successor01",
                "current_epoch_rows": 0,
                "state_current_epoch_rows": 0,
                "state_projection_parity": True,
                "missing_from_state_count": 0,
                "missing_from_ledger_count": 0,
            },
            "risk": {
                "halted": True,
                "halt_reason": "canonical execution/state projection divergence",
                "net_daily_loss_pct": 0.0,
                "intraday_drawdown_pct": 0.0,
            },
        }
        paper_status = {
            "cash": 13429.13,
            "equity": 13429.13,
            "positions": {},
            "recent_trades": [],
            "realized_pnl": {"total": 3429.13048559457, "today": 0.0},
        }
        fresh_day = {
            "baseline_status": "pass",
            "date": "2026-09-16",
            "day_start_equity": 13429.13048559457,
            "day_peak_equity": 13429.13048559457,
            "fresh_day_reset_pending": False,
            "halted": True,
            "halt_reason": "canonical execution/state projection divergence",
        }
        return daily_audit, paper_status, fresh_day

    def test_current_v5_runtime_evidence_binds_exact_provenance(self) -> None:
        audit, status, day = self._v5_runtime_evidence()
        binding = CanaryReadinessPlanner.bind_verified_flat_v5_runtime_evidence(
            daily_audit=audit,
            paper_status=status,
            fresh_day=day,
            ledger_sha256="a" * 64,
            revision=10,
            captured_at="2026-09-16 09:02:35 CDT",
        )

        self.assertTrue(binding.proof.verified)
        self.assertEqual(binding.proof.ledger_total_rows, 88)
        self.assertEqual(binding.proof.ledger_epoch_rows, 0)
        self.assertEqual(binding.proof.ledger_sha256, "a" * 64)
        self.assertEqual(
            binding.proof.epoch_id,
            "stable-paper-v5-20260914-issue222-flat-successor01",
        )
        self.assertEqual(binding.proof.evidence_source, "https://web-production-e1796.up.railway.app")
        self.assertFalse(binding.production_state_writes)
        self.assertFalse(binding.order_authority)

    def test_v5_runtime_adapter_rejects_incomplete_or_drifting_provenance(self) -> None:
        audit, status, day = self._v5_runtime_evidence()
        cases = []

        wrong_rows = {
            **copy.deepcopy(audit),
            "execution_ledger": {
                **audit["execution_ledger"],
                "state_current_epoch_rows": 1,
            },
        }
        cases.append((wrong_rows, status, day, "a" * 64, "https://web-production-e1796.up.railway.app"))

        economic_drift = {
            **copy.deepcopy(audit),
            "account": {**audit["account"], "equity": 13429.12},
        }
        cases.append((economic_drift, status, day, "a" * 64, "https://web-production-e1796.up.railway.app"))

        cases.append((audit, status, day, "missing", "https://web-production-e1796.up.railway.app"))
        cases.append((audit, status, day, "a" * 64, "https://trading-bot-clean.up.railway.app"))

        for row_audit, row_status, row_day, digest, source in cases:
            with self.subTest(digest=digest, source=source, equity=row_audit["account"]["equity"]):
                with self.assertRaises(CanaryInvariantError):
                    CanaryReadinessPlanner.bind_verified_flat_v5_runtime_evidence(
                        daily_audit=row_audit,
                        paper_status=row_status,
                        fresh_day=row_day,
                        ledger_sha256=digest,
                        revision=10,
                        captured_at="2026-09-16 09:02:35 CDT",
                        source_url=source,
                    )

    def _v5_binding(self):
        audit, status, day = self._v5_runtime_evidence()
        return CanaryReadinessPlanner.bind_verified_flat_v5_runtime_evidence(
            daily_audit=audit,
            paper_status=status,
            fresh_day=day,
            ledger_sha256="a" * 64,
            revision=10,
            captured_at="2026-09-16 09:02:35 CDT",
        )

    def _rollback_evidence(self, binding):
        return RollbackReadinessEvidence(
            baseline_revision=binding.proof.revision,
            baseline_payload_sha256=binding.proof.payload_sha256,
            baseline_ledger_sha256=binding.proof.ledger_sha256,
            archived_baseline_present=True,
            restore_drill_passed=True,
            restart_parity_passed=True,
            single_writer_exclusivity_passed=True,
        )

    def test_current_v5_hold_and_halt_block_cutover_readiness(self) -> None:
        binding = self._v5_binding()
        decision = CanaryReadinessPlanner.evaluate_cutover_readiness(
            binding=binding,
            canary_plan=CanaryReadinessPlanner.plan(
                evidence=self._all_green(), requested_fraction=0.01
            ),
            rollback=self._rollback_evidence(binding),
        )

        self.assertEqual(decision.state, "blocked")
        self.assertIn("validation_hold_released", decision.blockers)
        self.assertIn("risk_halt_released_by_governed_evidence", decision.blockers)
        self.assertFalse(decision.cutover_review_completed)
        self.assertFalse(decision.activation_performed)
        self.assertFalse(decision.rollback_performed)
        self.assertFalse(decision.runtime_registration)
        self.assertFalse(decision.production_state_writes)

    def test_stage_d_drill_receipt_binds_stage_f_rollback_readiness(self) -> None:
        binding = self._v5_binding()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical-state.json"
            archive_path = Path(tmp) / "rollback-baseline.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            store.commit_sandbox(binding.envelope)
            baseline_snapshot = binding.envelope.snapshot()
            canary_snapshot = replace(
                baseline_snapshot,
                portfolio=replace(
                    baseline_snapshot.portfolio,
                    cash=baseline_snapshot.portfolio.cash - 1.0,
                    equity=baseline_snapshot.portfolio.equity - 1.0,
                ),
            )
            receipt = store.run_rollback_drill_sandbox(
                archive_path,
                canary_envelope=store.prepare(
                    snapshot=canary_snapshot,
                    revision=binding.proof.revision + 1,
                    created_at="2026-09-20 10:00:00 CDT",
                ),
                restored_created_at="2026-09-20 10:01:00 CDT",
            )

        rollback = RollbackReadinessEvidence.from_drill_receipt(
            receipt=receipt,
            baseline_ledger_sha256=binding.proof.ledger_sha256,
        )
        self.assertEqual(rollback.baseline_revision, binding.proof.revision)
        self.assertEqual(
            rollback.baseline_payload_sha256,
            binding.proof.payload_sha256,
        )
        self.assertEqual(rollback.blockers(binding.proof), ())

        decision = CanaryReadinessPlanner.evaluate_cutover_readiness(
            binding=binding,
            canary_plan=CanaryReadinessPlanner.plan(
                evidence=self._all_green(), requested_fraction=0.01
            ),
            rollback=rollback,
        )
        self.assertEqual(decision.state, "blocked")
        self.assertEqual(
            decision.blockers,
            (
                "validation_hold_released",
                "risk_halt_released_by_governed_evidence",
            ),
        )
        self.assertFalse(decision.activation_performed)
        self.assertFalse(decision.runtime_registration)
        self.assertFalse(decision.production_state_writes)

    def test_stage_f_rejects_untyped_rollback_claim(self) -> None:
        with self.assertRaises(CanaryInvariantError):
            RollbackReadinessEvidence.from_drill_receipt(
                receipt={"restore_drill_passed": True},
                baseline_ledger_sha256="a" * 64,
            )

    def test_cutover_readiness_fails_closed_on_rollback_drift(self) -> None:
        binding = self._v5_binding()
        rollback = RollbackReadinessEvidence(
            baseline_revision=binding.proof.revision + 1,
            baseline_payload_sha256="b" * 64,
            baseline_ledger_sha256=binding.proof.ledger_sha256,
            archived_baseline_present=True,
            restore_drill_passed=False,
            restart_parity_passed=True,
            single_writer_exclusivity_passed=True,
        )
        decision = CanaryReadinessPlanner.evaluate_cutover_readiness(
            binding=binding,
            canary_plan=CanaryReadinessPlanner.plan(
                evidence=self._all_green(), requested_fraction=0.01
            ),
            rollback=rollback,
        )

        self.assertEqual(decision.state, "blocked")
        self.assertIn("rollback_baseline_revision", decision.blockers)
        self.assertIn("rollback_payload_digest", decision.blockers)
        self.assertIn("restore_drill_passed", decision.blockers)
        self.assertFalse(decision.activation_performed)

    def test_rollback_trigger_assessment_is_observational_and_fail_closed(self) -> None:
        healthy = CanaryReadinessPlanner.assess_rollback_triggers(
            canonical_chain_valid=True,
            state_projection_parity=True,
            accounting_parity=True,
            valuation_parity=True,
            risk_parity=True,
            restart_parity=True,
            active_writer_count=1,
        )
        self.assertFalse(healthy.rollback_required)
        self.assertEqual(healthy.triggers, ())

        failed = CanaryReadinessPlanner.assess_rollback_triggers(
            canonical_chain_valid=True,
            state_projection_parity=False,
            accounting_parity=True,
            valuation_parity=False,
            risk_parity=True,
            restart_parity=True,
            active_writer_count=2,
        )
        self.assertTrue(failed.rollback_required)
        self.assertEqual(
            failed.triggers,
            (
                "state_projection_divergence",
                "valuation_divergence",
                "writer_ownership_violation",
            ),
        )
        self.assertFalse(failed.activation_performed)
        self.assertFalse(failed.rollback_performed)

    def test_planner_descriptor_is_callable_and_cannot_claim_activation(self) -> None:
        descriptor = CanaryReadinessPlanner.descriptor()
        self.assertTrue(descriptor["cutover_review_required"])
        self.assertTrue(descriptor["rollback_readiness_required"])
        self.assertFalse(descriptor["cutover_review_completed"])
        self.assertFalse(descriptor["activation_performed"])
        self.assertFalse(descriptor["runtime_registration"])
        self.assertFalse(descriptor["production_state_writes"])

    def test_module_has_no_runtime_or_write_authority(self) -> None:
        path = ROOT / "trading" / "canary.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        forbidden_imports = {
            "app",
            "state_io_hardening",
            "alpaca_trade_api",
            "yfinance",
            "flask",
            "os",
            "threading",
        }
        forbidden_calls = {
            "save_state",
            "load_state",
            "submit_order",
            "place_order",
            "enter_position",
            "exit_position",
            "install",
            "apply",
            "register_routes",
            "open",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                self.assertNotIn(name, forbidden_calls)


if __name__ == "__main__":
    unittest.main()
