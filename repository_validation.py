#!/usr/bin/env python3
"""Repository-wide static validation and change classification.

This script is intentionally dependency-free so it can run in GitHub Actions,
Cursor, Codex, or a local Python 3.11 environment before any Railway deploy.

It does not import the trading application, contact providers, place orders,
read secrets, or mutate trading state.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

PROTECTED_ENV_DEFAULTS: dict[str, tuple[str, ...]] = {
    "MAX_DAILY_LOSS_PCT": ("0.03",),
    "MAX_INTRADAY_DRAWDOWN_PCT": ("0.025",),
    "ALLOW_MANUAL_AFTER_HOURS_TRADING": ("false",),
}

PROTECTED_MUTATION_NAMES = {
    "MAX_DAILY_LOSS_PCT",
    "MAX_INTRADAY_DRAWDOWN_PCT",
    "SELF_DEFENSE_HARD_DAILY_LOSS_PCT",
    "SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT",
}
PROTECTED_MUTATION_PREFIXES = (
    "MIN_ENTRY_SCORE_",
)

ADVISORY_ONLY_MODULES = (
    "performance_audit_lab.py",
    "performance_audit_lab_v2.py",
    "performance_audit_v2_async_route.py",
    "performance_audit_v2_recovery_guard.py",
)
FORBIDDEN_ORDER_CALLS = {
    "submit_order",
    "place_order",
    "send_order",
    "create_order",
    "execute_order",
    "buy",
    "sell",
}

BEHAVIOR_KEYWORDS = (
    "app.py",
    "strategy",
    "signal",
    "score",
    "entry",
    "exit",
    "risk",
    "sizing",
    "position",
    "portfolio",
    "scanner",
    "starter",
    "participation",
    "allocator",
    "policy",
    "stop",
    "broker",
    "execution",
    "order",
)
RUNTIME_KEYWORDS = (
    "gunicorn",
    "wsgi",
    "diagnostic",
    "self_check",
    "self-check",
    "status",
    "provider",
    "state",
    "recovery",
    "guard",
    "route",
    "watchdog",
)


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _tracked_python_files() -> list[Path]:
    result = _run_git(["ls-files", "-z", "--", "*.py", "**/*.py"])
    candidates: set[Path] = set()
    if result.returncode == 0:
        for raw in result.stdout.split("\0"):
            if raw:
                path = ROOT / raw
                if path.is_file():
                    candidates.add(path)
    if not candidates:
        candidates = {
            path
            for path in ROOT.rglob("*.py")
            if path.is_file() and not any(part in EXCLUDED_PARTS for part in path.parts)
        }
    return sorted(
        path
        for path in candidates
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    )


def _source(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        parts = [fn.attr]
        value = fn.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return "<dynamic>"


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _env_defaults(tree: ast.AST) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
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
        default = _literal(node.args[1])
        if isinstance(key, str):
            defaults[key] = default
    return defaults


def _string_arguments(node: ast.Call) -> list[str]:
    values: list[str] = []
    for arg in node.args:
        value = _literal(arg)
        if isinstance(value, str):
            values.append(value)
    for keyword in node.keywords:
        value = _literal(keyword.value)
        if isinstance(value, str):
            values.append(value)
    return values


def _is_protected_name(value: str) -> bool:
    return value in PROTECTED_MUTATION_NAMES or value.startswith(PROTECTED_MUTATION_PREFIXES)


def _module_level_calls(tree: ast.Module) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    class ModuleLevelVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def visit_Call(self, node: ast.Call) -> None:
            rows.append(
                {
                    "line": getattr(node, "lineno", None),
                    "call": _call_name(node),
                }
            )
            self.generic_visit(node)

    visitor = ModuleLevelVisitor()
    for statement in tree.body:
        visitor.visit(statement)
    return rows


def _dynamic_mutations(tree: ast.Module) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name.endswith("setattr") or name in {"_set_attr", "_set_core_attr"}:
            rows.append(
                {
                    "line": getattr(node, "lineno", None),
                    "call": name,
                    "string_arguments": _string_arguments(node),
                }
            )
    return rows


def _changed_files(base: str | None) -> list[str]:
    if not base or set(base) == {"0"}:
        return []
    result = _run_git(["diff", "--name-only", f"{base}...HEAD"])
    if result.returncode != 0:
        result = _run_git(["diff", "--name-only", base, "HEAD"])
    if result.returncode != 0:
        return []
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _classify_changes(changed: list[str]) -> tuple[str, list[str]]:
    if not changed:
        return (
            "full_repository_validation",
            [
                "compile_all_tracked_python",
                "static_safety_contracts",
                "manual_behavior_classification_if_releasing",
            ],
        )

    lowered = [name.lower() for name in changed]
    non_behavior_suffixes = {".md", ".txt", ".yml", ".yaml"}
    if all(Path(name).suffix.lower() in non_behavior_suffixes for name in changed):
        return (
            "documentation_or_ci_only",
            ["syntax_or_schema_validation", "no_backtest_required"],
        )

    if any(any(keyword in name for keyword in BEHAVIOR_KEYWORDS) for name in lowered):
        return (
            "trading_behavior_change",
            [
                "compile_all_tracked_python",
                "static_safety_contracts",
                "targeted_unit_and_invariant_tests",
                "baseline_vs_candidate_backtest",
                "walk_forward_or_untouched_holdout",
                "transaction_cost_and_slippage_sensitivity",
                "regime_segmented_results",
                "forward_shadow_or_bounded_paper_canary",
                "post_deploy_paper_self_check",
            ],
        )

    if any(any(keyword in name for keyword in RUNTIME_KEYWORDS) for name in lowered):
        return (
            "runtime_reliability_or_composition_change",
            [
                "compile_all_tracked_python",
                "static_safety_contracts",
                "targeted_mock_or_integration_tests",
                "worker_startup_smoke_test",
                "post_deploy_paper_self_check",
                "backtest_only_if_decision_output_can_change",
            ],
        )

    return (
        "general_code_change",
        [
            "compile_all_tracked_python",
            "static_safety_contracts",
            "targeted_unit_tests",
            "post_deploy_smoke_test_if_runtime_is_affected",
        ],
    )


def validate(base: str | None = None) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    files = _tracked_python_files()
    module_rows: list[dict[str, Any]] = []
    trees: dict[str, ast.Module] = {}

    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        try:
            text = _source(path)
            compile(text, relative, "exec")
            tree = ast.parse(text, filename=relative)
        except Exception as exc:
            errors.append(f"{relative}: compile_or_parse_failed: {type(exc).__name__}: {exc}")
            continue
        trees[relative] = tree
        module_rows.append(
            {
                "file": relative,
                "module_level_calls": _module_level_calls(tree),
                "dynamic_mutations": _dynamic_mutations(tree),
            }
        )

    app_tree = trees.get("app.py")
    if app_tree is None:
        errors.append("app.py: missing_or_unparseable")
    else:
        defaults = _env_defaults(app_tree)
        for key, allowed in PROTECTED_ENV_DEFAULTS.items():
            actual = str(defaults.get(key)).lower()
            if actual not in {value.lower() for value in allowed}:
                errors.append(
                    f"app.py: protected default {key} expected one of {allowed}, found {defaults.get(key)!r}"
                )

    adaptive_path = "paper_regime_adaptive_policy.py"
    adaptive_tree = trees.get(adaptive_path)
    if adaptive_tree is not None:
        defaults = _env_defaults(adaptive_tree)
        if str(defaults.get("PAPER_REGIME_ADAPTIVE_POLICY_PAPER_ONLY")).lower() != "true":
            errors.append(
                f"{adaptive_path}: PAPER_REGIME_ADAPTIVE_POLICY_PAPER_ONLY must default to true"
            )
        for mutation in _dynamic_mutations(adaptive_tree):
            protected = [
                value
                for value in mutation["string_arguments"]
                if _is_protected_name(value)
            ]
            if protected:
                errors.append(
                    f"{adaptive_path}:{mutation['line']}: protected runtime mutation {protected}"
                )
        for node in ast.walk(adaptive_tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr in {"scan_signals", "try_entries_and_rotations"}
                    ):
                        errors.append(
                            f"{adaptive_path}:{getattr(node, 'lineno', None)}: "
                            f"must not replace {target.attr}"
                        )

    advisory_order_calls: list[dict[str, Any]] = []
    for relative in ADVISORY_ONLY_MODULES:
        tree = trees.get(relative)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = _call_name(node)
            tail = call.rsplit(".", 1)[-1]
            if tail in FORBIDDEN_ORDER_CALLS:
                advisory_order_calls.append(
                    {
                        "file": relative,
                        "line": getattr(node, "lineno", None),
                        "call": call,
                    }
                )
    if advisory_order_calls:
        errors.append(
            "advisory performance modules contain possible order calls: "
            + json.dumps(advisory_order_calls, sort_keys=True)
        )

    changed = _changed_files(base)
    classification, required_gates = _classify_changes(changed)
    import_time_total = sum(len(row["module_level_calls"]) for row in module_rows)
    mutation_total = sum(len(row["dynamic_mutations"]) for row in module_rows)

    report = {
        "status": "pass" if not errors else "fail",
        "python_version": sys.version.split()[0],
        "tracked_python_files": len(files),
        "parsed_python_files": len(trees),
        "compile_errors": len(
            [error for error in errors if "compile_or_parse_failed" in error]
        ),
        "static_contract_errors": len(errors),
        "changed_files": changed,
        "change_classification": classification,
        "required_gates": required_gates,
        "inventory": {
            "module_level_call_count": import_time_total,
            "dynamic_mutation_count": mutation_total,
            "modules_with_module_level_calls": sorted(
                row["file"] for row in module_rows if row["module_level_calls"]
            ),
            "modules_with_dynamic_mutations": sorted(
                row["file"] for row in module_rows if row["dynamic_mutations"]
            ),
        },
        "errors": errors,
    }
    return report, errors


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default=None,
        help="Optional base commit for changed-file classification.",
    )
    parser.add_argument(
        "--report",
        default="repository_validation_report.json",
        help="JSON report path relative to the repository root.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report, errors = validate(args.base)
    report_path = ROOT / args.report
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
