#!/usr/bin/env python3
"""Validate a read-only typed configuration baseline against source audit data.

The validator consumes the static refactor audit and selected source files. It
never imports the trading application, reads process environment values, mutates
runtime configuration, or places orders.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path
from typing import Any

from typed_configuration_models import (
    ConfigUnit,
    ObservedConfigValue,
    SourceKind,
    SourceSelector,
    TypedConfigContract,
    normalize_value,
)

VERSION = "typed-configuration-validation-2026-08-03-v1-shadow"
ROOT = Path(__file__).resolve().parent


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


def _source_tree(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)


def _source_constant(path: str, name: str) -> tuple[Any, int | None]:
    tree = _source_tree(path)
    if name == "WATCHDOG_SLEEP_SECONDS" and path == "performance_audit_composition_guard.py":
        values: list[tuple[float, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "sleep" or not node.args:
                continue
            value = _literal(node.args[0])
            if isinstance(value, (int, float)):
                values.append((float(value), int(node.lineno)))
        if values:
            return min(values, key=lambda row: row[0])
        return "<missing>", None

    for node in tree.body:
        targets: list[ast.AST] = []
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return _literal(value_node), int(getattr(node, "lineno", 0) or 0)
    return "<missing>", None


def _source_env_setdefault(path: str, name: str) -> tuple[Any, int | None]:
    tree = _source_tree(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "setdefault" or len(node.args) < 2:
            continue
        owner = node.func.value
        is_environ = (
            isinstance(owner, ast.Attribute)
            and owner.attr == "environ"
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "os"
        )
        if is_environ and _literal(node.args[0]) == name:
            return _literal(node.args[1]), int(getattr(node, "lineno", 0) or 0)
    return "<missing>", None


def _audit_value(
    audit: dict[str, Any],
    *,
    group: str,
    path: str,
    name: str,
) -> tuple[Any, int | None]:
    rows = _list(_dict(_dict(audit.get("current")).get(group)).get(name))
    matches = [row for row in rows if isinstance(row, dict) and row.get("path") == path]
    if not matches:
        return "<missing>", None
    row = matches[0]
    key = "default" if group == "environment_owners" else "value"
    return row.get(key), row.get("line")


def _parse_contract(row: dict[str, Any]) -> TypedConfigContract:
    source = _dict(row.get("source"))
    return TypedConfigContract(
        config_id=str(row.get("config_id")),
        selector=SourceSelector(
            kind=SourceKind(str(source.get("kind"))),
            path=str(source.get("path")),
            name=str(source.get("name")),
        ),
        unit=ConfigUnit(str(row.get("unit"))),
        expected_raw=row.get("expected_raw"),
        expected_normalized=row.get("expected_normalized"),
        scope=str(row.get("scope") or ""),
        authoritative=bool(row.get("authoritative", False)),
        note=str(row.get("note") or ""),
    )


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
    return left == right


def _observe(contract: TypedConfigContract, audit: dict[str, Any]) -> ObservedConfigValue:
    selector = contract.selector
    if selector.kind is SourceKind.AUDIT_ENVIRONMENT:
        raw, line = _audit_value(
            audit,
            group="environment_owners",
            path=selector.path,
            name=selector.name,
        )
    elif selector.kind is SourceKind.AUDIT_PARAMETER:
        raw, line = _audit_value(
            audit,
            group="parameter_owners",
            path=selector.path,
            name=selector.name,
        )
    elif selector.kind is SourceKind.SOURCE_ENV_SETDEFAULT:
        raw, line = _source_env_setdefault(selector.path, selector.name)
    elif selector.kind is SourceKind.SOURCE_CONSTANT:
        raw, line = _source_constant(selector.path, selector.name)
    else:  # pragma: no cover
        raw, line = "<unsupported>", None

    try:
        normalized = normalize_value(raw, contract.unit)
        parity = _same(raw, contract.expected_raw) and _same(
            normalized, contract.expected_normalized
        )
        detail = "parity" if parity else (
            f"expected raw={contract.expected_raw!r}, normalized={contract.expected_normalized!r}; "
            f"observed raw={raw!r}, normalized={normalized!r}"
        )
    except Exception as exc:
        normalized = None
        parity = False
        detail = f"normalization_failed: {type(exc).__name__}: {exc}"

    return ObservedConfigValue(
        config_id=contract.config_id,
        selector=selector,
        unit=contract.unit,
        raw=raw,
        normalized=normalized,
        source_line=line,
        parity=parity,
        detail=detail,
    )


def _known_conflict_rows(
    baseline: dict[str, Any], audit: dict[str, Any]
) -> list[dict[str, Any]]:
    owners = _dict(_dict(audit.get("current")).get("environment_owners"))
    results: list[dict[str, Any]] = []
    for name, spec_raw in sorted(_dict(baseline.get("known_conflicts")).items()):
        spec = _dict(spec_raw)
        expected = _dict(spec.get("expected_owner_defaults"))
        observed_rows = _list(owners.get(name))
        observed: dict[str, Any] = {}
        for row in observed_rows:
            if not isinstance(row, dict) or not row.get("path"):
                continue
            observed.setdefault(str(row.get("path")), row.get("default"))
        selected = {path: observed.get(path, "<missing>") for path in expected}
        parity = selected == expected
        results.append(
            {
                "name": name,
                "status": spec.get("status"),
                "expected_owner_defaults": expected,
                "observed_owner_defaults": selected,
                "parity": parity,
            }
        )
    return results


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Typed Configuration Shadow Parity",
        "",
        f"- Status: **{str(report.get('status')).upper()}**",
        f"- Version: `{report.get('version')}`",
        f"- Baseline: `{report.get('baseline_version')}`",
        f"- Contracts checked: **{report.get('summary', {}).get('contracts_checked')}**",
        f"- Parity mismatches: **{report.get('summary', {}).get('parity_mismatches')}**",
        f"- Known-conflict drift: **{report.get('summary', {}).get('known_conflict_drift')}**",
        "",
        "## Mismatches",
        "",
    ]
    mismatches = _list(report.get("mismatches"))
    if not mismatches:
        lines.extend(["None.", ""])
    else:
        for row in mismatches:
            lines.append(
                f"- `{row.get('config_id')}` — `{row.get('path')}:{row.get('line')}` — {row.get('detail')}"
            )
        lines.append("")
    lines.extend(
        [
            "This snapshot is read-only and non-authoritative. A mismatch blocks the architecture gate so an effective configuration change cannot occur silently. Any intentional behavior change still requires backtest, walk-forward, and forward paper evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default="refactor_audit_report.json")
    parser.add_argument("--baseline", default="typed_configuration_baseline.json")
    parser.add_argument("--json", default="typed_configuration_report.json")
    parser.add_argument("--markdown", default="typed_configuration_report.md")
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    contracts = [_parse_contract(row) for row in _list(baseline.get("contracts"))]
    observed = [_observe(contract, audit) for contract in contracts]
    mismatches = [
        {
            "config_id": row.config_id,
            "path": row.selector.path,
            "name": row.selector.name,
            "line": row.source_line,
            "unit": row.unit.value,
            "raw": row.raw,
            "normalized": row.normalized,
            "detail": row.detail,
        }
        for row in observed
        if not row.parity
    ]
    conflicts = _known_conflict_rows(baseline, audit)
    conflict_drift = [row for row in conflicts if not row.get("parity")]
    status = "fail" if mismatches or conflict_drift else "pass"
    report = {
        "status": status,
        "type": "typed_configuration_shadow_parity",
        "version": VERSION,
        "baseline_version": baseline.get("version"),
        "summary": {
            "contracts_checked": len(contracts),
            "parity_matches": len(contracts) - len(mismatches),
            "parity_mismatches": len(mismatches),
            "known_conflicts_checked": len(conflicts),
            "known_conflict_drift": len(conflict_drift),
        },
        "policy": {
            "read_only": True,
            "authoritative": False,
            "imports_trading_runtime": False,
            "reads_process_environment": False,
            "changes_runtime_values": False,
            "places_orders": False,
        },
        "observed": [
            {
                "config_id": row.config_id,
                "source_kind": row.selector.kind.value,
                "path": row.selector.path,
                "name": row.selector.name,
                "line": row.source_line,
                "unit": row.unit.value,
                "raw": row.raw,
                "normalized": row.normalized,
                "parity": row.parity,
                "detail": row.detail,
            }
            for row in observed
        ],
        "known_conflicts": conflicts,
        "mismatches": mismatches,
        "known_conflict_drift": conflict_drift,
    }
    Path(args.json).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.markdown).write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
