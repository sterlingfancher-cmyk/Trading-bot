from __future__ import annotations

import ast
import json
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
    StateStoreInvariantError,
)

ROOT = Path(__file__).resolve().parent


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

    def test_descriptor_denies_runtime_authority(self) -> None:
        descriptor = CanonicalStateStore.descriptor()
        self.assertEqual(descriptor["authority"], "shadow_only")
        self.assertFalse(descriptor["production_write_enabled"])
        self.assertFalse(descriptor["runtime_registered"])
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
