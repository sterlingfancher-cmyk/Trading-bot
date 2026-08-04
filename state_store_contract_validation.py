#!/usr/bin/env python3
"""Validate the read-only StateStore migration contract.

This tool performs static source inspection only. It does not import the trading
runtime, open the paper state file, acquire runtime locks, write backups, alter
path resolution, or replace ``save_state``.
"""
from __future__ import annotations

import argparse
import ast
import json
import tokenize
from pathlib import Path
from typing import Any

VERSION = "state-store-contract-validation-2026-08-03-v1"
ROOT = Path(__file__).resolve().parent


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _source(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def _call_name(node: ast.Call) -> str:
    current = node.func
    parts: list[str] = []
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts)) if parts else "<dynamic>"


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return "<dynamic>"


def _defined_symbols(tree: ast.Module) -> set[str]:
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def _environment_defaults(tree: ast.Module) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "os.environ.get" and node.args:
            key = _literal(node.args[0])
            default = _literal(node.args[1]) if len(node.args) > 1 else None
        elif name == "os.getenv" and node.args:
            key = _literal(node.args[0])
            default = _literal(node.args[1]) if len(node.args) > 1 else None
        else:
            continue
        if isinstance(key, str):
            defaults[key] = default
    return defaults


def _string_literals(tree: ast.Module) -> set[str]:
    return {
        str(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _validate_module(
    path_text: str,
    required_symbols: list[str],
    required_calls: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = ROOT / path_text
    if not path.is_file():
        return (
            [{"path": path_text, "reason": "required_module_missing"}],
            {"path": path_text, "present": False},
        )

    text = _source(path)
    try:
        tree = ast.parse(text, filename=path_text)
    except Exception as exc:
        return (
            [
                {
                    "path": path_text,
                    "reason": "parse_failure",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ],
            {"path": path_text, "present": True, "parsed": False},
        )

    symbols = _defined_symbols(tree)
    calls = {_call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    missing_symbols = sorted(set(required_symbols) - symbols)
    missing_calls = sorted(set(required_calls) - calls)
    violations: list[dict[str, Any]] = []
    if missing_symbols:
        violations.append(
            {
                "path": path_text,
                "reason": "required_symbols_missing",
                "missing": missing_symbols,
            }
        )
    if missing_calls:
        violations.append(
            {
                "path": path_text,
                "reason": "required_calls_missing",
                "missing": missing_calls,
            }
        )
    return (
        violations,
        {
            "path": path_text,
            "present": True,
            "parsed": True,
            "required_symbols": required_symbols,
            "missing_symbols": missing_symbols,
            "required_calls": required_calls,
            "missing_calls": missing_calls,
            "environment_defaults": _environment_defaults(tree),
            "string_literals": sorted(_string_literals(tree)),
        },
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# StateStore Parity Contract Validation",
        "",
        f"- Status: **{str(report.get('status', 'unknown')).upper()}**",
        f"- Contract: `{report.get('contract_version')}`",
        f"- Validator: `{report.get('version')}`",
        f"- Violations: **{len(_list(report.get('violations')))}**",
        "",
        "## Contract Boundary",
        "",
        "- Read-only: `true`",
        "- Replaces `save_state`: `false`",
        "- Changes state path: `false`",
        "- Changes locking or backup policy: `false`",
        "- Runtime imports: `false`",
        "- State-file reads/writes: `false`",
        "",
        "## Violations",
        "",
    ]
    violations = _list(report.get("violations"))
    if not violations:
        lines.extend(["None.", ""])
    else:
        for row in violations:
            lines.append(
                f"- `{row.get('path') or row.get('target')}`: "
                f"`{row.get('reason')}` — `{row}`"
            )
        lines.append("")
    lines.extend(
        [
            "The contract freezes existing state behavior for staged migration. It does not make the future `StateStore` authoritative.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="state_store_contract.json")
    parser.add_argument("--json", default="state_store_contract_report.json")
    parser.add_argument("--markdown", default="state_store_contract_report.md")
    args = parser.parse_args()

    contract_path = ROOT / args.contract
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    violations: list[dict[str, Any]] = []
    modules: dict[str, Any] = {}

    required_symbols = _dict(contract.get("required_symbols"))
    required_calls = _dict(contract.get("required_calls"))
    module_paths = sorted(set(required_symbols) | set(required_calls))
    for path_text in module_paths:
        found, detail = _validate_module(
            path_text,
            [str(value) for value in _list(required_symbols.get(path_text))],
            [str(value) for value in _list(required_calls.get(path_text))],
        )
        violations.extend(found)
        modules[path_text] = detail

    defaults = _dict(contract.get("required_defaults"))
    observed_defaults: dict[str, Any] = {}
    for detail in modules.values():
        observed_defaults.update(_dict(detail.get("environment_defaults")))
    for key, expected in sorted(defaults.items()):
        actual = observed_defaults.get(key, "<missing>")
        if str(actual) != str(expected):
            violations.append(
                {
                    "target": key,
                    "reason": "required_default_missing_or_changed",
                    "expected": expected,
                    "actual": actual,
                }
            )

    path_contract = _dict(contract.get("path_contract"))
    app_path = ROOT / "app.py"
    if not app_path.is_file():
        violations.append({"path": "app.py", "reason": "canonical_path_owner_missing"})
        app_literals: set[str] = set()
        app_defaults: dict[str, Any] = {}
    else:
        app_tree = ast.parse(_source(app_path), filename="app.py")
        app_literals = _string_literals(app_tree)
        app_defaults = _environment_defaults(app_tree)

    canonical_key = str(path_contract.get("canonical_environment_key") or "")
    canonical_default = path_contract.get("canonical_default")
    if canonical_key not in app_literals:
        violations.append(
            {
                "path": "app.py",
                "target": canonical_key,
                "reason": "canonical_environment_key_not_referenced",
            }
        )
    if str(canonical_default) not in app_literals:
        violations.append(
            {
                "path": "app.py",
                "target": canonical_key,
                "reason": "canonical_default_not_referenced",
                "expected": canonical_default,
            }
        )
    for key in _list(path_contract.get("directory_precedence"))[:-1]:
        if str(key) not in app_literals:
            violations.append(
                {
                    "path": "app.py",
                    "target": key,
                    "reason": "directory_precedence_key_not_referenced",
                }
            )
    for key in _list(path_contract.get("filename_precedence"))[:-1]:
        if str(key) not in app_literals:
            violations.append(
                {
                    "path": "app.py",
                    "target": key,
                    "reason": "filename_precedence_key_not_referenced",
                }
            )

    policy = _dict(contract.get("policy"))
    forbidden_true = {
        "authoritative_runtime_source",
        "replaces_save_state",
        "changes_state_path",
        "changes_locking",
        "changes_backup_policy",
        "changes_runtime_authority",
    }
    for key in sorted(forbidden_true):
        if bool(policy.get(key)):
            violations.append(
                {"target": key, "reason": "shadow_contract_claims_runtime_authority"}
            )
    if not bool(policy.get("read_only")):
        violations.append({"target": "read_only", "reason": "contract_must_be_read_only"})

    status = "fail" if violations else "pass"
    report = {
        "status": status,
        "type": "state_store_parity_contract_validation",
        "version": VERSION,
        "contract_version": contract.get("version"),
        "target_interface": contract.get("target_interface"),
        "policy": {
            "static_source_only": True,
            "imports_trading_runtime": False,
            "reads_state_file": False,
            "writes_state_file": False,
            "replaces_save_state": False,
            "changes_runtime_authority": False,
        },
        "path_contract": path_contract,
        "canonical_app_environment_defaults": app_defaults,
        "required_capabilities": _dict(contract.get("required_capabilities")),
        "known_migration_debt": _dict(contract.get("known_migration_debt")),
        "modules": modules,
        "violations": violations,
    }

    (ROOT / args.json).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / args.markdown).write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
