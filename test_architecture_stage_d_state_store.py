from __future__ import annotations

import ast
from dataclasses import replace
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from trading.state import (
    AccountingEpochSnapshot,
    CanonicalStateSnapshot,
    PortfolioSnapshot,
    PositionSnapshot,
    RiskStateSnapshot,
)
from trading.state_store import (
    CanonicalStateEnvelope,
    CanonicalStateStore,
    RollbackDrillReceipt,
    StateStoreInvariantError,
)

ROOT = Path(__file__).resolve().parent


def _commit_in_process(
    path: str,
    revision: int,
    result_queue,
    entered=None,
    release=None,
) -> None:
    store = CanonicalStateStore(path, sandbox_io_enabled=True)
    if entered is not None and release is not None:
        original_read = store._read_envelope_file

        def delayed_read(target):
            current = original_read(target)
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release delayed commit")
            return current

        store._read_envelope_file = delayed_read
    envelope = store.prepare(
        snapshot=_snapshot(),
        revision=revision,
        created_at=f"2026-08-20 17:0{revision}:00 CDT",
    )
    try:
        store.commit_sandbox(envelope)
    except Exception as exc:
        result_queue.put(type(exc).__name__)
    else:
        result_queue.put("ok")


def _restore_in_process(
    path: str,
    archive_path: str,
    result_queue,
    entered,
    release,
) -> None:
    store = CanonicalStateStore(path, sandbox_io_enabled=True)
    original_read = store._read_envelope_file
    paused = False

    def delayed_read(target):
        nonlocal paused
        current = original_read(target)
        if Path(target) == store.path and not paused:
            paused = True
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release delayed rollback restore")
        return current

    store._read_envelope_file = delayed_read
    try:
        restored = store.restore_sandbox(
            archive_path,
            expected_current_revision=2,
            created_at="2026-09-19 16:00:00 CDT",
        )
    except Exception as exc:
        result_queue.put(type(exc).__name__)
    else:
        result_queue.put(f"ok:{restored.revision}")


def _drill_in_process(
    path: str,
    archive_path: str,
    result_queue,
    entered,
    release,
) -> None:
    store = CanonicalStateStore(path, sandbox_io_enabled=True)
    original_read = store._read_envelope_file
    paused = False

    def delayed_read(target):
        nonlocal paused
        current = original_read(target)
        if Path(target) == store.path and not paused:
            paused = True
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release delayed rollback drill")
        return current

    store._read_envelope_file = delayed_read
    baseline = _snapshot()
    canary_snapshot = replace(
        baseline,
        portfolio=replace(baseline.portfolio, cash=7900.0, equity=9950.0),
    )
    try:
        receipt = store.run_rollback_drill_sandbox(
            archive_path,
            canary_envelope=store.prepare(
                snapshot=canary_snapshot,
                revision=2,
                created_at="2026-09-20 10:01:00 CDT",
            ),
            restored_created_at="2026-09-20 10:02:00 CDT",
        )
    except Exception as exc:
        result_queue.put(type(exc).__name__)
    else:
        result_queue.put(f"ok:{receipt.restored_revision}")


def _snapshot() -> CanonicalStateSnapshot:
    epoch = AccountingEpochSnapshot(
        epoch_id="stable-paper-v3-test",
        baseline_type="verified_snapshot",
        historical_evidence_archived=True,
        validation_hold=False,
    )
    portfolio = PortfolioSnapshot(
        cash=8000.0,
        equity=10050.0,
        realized_total=50.0,
        realized_today=10.0,
        unrealized_pnl=50.0,
        positions=(
            PositionSnapshot(
                symbol="QQQ",
                side="long",
                quantity=2.0,
                entry_price=1000.0,
                mark_price=1025.0,
            ),
        ),
        accounting_epoch=epoch,
    )
    risk = RiskStateSnapshot(
        date="2026-08-20",
        day_start_equity=10000.0,
        day_peak_equity=10100.0,
        daily_loss_fraction=0.0,
        intraday_drawdown_fraction=(10100.0 - 10050.0) / 10100.0,
        halted=False,
        halt_reason="",
    )
    return CanonicalStateSnapshot(
        portfolio=portfolio,
        risk=risk,
        execution_ledger_rows=303,
        execution_epoch_rows=3,
        execution_chain_valid=True,
    )


