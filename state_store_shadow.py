#!/usr/bin/env python3
"""Read-only StateStore shadow descriptor and parity validator.

This module parses source and audit artifacts only. It does not import the
trading application, open the state file, acquire production locks, mutate
portfolio state, or replace load/save callables.
"""
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

VERSION = "state-store-shadow-2026-08-03-v1"
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class StateStoreDescriptor:
    target_interface: str
    canonical_state_key: str
    canonical_default: str
    primary_module: str
    hardening_module: str
    authoritative: bool = False
    write_enabled: bool = False


@dataclass(frozen=True, slots=True)
class StateStoreParityResult:
    status: str
    required_symbol_violations: tuple[str, ...]
    required_call_violations: tuple[str, ...]
    default_violations: tuple[str, ...]
    capability_violations: tuple[str, ...]
    typed_configuration_violations: tuple[str, ...]
    observed_save_state_owners: tuple[str, ...]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return "<dynamic>"


def _call_name(node: ast.Call) -> str:
    value = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts)) if parts else "<dynamic>"


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        value = node.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return None


def _source(path: str) -> tuple[str, ast.Module]:
    text = (ROOT / path).read_text(encoding="utf-8")
    return text, ast.parse(text, filename=path)


def _symbols(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                name = _target_name(target)
                if name:
                    found.add(name)
        elif isinstance(node, ast.AnnAssign):
            name = _target_name(node.target)
            if name:
                found.add(name)
    return found


def _calls(tree: ast.Module) -> set[str]:
    return {
        _call_name(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


def _environment_defaults(tree: ast.Module) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get" or len(node.args) < 2:
            continue
        owner = node.func.value
        is_environ = (
            isinstance(owner, ast.Attribute)
            and owner.attr == "environ"
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "os"
        )
        if not is_environ:
            continue
        key = _literal(node.args[0])
        if isinstance(key, str):
            output[key] = _literal(node.args[1])
    return output


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _node_text(text: str, node: ast.AST | None) -> str:
    if node is None:
        return ""
    segment = ast.get_source_segment(text, node)
    return segment or ""


def _capabilities(text: str, tree: ast.Module) -> dict[str, bool]:
    atomic = _node_text(text, _function(tree, "atomic_json_write"))
    safe_load = _node_text(text, _function(tree, "safe_load_json_file"))
    backup = _node_text(text, _function(tree, "backup_current_state"))
    install = _node_text(text, _function(tree, "install"))
    lock_class = ""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "_FileLock":
            lock_class = _node_text(text, node)
            break

    return {
        "atomic_write": "os.replace" in atomic,
        "file_fsync": "os.fsync" in atomic,
        "directory_fsync_attempt": "os.O_DIRECTORY" in atomic,
        "thread_locking": "threading.RLock" in text and "threading.Lock" in text,
        "file_locking_when_supported": "fcntl.flock" in lock_class,
        "shared_read_lock": "LOCK_SH" in lock_class and "exclusive=False" in safe_load,
        "exclusive_write_lock": "LOCK_EX" in lock_class and "exclusive=True" in text,
        "retrying_reads": "READ_RETRIES" in safe_load and "READ_RETRY_SLEEP" in safe_load,
        "backup_fallback_reads": all(
            name in safe_load
            for name in ("STATE_BACKUP_LATEST", "STATE_BACKUP_LARGEST", "STATE_BACKUP_PREWRITE")
        ),
        "latest_backup": "STATE_BACKUP_LATEST" in backup,
        "largest_backup": "STATE_BACKUP_LARGEST" in backup,
        "prewrite_backup": "STATE_BACKUP_PREWRITE" in backup,
        "non_overlapping_cycle_guard": "original_run_cycle" in install and "_RUN_LOCK" in text,
    }


def _typed_state_contract(report: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    environment = _dict(report.get("environment"))
    state = _dict(environment.get("STATE_FILE"))
    if not state:
        errors.append("STATE_FILE missing from typed configuration report")
        return False, errors
    if not state.get("canonical_present"):
        errors.append("STATE_FILE canonical observation is not present")
    if state.get("canonical_owner") != "app.py":
        errors.append(f"STATE_FILE canonical owner changed: {state.get('canonical_owner')!r}")
    if state.get("canonical_default") != "state.json":
        errors.append(f"STATE_FILE canonical default changed: {state.get('canonical_default')!r}")
    return not errors, errors


def validate(
    contract: dict[str, Any],
    audit: dict[str, Any],
    typed_config: dict[str, Any],
) -> tuple[dict[str, Any], StateStoreParityResult]:
    primary = "app.py"
    hardening = "state_io_hardening.py"
    text, tree = _source(hardening)
    symbols = _symbols(tree)
    calls = _calls(tree)
    defaults = _environment_defaults(tree)

    required_symbols = _list(_dict(contract.get("required_symbols")).get(hardening))
    symbol_violations = tuple(sorted(set(map(str, required_symbols)) - symbols))

    required_calls = _list(_dict(contract.get("required_calls")).get(hardening))
    call_violations = tuple(
        sorted(name for name in map(str, required_calls) if name not in calls)
    )

    default_violations: list[str] = []
    for key, expected in _dict(contract.get("required_defaults")).items():
        observed = defaults.get(key, "<missing>")
        if observed != expected:
            default_violations.append(
                f"{key}: expected {expected!r}, observed {observed!r}"
            )

    observed_capabilities = _capabilities(text, tree)
    required_capabilities = _dict(contract.get("required_capabilities"))
    capability_violations = tuple(
        sorted(
            name
            for name, required in required_capabilities.items()
            if bool(required) and not observed_capabilities.get(name, False)
        )
    )

    _, typed_errors = _typed_state_contract(typed_config)
    mutation_owners = _dict(_dict(audit.get("current")).get("mutation_owners"))
    save_state_owners = tuple(
        sorted(
            {
                str(row.get("path"))
                for row in _list(mutation_owners.get("save_state"))
                if isinstance(row, dict) and row.get("path")
            }
        )
    )

    result = StateStoreParityResult(
        status=(
            "pass"
            if not symbol_violations
            and not call_violations
            and not default_violations
            and not capability_violations
            and not typed_errors
            else "fail"
        ),
        required_symbol_violations=symbol_violations,
        required_call_violations=call_violations,
        default_violations=tuple(default_violations),
        capability_violations=capability_violations,
        typed_configuration_violations=tuple(typed_errors),
        observed_save_state_owners=save_state_owners,
    )
    descriptor = StateStoreDescriptor(
        target_interface=str(contract.get("target_interface")),
        canonical_state_key=str(_dict(contract.get("path_contract")).get("canonical_environment_key")),
        canonical_default=str(_dict(contract.get("path_contract")).get("canonical_default")),
        primary_module=primary,
        hardening_module=hardening,
    )
    report = {
        "status": result.status,
        "type": "state_store_shadow_parity",
        "version": VERSION,
        "contract_version": contract.get("version"),
        "descriptor": asdict(descriptor),
        "result": asdict(result),
        "observed": {
            "required_symbols_present": sorted(set(map(str, required_symbols)) & symbols),
            "required_calls_present": sorted(set(map(str, required_calls)) & calls),
            "environment_defaults": defaults,
            "capabilities": observed_capabilities,
            "save_state_owner_count": len(save_state_owners),
        },
        "policy": {
            "read_only": True,
            "authoritative": False,
            "imports_trading_runtime": False,
            "reads_or_writes_state_file": False,
            "replaces_save_state": False,
            "changes_state_path": False,
            "places_orders": False,
        },
    }
    return report, result


def _markdown(report: dict[str, Any]) -> str:
    result = _dict(report.get("result"))
    observed = _dict(report.get("observed"))
    lines = [
        "# StateStore Shadow Parity",
        "",
        f"- Status: **{str(report.get('status')).upper()}**",
        f"- Contract: `{report.get('contract_version')}`",
        f"- Save-state owners observed: **{observed.get('save_state_owner_count')}**",
        f"- Missing symbols: `{result.get('required_symbol_violations')}`",
        f"- Missing calls: `{result.get('required_call_violations')}`",
        f"- Default drift: `{result.get('default_violations')}`",
        f"- Capability drift: `{result.get('capability_violations')}`",
        f"- Typed configuration drift: `{result.get('typed_configuration_violations')}`",
        "",
        "This report is read-only. It does not open the production state file or replace runtime state functions.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="state_store_contract.json")
    parser.add_argument("--audit", default="refactor_audit_report.json")
    parser.add_argument("--typed-config", default="typed_configuration_report.json")
    parser.add_argument("--json", default="state_store_report.json")
    parser.add_argument("--markdown", default="state_store_report.md")
    args = parser.parse_args()

    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    typed_config = json.loads(Path(args.typed_config).read_text(encoding="utf-8"))
    report, result = validate(contract, audit, typed_config)
    Path(args.json).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.markdown).write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if result.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
