#!/usr/bin/env python3
"""Calibrated, JSON-safe command-line interface for refactor_audit.

The core analyzer gathers a broad source inventory. This adapter removes known
static-analysis noise before comparing commits:

- local object attribute assignments are not treated as runtime monkey patches;
- ordinary dictionary ``get`` calls are not treated as network calls;
- watchdog loops using named sleep constants are not treated as no-sleep loops;
- ``while True`` loops with a reachable ``break`` are treated as bounded loops;
- dynamic route and environment expressions are excluded from literal conflicts.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import refactor_audit as core

VERSION = "refactor-audit-cli-2026-08-03-v3-bounded-loop-calibration"
RUNTIME_ASSIGNMENT_ROOTS = {"app", "core", "flask_app", "m", "mod", "module"}
NETWORK_ROOTS = {"httpx", "requests", "urllib", "urllib3", "yf", "yfinance"}
TOOLING_NETWORK_PATHS = {"runtime_research_snapshot.py"}
REBUILT_CATEGORIES = {
    "busy_infinite_loop",
    "conflicting_environment_defaults",
    "overlapping_mutation_owners",
    "route_overlap",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    if isinstance(value, tuple):
        return list(value)
    return repr(value)


def _dumps(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("default", _json_default)
    return json.dumps(value, **kwargs)


def _finding(
    severity: str,
    category: str,
    path: str,
    line: int | None,
    target: str,
    detail: str,
) -> dict[str, Any]:
    return core.Finding(severity, category, path, line, target, detail).as_dict()


def _assignment_is_runtime(target_key: str, row: dict[str, Any]) -> bool:
    if row.get("kind") != "assignment":
        return True
    target = str(row.get("target") or "")
    root = re.split(r"[.[]", target, maxsplit=1)[0]
    return bool(
        target_key in core.CRITICAL_CALLABLES
        or target_key in core.PROTECTED_PARAMETERS
        or root in RUNTIME_ASSIGNMENT_ROOTS
        or "view_functions" in target
    )


def _network_call_is_relevant(call: str) -> bool:
    name = str(call or "")
    parts = name.split(".")
    root = parts[0].lower() if parts else ""
    tail = parts[-1].lower() if parts else ""
    if tail in {"download", "download_prices", "fetch", "urlopen"}:
        return True
    if tail.endswith("download") or tail.endswith("download_prices"):
        return True
    return root in NETWORK_ROOTS and tail in {"get", "post", "request", "urlopen"}


def _loop_properties(
    units: dict[str, core.SourceUnit],
) -> dict[tuple[str, int], dict[str, bool]]:
    rows: dict[tuple[str, int], dict[str, bool]] = {}
    for path, unit in units.items():
        for node in ast.walk(unit.tree):
            if not isinstance(node, ast.While) or not core._is_true_loop(node):
                continue
            children = list(ast.walk(node))
            has_sleep = any(
                isinstance(child, ast.Call)
                and core._call_name(child).rsplit(".", 1)[-1] == "sleep"
                for child in children
            )
            has_break = any(isinstance(child, ast.Break) for child in children)
            rows[(path, int(node.lineno))] = {
                "has_sleep": has_sleep,
                "has_break": has_break,
            }
    return rows


def _calibrate(analysis: dict[str, Any], units: dict[str, core.SourceUnit]) -> dict[str, Any]:
    findings = [
        row
        for row in analysis.get("findings", [])
        if row.get("category") not in REBUILT_CATEGORIES
    ]

    environment_owners = {
        key: owners
        for key, owners in analysis.get("environment_owners", {}).items()
        if key != "<dynamic>"
    }
    environment_conflicts: dict[str, list[dict[str, Any]]] = {}
    for key, owners in sorted(environment_owners.items()):
        defaults = {_dumps(row.get("default"), sort_keys=True) for row in owners}
        if len(defaults) <= 1:
            continue
        environment_conflicts[key] = owners
        severity = "critical" if key in core.PROTECTED_PARAMETERS else "warning"
        findings.append(
            _finding(
                severity,
                "conflicting_environment_defaults",
                owners[0]["path"],
                owners[0].get("line"),
                key,
                f"environment key has {len(defaults)} different defaults across {len(owners)} owners",
            )
        )

    route_owners = {
        key: owners
        for key, owners in analysis.get("route_owners", {}).items()
        if key != "<dynamic>"
    }
    route_overlaps: dict[str, list[dict[str, Any]]] = {}
    for route, owners in sorted(route_owners.items()):
        paths = {row.get("path") for row in owners}
        if len(paths) <= 1:
            continue
        route_overlaps[route] = owners
        findings.append(
            _finding(
                "warning",
                "route_overlap",
                owners[0]["path"],
                owners[0].get("line"),
                route,
                f"route literal is registered from {len(paths)} modules",
            )
        )

    mutation_owners: dict[str, list[dict[str, Any]]] = {}
    for target, owners in analysis.get("mutation_owners", {}).items():
        retained = [row for row in owners if _assignment_is_runtime(target, row)]
        if retained:
            mutation_owners[target] = retained

    mutation_overlaps: dict[str, list[dict[str, Any]]] = {}
    for target, owners in sorted(mutation_owners.items()):
        paths = {row.get("path") for row in owners}
        if target == "<dynamic>" or len(paths) <= 1:
            continue
        mutation_overlaps[target] = owners
        severity = (
            "critical"
            if target in core.CRITICAL_CALLABLES or target in core.PROTECTED_PARAMETERS
            else "warning"
        )
        findings.append(
            _finding(
                severity,
                "overlapping_mutation_owners",
                owners[0]["path"],
                owners[0].get("line"),
                target,
                f"runtime target is mutated from {len(paths)} modules",
            )
        )

    loop_properties = _loop_properties(units)
    watchdogs: list[dict[str, Any]] = []
    bounded_true_loops: list[dict[str, Any]] = []
    for raw in analysis.get("watchdog_loops", []):
        row = dict(raw)
        props = loop_properties.get(
            (str(row.get("path")), int(row.get("line") or 0)),
            {"has_sleep": False, "has_break": False},
        )
        if props.get("has_break"):
            row["busy"] = False
            row["bounded_by_break"] = True
            bounded_true_loops.append(row)
            continue
        if row.get("sleep_seconds") is None and props.get("has_sleep"):
            row["busy"] = False
            row["sleep_source"] = "dynamic_constant_or_expression"
        watchdogs.append(row)
        if row.get("busy"):
            findings.append(
                _finding(
                    "warning",
                    "busy_infinite_loop",
                    str(row.get("path")),
                    int(row.get("line") or 0),
                    "while_true",
                    "persistent loop has no sleep call or sleeps under 10 seconds",
                )
            )

    network_calls = [
        row
        for row in analysis.get("network_calls_inside_loops", [])
        if row.get("path") not in TOOLING_NETWORK_PATHS
        and _network_call_is_relevant(str(row.get("call") or ""))
    ]

    findings.sort(
        key=lambda row: (
            str(row.get("severity")),
            str(row.get("category")),
            str(row.get("path")),
            int(row.get("line") or 0),
            str(row.get("target")),
        )
    )
    summary = dict(analysis.get("summary", {}))
    summary.update(
        {
            "watchdog_loops": len(watchdogs),
            "bounded_true_loops": len(bounded_true_loops),
            "busy_watchdog_loops": sum(1 for row in watchdogs if row.get("busy")),
            "dynamic_mutation_targets": len(mutation_owners),
            "environment_keys": len(environment_owners),
            "environment_default_conflicts": len(environment_conflicts),
            "mutation_overlaps": len(mutation_overlaps),
            "network_calls_inside_loops": len(network_calls),
            "route_literals": len(route_owners),
            "route_overlaps": len(route_overlaps),
            "critical_findings": sum(1 for row in findings if row.get("severity") == "critical"),
            "warning_findings": sum(1 for row in findings if row.get("severity") == "warning"),
            "info_findings": sum(1 for row in findings if row.get("severity") == "info"),
        }
    )

    analysis.update(
        {
            "summary": summary,
            "findings": findings,
            "environment_owners": environment_owners,
            "environment_conflicts": environment_conflicts,
            "route_owners": route_owners,
            "route_overlaps": route_overlaps,
            "mutation_owners": mutation_owners,
            "mutation_overlaps": mutation_overlaps,
            "watchdog_loops": watchdogs,
            "bounded_true_loops": bounded_true_loops,
            "network_calls_inside_loops": network_calls,
            "calibration": {
                "version": VERSION,
                "local_attribute_assignments_excluded": True,
                "generic_dict_get_excluded_from_network_calls": True,
                "tooling_network_calls_excluded": True,
                "dynamic_watchdog_sleep_recognized": True,
                "bounded_break_loops_excluded_from_watchdogs": True,
                "dynamic_literal_conflicts_excluded": True,
            },
        }
    )
    return analysis


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None)
    parser.add_argument("--json", default="refactor_audit_report.json")
    parser.add_argument("--markdown", default="refactor_audit_report.md")
    parser.add_argument("--fail-on-new-critical", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    current_units, current_parse = core._parse_sources(core._current_sources())
    current = _calibrate(core._analyze(current_units, current_parse), current_units)

    base_analysis: dict[str, Any] | None = None
    if args.base and set(args.base) != {"0"}:
        base_sources = core._ref_sources(args.base)
        if base_sources:
            base_units, base_parse = core._parse_sources(base_sources)
            base_analysis = _calibrate(core._analyze(base_units, base_parse), base_units)

    comparison = core._compare(current, base_analysis)
    status = (
        "fail"
        if args.fail_on_new_critical and comparison.get("new_critical")
        else "pass"
    )
    report = {
        "status": status,
        "type": "refactor_structural_audit",
        "version": VERSION,
        "python_version": sys.version.split()[0],
        "base": args.base,
        "policy": {
            "fail_on_new_critical": bool(args.fail_on_new_critical),
            "legacy_debt_is_inventoried_not_auto_failed": True,
            "runtime_imports": False,
            "network_calls": False,
            "state_mutation": False,
            "order_authority": False,
        },
        "comparison": comparison,
        "current": current,
    }

    Path(args.json).write_text(
        _dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.markdown).write_text(core._markdown(report) + "\n", encoding="utf-8")
    print(
        _dumps(
            {
                "status": status,
                "summary": current.get("summary", {}),
                "comparison": {
                    "base_available": comparison.get("base_available"),
                    "new_critical": len(comparison.get("new_critical", [])),
                    "new_warnings": len(comparison.get("new_warnings", [])),
                    "resolved_critical": len(comparison.get("resolved_critical", [])),
                    "resolved_warnings": len(comparison.get("resolved_warnings", [])),
                },
                "json_report": args.json,
                "markdown_report": args.markdown,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
