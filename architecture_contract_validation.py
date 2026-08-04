#!/usr/bin/env python3
"""Validate the static refactor audit against declared architecture ownership.

The contract is intentionally one-way during migration:

- legacy owners may disappear as refactoring progresses;
- no undeclared owner may be added;
- no undeclared route overlap or environment-default conflict may appear;
- target future owners are descriptive and receive no runtime authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "architecture-contract-validation-2026-08-03-v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _owners(rows: Any) -> set[str]:
    return {
        str(row.get("path"))
        for row in _list(rows)
        if isinstance(row, dict) and row.get("path")
    }


def _check_group(
    group_name: str,
    registry: dict[str, Any],
    actual: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []

    for target, contract_raw in sorted(registry.items()):
        contract = _dict(contract_raw)
        allowed = {str(value) for value in _list(contract.get("allowed_current_owners"))}
        observed = _owners(actual.get(target))
        unauthorized = sorted(observed - allowed)
        removed = sorted(allowed - observed)
        if unauthorized:
            violations.append(
                {
                    "group": group_name,
                    "target": target,
                    "target_owner": contract.get("target_owner"),
                    "unauthorized_owners": unauthorized,
                    "allowed_current_owners": sorted(allowed),
                    "observed_owners": sorted(observed),
                }
            )
        if removed:
            progress.append(
                {
                    "group": group_name,
                    "target": target,
                    "target_owner": contract.get("target_owner"),
                    "removed_legacy_owners": removed,
                    "remaining_owners": sorted(observed),
                }
            )

    registered = set(registry)
    unregistered = sorted(set(actual) - registered)
    for target in unregistered:
        observed = sorted(_owners(actual.get(target)))
        violations.append(
            {
                "group": group_name,
                "target": target,
                "reason": "unregistered_overlapping_or_conflicting_target",
                "observed_owners": observed,
            }
        )

    return violations, progress


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Architecture Ownership Contract Validation",
        "",
        f"- Status: **{str(report.get('status', 'unknown')).upper()}**",
        f"- Version: `{report.get('version')}`",
        f"- Registry: `{report.get('registry_version')}`",
        f"- Violations: **{len(_list(report.get('violations')))}**",
        f"- Legacy-owner removals detected: **{len(_list(report.get('progress')))}**",
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
                f"- `{row.get('group')}` / `{row.get('target')}`: "
                f"{row.get('reason') or 'unauthorized owner'} — "
                f"`{row.get('unauthorized_owners') or row.get('observed_owners')}`"
            )
        lines.append("")

    lines.extend(["## Refactor Progress", ""])
    progress = _list(report.get("progress"))
    if not progress:
        lines.extend(["No registered legacy owner disappeared in this comparison.", ""])
    else:
        for row in progress:
            lines.append(
                f"- `{row.get('group')}` / `{row.get('target')}` removed "
                f"`{row.get('removed_legacy_owners')}`"
            )
        lines.append("")

    lines.extend(
        [
            "Future target-owner names are descriptive only. This validation does not import the trading application, replace callables, change parameters, mutate state, or place orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default="refactor_audit_report.json")
    parser.add_argument("--registry", default="architecture_ownership_registry.json")
    parser.add_argument("--json", default="architecture_contract_report.json")
    parser.add_argument("--markdown", default="architecture_contract_report.md")
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    current = _dict(audit.get("current"))

    groups = (
        (
            "callable_targets",
            _dict(registry.get("callable_targets")),
            _dict(current.get("mutation_owners")),
        ),
        (
            "route_targets",
            _dict(registry.get("route_targets")),
            _dict(current.get("route_overlaps")),
        ),
        (
            "environment_targets",
            _dict(registry.get("environment_targets")),
            _dict(current.get("environment_conflicts")),
        ),
    )

    violations: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    group_summary: dict[str, Any] = {}
    for name, declared, actual in groups:
        found, reduced = _check_group(name, declared, actual)
        violations.extend(found)
        progress.extend(reduced)
        group_summary[name] = {
            "registered_targets": len(declared),
            "observed_targets": len(actual),
            "violations": len(found),
            "progress_rows": len(reduced),
        }

    status = "fail" if violations else "pass"
    report = {
        "status": status,
        "type": "architecture_ownership_contract_validation",
        "version": VERSION,
        "registry_version": registry.get("version"),
        "audit_version": audit.get("version"),
        "policy": {
            "legacy_owner_removal_allowed": True,
            "new_owner_allowed": False,
            "changes_runtime_authority": False,
            "imports_trading_runtime": False,
            "places_orders": False,
        },
        "groups": group_summary,
        "violations": violations,
        "progress": progress,
    }

    Path(args.json).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.markdown).write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