class StablePaperCoreStageDStateStoreTests(unittest.TestCase):
    def test_contract_remains_shadow_only(self) -> None:
        contract = json.loads(
            (ROOT / "stable_paper_core_v3_stage_d_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["authority"], "shadow_only")
        self.assertFalse(contract["production_write_enabled"])
        self.assertFalse(contract["runtime_registered"])
        self.assertTrue(contract["constraints"]["restart_round_trip_parity_required"])
        self.assertTrue(contract["constraints"]["rollback_archive_immutable"])
        self.assertTrue(
            contract["constraints"]["rollback_restore_monotonic_revision"]
        )
        self.assertTrue(
            contract["constraints"]["rollback_uses_same_exclusive_process_lock"]
        )
        self.assertTrue(
            contract["constraints"]["typed_rollback_drill_receipt_required"]
        )
        self.assertTrue(
            contract["constraints"]["rollback_drill_single_lock_scope_required"]
        )
        self.assertTrue(
            contract["constraints"]["cross_instance_process_serialization_required"]
        )
        self.assertIn(
            "issue_82_prospective_fresh_day_acceptance",
            contract["promotion_blockers"],
        )

    def test_envelope_round_trip_preserves_canonical_economics(self) -> None:
        snapshot = _snapshot()
        envelope = CanonicalStateStore.prepare(
            snapshot=snapshot,
            revision=7,
            created_at="2026-08-20 17:05:00 CDT",
        )
        rebuilt = envelope.snapshot()
        self.assertEqual(rebuilt.portfolio.cash, snapshot.portfolio.cash)
        self.assertEqual(rebuilt.portfolio.equity, snapshot.portfolio.equity)
        self.assertEqual(rebuilt.risk.day_start_equity, snapshot.risk.day_start_equity)
        self.assertEqual(rebuilt.risk.day_peak_equity, snapshot.risk.day_peak_equity)
        self.assertEqual(rebuilt.execution_ledger_rows, 303)
        self.assertEqual(rebuilt.execution_epoch_rows, 3)
        self.assertTrue(rebuilt.execution_chain_valid)
        self.assertIsNotNone(rebuilt.portfolio.accounting_epoch)
        self.assertEqual(
            rebuilt.portfolio.accounting_epoch.epoch_id,
            "stable-paper-v3-test",
        )

    def test_digest_tampering_fails_closed(self) -> None:
        envelope = CanonicalStateStore.prepare(
            snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
        )
        raw = dict(envelope.to_dict())
        payload = dict(raw["payload"])
        portfolio = dict(payload["portfolio"])
        portfolio["equity"] = 1.0
        payload["portfolio"] = portfolio
        with self.assertRaises(StateStoreInvariantError):
            CanonicalStateEnvelope(
                schema_version=raw["schema_version"],
                authority=raw["authority"],
                version=raw["version"],
                revision=raw["revision"],
                created_at=raw["created_at"],
                payload_sha256=raw["payload_sha256"],
                payload=payload,
            )

    def test_envelope_payload_is_deeply_immutable(self) -> None:
        envelope = CanonicalStateStore.prepare(
            snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
        )

        with self.assertRaises(TypeError):
            envelope.payload["portfolio"]["cash"] = 1.0
        with self.assertRaises(TypeError):
            envelope.payload["portfolio"]["positions"][0]["quantity"] = 999.0

        rebuilt = envelope.snapshot()
        self.assertEqual(rebuilt.portfolio.cash, 8000.0)
        self.assertEqual(rebuilt.portfolio.positions[0].quantity, 2.0)

    def test_mutating_exported_plain_payload_cannot_change_envelope(self) -> None:
        envelope = CanonicalStateStore.prepare(
            snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
        )
        exported = envelope.to_dict()
        exported["payload"]["portfolio"]["cash"] = 1.0

        self.assertEqual(envelope.snapshot().portfolio.cash, 8000.0)
        self.assertEqual(
            envelope.payload_sha256,
            CanonicalStateStore.prepare(
                snapshot=_snapshot(),
                revision=1,
                created_at="2026-08-20 17:05:00 CDT",
            ).payload_sha256,
        )

    def test_production_io_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStateStore(Path(tmp) / "state.json")
            envelope = store.prepare(
                snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
            )
            with self.assertRaises(PermissionError):
                store.commit_sandbox(envelope)
            with self.assertRaises(PermissionError):
                store.read_sandbox()
            with self.assertRaises(PermissionError):
                store.archive_sandbox(Path(tmp) / "rollback.json")
            with self.assertRaises(PermissionError):
                store.restore_sandbox(
                    Path(tmp) / "rollback.json",
                    expected_current_revision=1,
                    created_at="2026-09-19 16:00:00 CDT",
                )
            with self.assertRaises(PermissionError):
                store.run_rollback_drill_sandbox(
                    Path(tmp) / "rollback.json",
                    canary_envelope=store.prepare(
                        snapshot=_snapshot(),
                        revision=2,
                        created_at="2026-09-20 10:01:00 CDT",
                    ),
                    restored_created_at="2026-09-20 10:02:00 CDT",
                )
            self.assertFalse((Path(tmp) / "state.json").exists())

    def test_atomic_sandbox_commit_and_restart_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            envelope = store.prepare(
                snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
            )
            store.commit_sandbox(envelope)
            self.assertTrue(path.exists())

            restarted = CanonicalStateStore(path, sandbox_io_enabled=True)
            loaded = restarted.read_sandbox()
            self.assertEqual(loaded.revision, 1)
            self.assertEqual(loaded.payload_sha256, envelope.payload_sha256)
            self.assertEqual(loaded.snapshot().portfolio.equity, 10050.0)
            self.assertEqual(loaded.snapshot().execution_ledger_rows, 303)
            self.assertEqual(loaded.snapshot().execution_epoch_rows, 3)
            self.assertTrue(loaded.snapshot().execution_chain_valid)

    def test_revision_must_increase_and_backup_preserves_prior_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            first = store.prepare(
                snapshot=_snapshot(), revision=1, created_at="2026-08-20 17:05:00 CDT"
            )
            store.commit_sandbox(first)
            with self.assertRaises(StateStoreInvariantError):
                store.commit_sandbox(first)

            second = store.prepare(
                snapshot=_snapshot(), revision=2, created_at="2026-08-20 17:06:00 CDT"
            )
            store.commit_sandbox(second)
            self.assertEqual(store.read_sandbox().revision, 2)
            self.assertTrue(store.backup_path.exists())
            backup_raw = json.loads(store.backup_path.read_text(encoding="utf-8"))
            self.assertEqual(backup_raw["revision"], 1)

    def test_same_revision_commits_are_serialized_across_processes(self) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=1,
                    created_at="2026-08-20 17:01:00 CDT",
                )
            )

            results = context.Queue()
            entered = context.Event()
            release = context.Event()
            first = context.Process(
                target=_commit_in_process,
                args=(str(path), 2, results, entered, release),
            )
            second = context.Process(
                target=_commit_in_process,
                args=(str(path), 2, results),
            )
            first.start()
            self.assertTrue(entered.wait(timeout=5))
            second.start()
            second.join(timeout=0.25)
            self.assertTrue(
                second.is_alive(),
                "competing commit bypassed the held StateStore process lock",
            )

            release.set()
            first.join(timeout=5)
            second.join(timeout=5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(
                sorted((results.get(timeout=2), results.get(timeout=2))),
                ["StateStoreInvariantError", "ok"],
            )
            self.assertEqual(store.read_sandbox().revision, 2)
            self.assertTrue(store.lock_path.exists())

    def test_rollback_archive_restore_preserves_lineage_and_restart_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            archive_path = Path(tmp) / "rollback-revision-1.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            baseline = store.prepare(
                snapshot=_snapshot(),
                revision=1,
                created_at="2026-09-19 15:45:00 CDT",
            )
            store.commit_sandbox(baseline)
            archived = store.archive_sandbox(archive_path)
            archive_bytes = archive_path.read_bytes()

            baseline_snapshot = _snapshot()
            canary_snapshot = replace(
                baseline_snapshot,
                portfolio=replace(
                    baseline_snapshot.portfolio,
                    cash=7900.0,
                    equity=9950.0,
                ),
            )
            canary = store.prepare(
                snapshot=canary_snapshot,
                revision=2,
                created_at="2026-09-19 15:50:00 CDT",
            )
            store.commit_sandbox(canary)
            restored = store.restore_sandbox(
                archive_path,
                expected_current_revision=2,
                created_at="2026-09-19 15:55:00 CDT",
            )

            self.assertEqual(restored.revision, 3)
            self.assertEqual(restored.payload_sha256, baseline.payload_sha256)
            self.assertNotEqual(canary.payload_sha256, baseline.payload_sha256)
            self.assertEqual(restored.snapshot().portfolio.cash, 8000.0)
            self.assertEqual(archived.revision, 1)
            self.assertEqual(archive_path.read_bytes(), archive_bytes)
            backup = store._read_envelope_file(store.backup_path)
            self.assertEqual(backup.revision, 2)
            self.assertEqual(backup.payload_sha256, canary.payload_sha256)

            restarted = CanonicalStateStore(path, sandbox_io_enabled=True)
            loaded = restarted.read_sandbox()
            self.assertEqual(loaded.revision, 3)
            self.assertEqual(loaded.payload_sha256, baseline.payload_sha256)

    def test_rollback_archive_is_immutable_and_stale_restore_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            archive_path = Path(tmp) / "rollback.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=1,
                    created_at="2026-09-19 15:45:00 CDT",
                )
            )
            store.archive_sandbox(archive_path)
            archive_bytes = archive_path.read_bytes()
            with self.assertRaises(FileExistsError):
                store.archive_sandbox(archive_path)

            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=2,
                    created_at="2026-09-19 15:50:00 CDT",
                )
            )
            state_bytes = path.read_bytes()
            with self.assertRaises(StateStoreInvariantError):
                store.restore_sandbox(
                    archive_path,
                    expected_current_revision=1,
                    created_at="2026-09-19 15:55:00 CDT",
                )
            self.assertEqual(path.read_bytes(), state_bytes)
            self.assertEqual(archive_path.read_bytes(), archive_bytes)

    def test_rollback_restore_serializes_single_writer_handoff(self) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            archive_path = Path(tmp) / "rollback.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=1,
                    created_at="2026-09-19 15:40:00 CDT",
                )
            )
            store.archive_sandbox(archive_path)
            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=2,
                    created_at="2026-09-19 15:45:00 CDT",
                )
            )

            results = context.Queue()
            entered = context.Event()
            release = context.Event()
            rollback = context.Process(
                target=_restore_in_process,
                args=(str(path), str(archive_path), results, entered, release),
            )
            competing = context.Process(
                target=_commit_in_process,
                args=(str(path), 3, results),
            )
            rollback.start()
            self.assertTrue(entered.wait(timeout=5))
            competing.start()
            competing.join(timeout=0.25)
            self.assertTrue(
                competing.is_alive(),
                "competing writer bypassed the rollback restore process lock",
            )

            release.set()
            rollback.join(timeout=5)
            competing.join(timeout=5)
            self.assertFalse(rollback.is_alive())
            self.assertFalse(competing.is_alive())
            self.assertEqual(
                sorted((results.get(timeout=2), results.get(timeout=2))),
                ["StateStoreInvariantError", "ok:3"],
            )
            self.assertEqual(store.read_sandbox().revision, 3)

    def test_complete_rollback_drill_emits_typed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            archive_path = Path(tmp) / "rollback.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            baseline_snapshot = _snapshot()
            baseline = store.prepare(
                snapshot=baseline_snapshot,
                revision=7,
                created_at="2026-09-20 09:55:00 CDT",
            )
            store.commit_sandbox(baseline)
            canary = store.prepare(
                snapshot=replace(
                    baseline_snapshot,
                    portfolio=replace(
                        baseline_snapshot.portfolio,
                        cash=7900.0,
                        equity=9950.0,
                    ),
                ),
                revision=8,
                created_at="2026-09-20 10:00:00 CDT",
            )

            receipt = store.run_rollback_drill_sandbox(
                archive_path,
                canary_envelope=canary,
                restored_created_at="2026-09-20 10:01:00 CDT",
            )

            self.assertIsInstance(receipt, RollbackDrillReceipt)
            self.assertEqual(receipt.baseline_revision, 7)
            self.assertEqual(receipt.canary_revision, 8)
            self.assertEqual(receipt.restored_revision, 9)
            self.assertEqual(receipt.baseline_payload_sha256, baseline.payload_sha256)
            self.assertEqual(receipt.restored_payload_sha256, baseline.payload_sha256)
            self.assertEqual(receipt.backup_canary_payload_sha256, canary.payload_sha256)
            self.assertTrue(receipt.archive_immutable)
            self.assertTrue(receipt.restart_parity_passed)
            self.assertTrue(receipt.single_writer_exclusivity_passed)
            self.assertFalse(receipt.runtime_registration)
            self.assertFalse(receipt.production_state_writes)
            self.assertEqual(store.read_sandbox().revision, 9)

    def test_complete_rollback_drill_holds_one_lock_across_handoff(self) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical_state.json"
            archive_path = Path(tmp) / "rollback.json"
            store = CanonicalStateStore(path, sandbox_io_enabled=True)
            store.commit_sandbox(
                store.prepare(
                    snapshot=_snapshot(),
                    revision=1,
                    created_at="2026-09-20 10:00:00 CDT",
                )
            )

            results = context.Queue()
            entered = context.Event()
            release = context.Event()
            drill = context.Process(
                target=_drill_in_process,
                args=(str(path), str(archive_path), results, entered, release),
            )
            competing = context.Process(
                target=_commit_in_process,
                args=(str(path), 2, results),
            )
            drill.start()
            self.assertTrue(entered.wait(timeout=5))
            competing.start()
            competing.join(timeout=0.25)
            self.assertTrue(
                competing.is_alive(),
                "competing writer bypassed the full rollback drill lock",
            )

            release.set()
            drill.join(timeout=5)
            competing.join(timeout=5)
            self.assertFalse(drill.is_alive())
            self.assertFalse(competing.is_alive())
            self.assertEqual(
                sorted((results.get(timeout=2), results.get(timeout=2))),
                ["StateStoreInvariantError", "ok:3"],
            )
            self.assertEqual(store.read_sandbox().revision, 3)

    def test_descriptor_denies_runtime_authority(self) -> None:
        descriptor = CanonicalStateStore.descriptor()
        self.assertEqual(descriptor["authority"], "shadow_only")
        self.assertFalse(descriptor["production_write_enabled"])
        self.assertFalse(descriptor["runtime_registered"])
        self.assertTrue(descriptor["interprocess_locking"])
        self.assertFalse(descriptor["reads_environment"])
        self.assertFalse(descriptor["places_orders"])

    def test_module_has_no_runtime_registration_or_environment_reads(self) -> None:
        path = ROOT / "trading" / "state_store.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {
            "app",
            "state_io_hardening",
            "alpaca_trade_api",
            "yfinance",
        }
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
            "load_state",
            "register_routes",
            "install",
            "apply",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".", 1)[0], forbidden_imports)
            elif isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                self.assertNotIn(name, forbidden_calls)
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    self.assertFalse(
                        func.value.id == "os" and func.attr in {"getenv"},
                        "Stage D StateStore must not read environment configuration",
                    )


if __name__ == "__main__":
    unittest.main()
