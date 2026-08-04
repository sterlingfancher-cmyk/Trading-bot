from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from state_store_shadow import StateStoreDescriptor

ROOT = Path(__file__).resolve().parent


class StateStoreShadowTests(unittest.TestCase):
    def test_contract_is_read_only_and_non_authoritative(self) -> None:
        contract = json.loads(
            (ROOT / "state_store_contract.json").read_text(encoding="utf-8")
        )
        policy = contract["policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["authoritative_runtime_source"])
        self.assertFalse(policy["replaces_save_state"])
        self.assertFalse(policy["changes_state_path"])
        self.assertTrue(policy["migration_requires_output_parity"])

    def test_descriptor_is_immutable_and_write_disabled(self) -> None:
        descriptor = StateStoreDescriptor(
            target_interface="trading.state.StateStore",
            canonical_state_key="STATE_FILE",
            canonical_default="state.json",
            primary_module="app.py",
            hardening_module="state_io_hardening.py",
        )
        self.assertFalse(descriptor.authoritative)
        self.assertFalse(descriptor.write_enabled)
        with self.assertRaises(FrozenInstanceError):
            descriptor.canonical_default = "other.json"  # type: ignore[misc]

    def test_shadow_validator_has_no_runtime_or_state_authority(self) -> None:
        path = ROOT / "state_store_shadow.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden_imports = {"app", "state_io_hardening", "alpaca_trade_api", "yfinance"}
        forbidden_calls = {
            "submit_order",
            "place_order",
            "execute_order",
            "enter_position",
            "exit_position",
            "save_state",
            "load_state",
            "atomic_json_write",
            "safe_load_json_file",
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

    def test_contract_requires_current_safety_capabilities(self) -> None:
        contract = json.loads(
            (ROOT / "state_store_contract.json").read_text(encoding="utf-8")
        )
        capabilities = contract["required_capabilities"]
        for required in (
            "atomic_write",
            "file_fsync",
            "thread_locking",
            "file_locking_when_supported",
            "retrying_reads",
            "backup_fallback_reads",
            "non_overlapping_cycle_guard",
        ):
            self.assertTrue(capabilities[required], required)


if __name__ == "__main__":
    unittest.main()
