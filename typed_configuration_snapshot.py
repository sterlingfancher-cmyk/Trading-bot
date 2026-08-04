#!/usr/bin/env python3
"""Validate typed configuration observations without changing runtime policy.

The validator consumes the static refactor-audit artifact. It never imports the
trading application, reads secrets, resolves live environment variables, mutates
paper state, or places orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "typed-configuration-snapshot-2026-08-03-v1"
ALLOWED_UNITS = {
    "fraction",
    "percentage_points",
    "raw_score",
    "path",
    "minutes",
    "seconds",
    "count",
    "unknown_requires_namespacing",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _observations(rows: Any, key: str = "default") -> set[tuple[str, str]]:
    return {
        (str(row.get("path")), _normalize(row.get(key)))
        for row in _list(rows)
        if isinstance(row, dict) and row.get("path")
    }


def _environment_validation(
    contract: dict[str, Any],
    environment_owners: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    results: dict[str, Any] = {}

    for key, raw in sorted(contract.items()):
        row = _dict(raw)
        unit = str(row.get("unit") or "")
        if unit not in ALLOWED_UNITS:
            violations.append(
                {"target": key, "reason": "unknown_unit", "unit": unit}
            )

        allowed = _observations(row.get("allowed_observations"))
        actual = _observations(environment_owners.get(key))
        unauthorized = sorted(actual - allowed)
        removed = sorted(allowed - actual)

        canonical = (
            str(row.get("canonical_owner")),
            _normalize(row.get("canonical_default")),
        )
        canonical_present = canonical in actual
        if not canonical_present:
            violations.append(
                {
                    "target": key,
                    "reason": "canonical_default_missing_or_changed",
                    "expected": canonical,
                    "actual": sorted(actual),
                    "behavior_sensitive": bool(row.get("behavior_sensitive")),
                }
            )
        if unauthorized:
            violations.append(
                {
                    "target": key,
                    "reason": "unauthorized_configuration_observation",
                    "unauthorized": unauthorized,
                    "allowed": sorted(allowed),
                }
            )
        if removed:
            progress.append(
                {
                    "target": key,
                    "removed_legacy_observations": removed,
                    "canonical_present": canonical_present,
                }
            )

        results[key] = {
            "unit": unit,
            "meaning": row.get("meaning"),
            "behavior_sensitive": bool(row.get("behavior_sensitive")),
            "known_conflict": bool(row.get("known_conflict")),
            "canonical_owner": row.get("canonical_owner"),
            "canonical_default": row.get("canonical_default"),
            "canonical_present": canonical_present,
            "observed": sorted(actual),
            "unauthorized": unauthorized,
            "removed": removed,
        }

    return violations, progress, results


def _parameter_validation(
    contract: dict[str, Any],
    parameter_owners: dict[str, Any],
    existing_paths: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    results: dict[str, Any] = {}

    for key, raw in sorted(contract.items()):
        row = _dict(raw)
        default_unit = row.get("unit")
        if default_unit and str(default_unit) not in ALLOWED_UNITS:
            violations.append(
                {"target": key, "reason": "unknown_unit", "unit": default_unit}
            )

        actual = _observations(parameter_owners.get(key), key="value")
        declared_rows = _list(row.get("observations"))
        declared: set[tuple[str, str]] = set()
        units_by_path: dict[str, str] = {}
        for observation in declared_rows:
            if not isinstance(observation, dict) or not observation.get("path"):
                continue
            path = str(observation.get("path"))
            value = _normalize(observation.get("value"))
            declared.add((path, value))
            unit = str(observation.get("unit") or default_unit or "")
            units_by_path[path] = unit
            if unit not in ALLOWED_UNITS:
                violations.append(
                    {
                        "target": key,
                        "path": path,
                        "reason": "unknown_unit",
                        "unit": unit,
                    }
                )

        missing = sorted(declared - actual)
        for path, value in missing:
            if path in existing_paths:
                violations.append(
                    {
                        "target": key,
                        "path": path,
                        "reason": "declared_parameter_value_missing_or_changed",
                        "expected_value": value,
                        "actual": sorted(item for item in actual if item[0] == path),
                    }
                )
            else:
                progress.append(
                    {
                        "target": key,
                        "path": path,
                        "reason": "legacy_parameter_owner_removed",
                    }
                )

        results[key] = {
            "known_unit_ambiguity": bool(row.get("known_unit_ambiguity")),
            "default_unit": default_unit,
            "declared": sorted(declared),
            "observed": sorted(actual),
            "undeclared_observations": sorted(actual - declared),
            "units_by_path": units_by_path,
        }

    return violations, progress, results


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Typed Configuration Snapshot",
        "",
        f"- Status: **{str(report.get('status', 'unknown')).upper()}**",
        f"- Contract: `{report.get('contract_version')}`",
        f"- Violations: **{len(_list(report.get('violations')))}**",
        f"- Progress rows: **{len(_list(report.get('progress')))}**",
        f"- Known conflicts preserved: **{report.get('known_conflict_count')}**",
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
                f"- `{row.get('target')}`: `{row.get('reason')}` — `{row}`"
            )
        lines.append("")

    lines.extend(["## Environment Configuration", ""])
    for key, row in _dict(report.get("environment")).items():
        lines.append(
            f"- `{key}` — unit `{row.get('unit')}`, canonical "
            f"`{row.get('canonical_owner')}={row.get('canonical_default')}`, "
            f"present `{row.get('canonical_present')}`, known conflict `{row.get('known_conflict')}`"
        )
    lines.append("")

    lines.extend(
        [
            "The snapshot is intentionally non-authoritative. Known conflicts remain frozen for controlled migration and may not be resolved without the validation required for their behavior sensitivity.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default="refactor_audit_report.json")
    parser.add_argument("--contract", default="typed_configuration_contract.json")
    parser.add_argument("--json", default="typed_configuration_report.json")
    parser.add_argument("--markdown", default="typed_configuration_report.md")
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    current = _dict(audit.get("current"))
    existing_paths = {
        str(row.get("path"))
        for row in _list(current.get("file_metrics"))
        if isinstance(row, dict) and row.get("path")
    }

    env_violations, env_progress, environment = _environment_validation(
        _dict(contract.get("environment_contracts")),
        _dict(current.get("environment_owners")),
    )
    param_violations, param_progress, parameters = _parameter_validation(
        _dict(contract.get("parameter_unit_contracts")),
        _dict(current.get("parameter_owners")),
        existing_paths,
    )

    violations = env_violations + param_violations
    progress = env_progress + param_progress
    known_conflict_count = sum(
        1 for row in environment.values() if row.get("known_conflict")
    ) + sum(
        1 for row in parameters.values() if row.get("known_unit_ambiguity")
    )
    status = "fail" if violations else "pass"
    report = {
        "status": status,
        "type": "typed_configuration_snapshot",
        "version": VERSION,
        "contract_version": contract.get("version"),
        "audit_version": audit.get("version"),
        "policy": {
            "read_only": True,
            "authoritative_runtime_source": False,
            "changes_effective_values": False,
            "imports_trading_runtime": False,
            "reads_secrets": False,
            "places_orders": False,
        },
        "known_conflict_count": known_conflict_count,
        "environment": environment,
        "parameters": parameters,
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
