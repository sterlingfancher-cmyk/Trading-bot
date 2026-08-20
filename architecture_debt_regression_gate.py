#!/usr/bin/env python3
"""Fail CI when a change increases known structural debt.

Existing debt remains an explicit migration backlog. This gate only prevents the
repository from accumulating more warning/informational architecture debt while
the canonical runtime is being built.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "architecture-debt-regression-gate-2026-08-20-v1"

# These are debt measures, not ordinary growth measures. New files, source lines,
# functions, imports, and routes are allowed when they do not increase ambiguity.
BLOCK_POSITIVE_DELTAS = (
    "broad_exception_passes",
    "busy_watchdog_loops",
    "critical_findings",
    "duplicate_function_groups",
    "dynamic_mutation_targets",
    "environment_default_conflicts",
    "import_cycles",
    "import_time_threads",
    "info_findings",
    "mutation_overlaps",
    "network_calls_inside_loops",
    "parallel_version_families",
    "parameter_owner_conflicts",
    "route_overlaps",
    "warning_findings",
    "watchdog_loops",
)


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    comparison = report.get("comparison") if isinstance(report, dict) else None
    comparison = comparison if isinstance(comparison, dict) else {}
    base_available = bool(comparison.get("base_available"))
    deltas = comparison.get("summary_delta")
    deltas = deltas if isinstance(deltas, dict) else {}

    if not base_available:
        return {
            "status": "pass",
            "version": VERSION,
            "enforced": False,
            "reason": "no_base_comparison",
            "violations": [],
        }

    violations: list[dict[str, Any]] = []
    for key in BLOCK_POSITIVE_DELTAS:
        try:
            delta = int(deltas.get(key, 0) or 0)
        except Exception:
            delta = 0
        if delta > 0:
            violations.append({"metric": key, "delta": delta})

    # Keep category evidence compact so a failed PR immediately tells the author
    # what kind of debt was introduced without changing audit severity.
    new_warnings = comparison.get("new_warnings")
    new_warnings = new_warnings if isinstance(new_warnings, list) else []
    warning_categories = sorted(
        {
            str(row.get("category") or "unknown")
            for row in new_warnings
            if isinstance(row, dict)
        }
    )

    return {
        "status": "fail" if violations else "pass",
        "version": VERSION,
        "enforced": True,
        "violations": violations,
        "new_warning_categories": warning_categories,
        "policy": {
            "existing_debt_is_not_failed": True,
            "positive_debt_delta_is_failed": True,
            "changes_runtime_authority": False,
            "changes_trading_behavior": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default="refactor_audit_report.json")
    parser.add_argument("--json", default="architecture_debt_regression_report.json")
    args = parser.parse_args()

    report = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    result = evaluate(report)
    Path(args.json).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
