#!/usr/bin/env python3
"""Mandatory exact-head change safety audit for future Trading-bot changes.

The gate is governance/test-only. It never imports the trading runtime, reads or
writes production state, places orders, or changes runtime authority.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VERSION = "change-safety-audit-2026-08-21-v7-sls-recovery-proof"

CORE_TESTS = (
    "test_architecture_stage_b.py",
    "test_architecture_stage_c.py",
    "test_architecture_stage_d_state_store.py",
    "test_architecture_stage_e_accounting.py",
    "test_architecture_stage_f_canary.py",
)
RUNTIME_TESTS = (
    "test_runtime_shadow_capture.py",
    "test_self_check_runtime_classification.py",
)
STATE_TESTS = ("test_state_store_stage_c.py",)
DECISION_TESTS = ("test_shadow_decision_stage_d.py",)
CONFIG_TESTS = ("test_architecture_stage_b.py",)
PROVENANCE_TESTS = (
    "test_verified_snapshot_provenance_status.py",
    "test_verified_snapshot_backup_provenance_status.py",
    "test_verified_snapshot_journal_ledger_provenance_status.py",
)
DAY_PEAK_PROVENANCE_TESTS = ("test_day_peak_provenance_status.py",)
PRICE_INTEGRITY_TESTS = (
    "test_paper_exit_source_price_plausibility.py",
    "tests/test_paper_exit_guard_dynamic_owner.py",
)
SLS_RECOVERY_PROOF_TESTS = ("test_sls_bad_execution_recovery_proof.py",)


@dataclass(frozen=True)
class AuditDecision:
    status: str
    exact_head_match: bool
    changed_files: tuple[str, ...]
    impact_categories: tuple[str, ...]
    authority_boundaries: tuple[str, ...]
    regression_tests: tuple[str, ...]
    component_results: dict[str, str]
    failures: tuple[str, ...]


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def changed_files(base: str, head: str) -> tuple[str, ...]:
    text = _git("diff", "--name-only", f"{base}...{head}")
    return tuple(sorted({line.strip() for line in text.splitlines() if line.strip()}))


def _is_verified_snapshot_provenance_path(path: str) -> bool:
    lowered = path.lower()
    return "verified_snapshot" in lowered and "provenance" in lowered


def _is_day_peak_provenance_path(path: str) -> bool:
    return "day_peak_provenance" in path.lower()


def _is_price_integrity_path(path: str) -> bool:
    lowered = path.lower()
    return "price_integrity" in lowered or "exit_price_integrity" in lowered


def _is_sls_recovery_proof_path(path: str) -> bool:
    return "sls_bad_execution_recovery_proof" in path.lower()


def classify_paths(paths: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    categories: set[str] = set()
    boundaries: set[str] = set()
    for raw in paths:
        path = raw.lower()
        name = Path(path).name
        if path.endswith(".md") or path.startswith("docs/"):
            categories.add("documentation")
        if path.startswith(".github/workflows/"):
            categories.add("workflow")
        if path.endswith(".py"):
            categories.add("python")
        if name.startswith("test_") or "/test_" in path:
            categories.add("tests")
        if any(
            token in path
            for token in ("bootstrap", "wsgi", "sitecustomize", "usercustomize", "app.py")
        ):
            categories.add("runtime_composition")
            boundaries.add("startup_runtime")
        if any(token in path for token in ("state", "persistence", "journal")):
            categories.add("state_persistence")
            boundaries.add("state")
        if any(token in path for token in ("valuation", "price_integrity", "market_data")):
            categories.add("valuation_market_data")
            boundaries.add("valuation")
        if any(token in path for token in ("accounting", "ledger", "execution")):
            categories.add("accounting_execution")
            boundaries.update(("accounting", "execution"))
        if _is_verified_snapshot_provenance_path(path):
            categories.add("state_persistence")
            boundaries.update(("state", "accounting"))
        if _is_day_peak_provenance_path(path):
            categories.add("risk")
            boundaries.update(("risk", "state"))
        if _is_sls_recovery_proof_path(path):
            categories.update(("state_persistence", "accounting_execution", "risk"))
            boundaries.update(("state", "accounting", "execution", "risk"))
        if "risk" in path:
            categories.add("risk")
            boundaries.add("risk")
        if any(
            token in path
            for token in ("signal", "scanner", "decision", "entry", "exit", "sizing")
        ):
            categories.add("strategy_decision")
            boundaries.add("decision")
        if any(token in path for token in ("config", "contract", "railway", "procfile")):
            categories.add("configuration")
            boundaries.add("configuration")
    if not categories:
        categories.add("other")
    return tuple(sorted(categories)), tuple(sorted(boundaries))


def planned_regressions(paths: Iterable[str]) -> tuple[str, ...]:
    path_tuple = tuple(paths)
    categories, _ = classify_paths(path_tuple)
    tests: list[str] = list(CORE_TESTS)
    if "runtime_composition" in categories or "workflow" in categories:
        tests.extend(RUNTIME_TESTS)
    if "state_persistence" in categories:
        tests.extend(STATE_TESTS)
    if "strategy_decision" in categories:
        tests.extend(DECISION_TESTS)
    if "configuration" in categories:
        tests.extend(CONFIG_TESTS)
    if any(_is_verified_snapshot_provenance_path(path) for path in path_tuple):
        tests.extend(PROVENANCE_TESTS)
    if any(_is_day_peak_provenance_path(path) for path in path_tuple):
        tests.extend(DAY_PEAK_PROVENANCE_TESTS)
    if any(_is_price_integrity_path(path) for path in path_tuple):
        tests.extend(PRICE_INTEGRITY_TESTS)
    if any(_is_sls_recovery_proof_path(path) for path in path_tuple):
        tests.extend(SLS_RECOVERY_PROOF_TESTS)
    existing: list[str] = []
    seen: set[str] = set()
    for test in tests:
        if test not in seen and Path(test).exists():
            existing.append(test)
            seen.add(test)
    return tuple(existing)


def run_regressions(paths: Iterable[str]) -> tuple[str, ...]:
    tests = planned_regressions(paths)
    if not tests:
        return tests
    subprocess.run([sys.executable, "-m", "unittest", "-v", *tests], check=True)
    return tests


def evaluate_gate(
    *,
    expected_head: str,
    actual_head: str,
    paths: Iterable[str],
    component_results: dict[str, str],
    new_critical: int = 0,
) -> AuditDecision:
    paths_tuple = tuple(sorted(paths))
    categories, boundaries = classify_paths(paths_tuple)
    tests = planned_regressions(paths_tuple)
    failures: list[str] = []
    exact = bool(expected_head) and expected_head == actual_head
    if not exact:
        failures.append(
            f"audit head mismatch: expected={expected_head!r} actual={actual_head!r}"
        )
    for name, status in sorted(component_results.items()):
        if status != "success":
            failures.append(f"component {name} is {status!r}, not success")
    if int(new_critical) != 0:
        failures.append(f"architecture debt regression: new_critical={int(new_critical)}")
    return AuditDecision(
        status="pass" if not failures else "fail",
        exact_head_match=exact,
        changed_files=paths_tuple,
        impact_categories=categories,
        authority_boundaries=boundaries,
        regression_tests=tests,
        component_results=dict(sorted(component_results.items())),
        failures=tuple(failures),
    )


def _parse_component(rows: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        if "=" not in row:
            raise ValueError(f"component must be NAME=STATUS: {row!r}")
        key, value = row.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--component", action="append", default=[])
    parser.add_argument("--new-critical", type=int, default=0)
    parser.add_argument("--run-regressions", action="store_true")
    parser.add_argument("--json", default="change_safety_audit_report.json")
    args = parser.parse_args()

    paths = changed_files(args.base, args.head)
    tests = run_regressions(paths) if args.run_regressions else planned_regressions(paths)

    components = _parse_component(args.component)
    expected_head = args.expected_head or args.head
    actual_head = _git("rev-parse", "HEAD")
    decision = evaluate_gate(
        expected_head=expected_head,
        actual_head=actual_head,
        paths=paths,
        component_results=components,
        new_critical=args.new_critical,
    )
    payload = {
        "version": VERSION,
        "status": decision.status,
        "base_sha": args.base,
        "requested_head_sha": args.head,
        "actual_checkout_sha": actual_head,
        "exact_head_match": decision.exact_head_match,
        "changed_files": list(decision.changed_files),
        "impact_categories": list(decision.impact_categories),
        "authority_boundaries": list(decision.authority_boundaries),
        "regression_tests": list(tests),
        "component_results": decision.component_results,
        "new_critical": args.new_critical,
        "failures": list(decision.failures),
        "policy": {
            "mandatory_for_relevant_prs": True,
            "stale_head_fails_closed": True,
            "architecture_debt_growth_allowed": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "places_orders": False,
            "reads_or_writes_production_state": False,
        },
    }
    Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
