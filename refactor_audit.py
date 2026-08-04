#!/usr/bin/env python3
"""Static architecture, mutation, overlap, and refactor-debt audit.

The audit is dependency-free and safe to run in GitHub Actions. It reads source
code and Git history only. It never imports the trading application, contacts a
provider, reads runtime secrets, mutates state, or places orders.

Two operating modes are supported:

1. Per-update review with --base. The current tree is compared with the base
   commit and newly introduced critical findings can fail the gate.
2. Full scheduled audit without --base. The complete architecture inventory is
   emitted without failing solely because legacy debt already exists.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import textwrap
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

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

CRITICAL_CALLABLES = {
    "scan_signals",
    "try_entries_and_rotations",
    "execute_trade",
    "execute_entry",
    "execute_exit",
    "place_order",
    "submit_order",
}

PROTECTED_PARAMETERS = {
    "MAX_DAILY_LOSS_PCT",
    "MAX_INTRADAY_DRAWDOWN_PCT",
    "SELF_DEFENSE_HARD_DAILY_LOSS_PCT",
    "SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT",
    "LIVE_TRADING_ENABLED",
    "BROKER_MODE",
}

PARAMETER_PREFIXES = (
    "MAX_",
    "MIN_",
    "ENTRY_",
    "EXIT_",
    "STOP_",
    "TRAIL_",
    "RISK_",
    "ALLOC",
    "POSITION",
    "EXPOSURE",
    "COOLDOWN",
    "SCORE",
    "CASH",
    "LOSS",
    "DRAWDOWN",
    "WATCHDOG",
    "INTERVAL",
)

NETWORK_CALL_TAILS = {
    "download",
    "download_prices",
    "get",
    "post",
    "request",
    "urlopen",
    "fetch",
}

MUTATION_HELPERS = {
    "setattr",
    "_set_attr",
    "_set_core_attr",
    "replace_callable",
    "patch_callable",
}

IMPORT_TIME_ACTIVATION_TAILS = {
    "apply",
    "install",
    "register_routes",
    "start_watchdog",
    "start",
    "patch",
}

TRADING_PARAMETER_RE = re.compile(
    r"(?:MAX|MIN|ENTRY|EXIT|STOP|TRAIL|RISK|ALLOC|POSITION|EXPOSURE|"
    r"COOLDOWN|SCORE|CASH|LOSS|DRAWDOWN|WATCHDOG|INTERVAL)"
)
VERSION_SUFFIX_RE = re.compile(r"(?:_v\d+|_version\d+|_legacy|_old|_backup)$", re.IGNORECASE)


@dataclass(frozen=True)
class SourceUnit:
    path: str
    text: str
    tree: ast.Module


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    path: str
    line: int | None
    target: str
    detail: str

    @property
    def signature(self) -> str:
        stable_detail = re.sub(r"\bline\s+\d+\b", "line", self.detail.lower())
        return "|".join(
            [
                self.severity,
                self.category,
                self.path,
                self.target,
                stable_detail,
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "path": self.path,
            "line": self.line,
            "target": self.target,
            "detail": self.detail,
            "signature": self.signature,
        }


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _current_sources() -> dict[str, str]:
    result = _git(["ls-files", "-z", "--", "*.py", "**/*.py"])
    paths: list[str] = []
    if result.returncode == 0:
        paths = [item for item in result.stdout.split("\0") if item]
    if not paths:
        paths = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*.py")
            if path.is_file()
            and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
        ]
    sources: dict[str, str] = {}
    for relative in sorted(set(paths)):
        path = ROOT / relative
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            with tokenize.open(path) as handle:
                sources[relative] = handle.read()
        except Exception:
            sources[relative] = path.read_text(encoding="utf-8", errors="replace")
    return sources


def _ref_sources(ref: str) -> dict[str, str]:
    listing = _git(["ls-tree", "-r", "--name-only", ref])
    if listing.returncode != 0:
        return {}
    sources: dict[str, str] = {}
    for relative in listing.stdout.splitlines():
        relative = relative.strip()
        if not relative.endswith(".py"):
            continue
        if any(part in EXCLUDED_PARTS for part in Path(relative).parts):
            continue
        blob = _git(["show", f"{ref}:{relative}"])
        if blob.returncode == 0:
            sources[relative] = blob.stdout
    return sources


def _parse_sources(sources: dict[str, str]) -> tuple[dict[str, SourceUnit], list[Finding]]:
    units: dict[str, SourceUnit] = {}
    findings: list[Finding] = []
    for path, text in sorted(sources.items()):
        try:
            tree = ast.parse(text, filename=path)
        except Exception as exc:
            findings.append(
                Finding(
                    "critical",
                    "parse_error",
                    path,
                    getattr(exc, "lineno", None),
                    path,
                    f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        units[path] = SourceUnit(path=path, text=text, tree=tree)
    return units, findings


def _module_name(path: str) -> str:
    value = path[:-3] if path.endswith(".py") else path
    value = value.replace("/", ".")
    if value.endswith(".__init__"):
        value = value[: -len(".__init__")]
    return value


def _call_name(call: ast.Call) -> str:
    node = call.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts)) if parts else "<dynamic>"


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return "<dynamic>"


def _literal_text(node: ast.AST | None) -> str:
    value = _literal(node)
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:
        return repr(value)


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
    if isinstance(node, ast.Subscript):
        root = _target_name(node.value)
        index = _literal(node.slice)
        return f"{root}[{index!r}]" if root else None
    return None


def _string_args(call: ast.Call) -> list[str]:
    values: list[str] = []
    for node in call.args:
        value = _literal(node)
        if isinstance(value, str):
            values.append(value)
    for keyword in call.keywords:
        value = _literal(keyword.value)
        if isinstance(value, str):
            values.append(value)
    return values


def _module_level_nodes(tree: ast.Module) -> Iterator[ast.AST]:
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.nodes: list[ast.AST] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def generic_visit(self, node: ast.AST) -> None:
            self.nodes.append(node)
            super().generic_visit(node)

    visitor = Visitor()
    for statement in tree.body:
        visitor.visit(statement)
    return iter(visitor.nodes)


def _function_length(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end = getattr(node, "end_lineno", None) or node.lineno
    return max(1, int(end) - int(node.lineno) + 1)


def _body_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    payload = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _while_sleep_seconds(node: ast.While) -> float | None:
    values: list[float] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _call_name(child).rsplit(".", 1)[-1] != "sleep" or not child.args:
            continue
        value = _literal(child.args[0])
        if isinstance(value, (int, float)):
            values.append(float(value))
    return min(values) if values else None


def _is_true_loop(node: ast.While) -> bool:
    return isinstance(node.test, ast.Constant) and node.test.value is True


def _network_calls_inside_loops(tree: ast.Module) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.loop_depth = 0

        def visit_For(self, node: ast.For) -> None:
            self.loop_depth += 1
            self.generic_visit(node)
            self.loop_depth -= 1

        def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
            self.loop_depth += 1
            self.generic_visit(node)
            self.loop_depth -= 1

        def visit_While(self, node: ast.While) -> None:
            self.loop_depth += 1
            self.generic_visit(node)
            self.loop_depth -= 1

        def visit_Call(self, node: ast.Call) -> None:
            if self.loop_depth:
                name = _call_name(node)
                tail = name.rsplit(".", 1)[-1]
                if tail in NETWORK_CALL_TAILS:
                    rows.append((getattr(node, "lineno", 0), name))
            self.generic_visit(node)

    Visitor().visit(tree)
    return rows


def _strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(graph.get(node, set())):
            if neighbor not in indices:
                visit(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif neighbor in on_stack:
                lowlink[node] = min(lowlink[node], indices[neighbor])

        if lowlink[node] == indices[node]:
            component: list[str] = []
            while stack:
                item = stack.pop()
                on_stack.discard(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def _analyze(units: dict[str, SourceUnit], initial: list[Finding]) -> dict[str, Any]:
    findings = list(initial)
    module_by_path = {path: _module_name(path) for path in units}
    internal_modules = set(module_by_path.values())
    module_roots = {name.split(".", 1)[0] for name in internal_modules}
    graph: dict[str, set[str]] = {name: set() for name in internal_modules}

    env_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    constant_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    route_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mutation_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    function_hashes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_metrics: list[dict[str, Any]] = []
    module_level_calls: list[dict[str, Any]] = []
    watchdogs: list[dict[str, Any]] = []
    broad_exception_passes: list[dict[str, Any]] = []
    loop_network_calls: list[dict[str, Any]] = []
    import_time_threads: list[dict[str, Any]] = []

    for path, unit in sorted(units.items()):
        module = module_by_path[path]
        lines = unit.text.count("\n") + 1
        function_count = 0
        max_function_lines = 0
        dynamic_mutations = 0
        broad_passes = 0

        for node in ast.walk(unit.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in module_roots:
                        candidates = [name for name in internal_modules if name == alias.name or name.startswith(alias.name + ".")]
                        if alias.name in internal_modules:
                            graph[module].add(alias.name)
                        elif candidates:
                            graph[module].add(sorted(candidates)[0])
            elif isinstance(node, ast.ImportFrom):
                imported = node.module or ""
                if node.level:
                    parts = module.split(".")[:-node.level]
                    imported = ".".join(parts + ([imported] if imported else []))
                if imported in internal_modules:
                    graph[module].add(imported)
                elif imported.split(".", 1)[0] in module_roots:
                    candidates = [name for name in internal_modules if name == imported or name.startswith(imported + ".")]
                    if candidates:
                        graph[module].add(sorted(candidates)[0])

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1
                length = _function_length(node)
                max_function_lines = max(max_function_lines, length)
                if length >= 250:
                    findings.append(
                        Finding(
                            "warning",
                            "large_function",
                            path,
                            node.lineno,
                            node.name,
                            f"function spans {length} lines",
                        )
                    )
                if len(node.body) >= 2:
                    function_hashes[_body_hash(node)].append(
                        {"path": path, "line": node.lineno, "function": node.name, "lines": length}
                    )

            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (
                    isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
                )
                body_only_pass = bool(node.body) and all(isinstance(item, ast.Pass) for item in node.body)
                if broad and body_only_pass:
                    broad_passes += 1
                    broad_exception_passes.append(
                        {"path": path, "line": node.lineno, "exception": "broad"}
                    )

            if isinstance(node, ast.While) and _is_true_loop(node):
                seconds = _while_sleep_seconds(node)
                row = {
                    "path": path,
                    "line": node.lineno,
                    "sleep_seconds": seconds,
                    "busy": seconds is None or seconds < 10.0,
                }
                watchdogs.append(row)
                if row["busy"]:
                    findings.append(
                        Finding(
                            "warning",
                            "busy_infinite_loop",
                            path,
                            node.lineno,
                            "while_true",
                            "infinite loop has no constant sleep or sleeps under 10 seconds",
                        )
                    )

            if isinstance(node, ast.Call):
                call_name = _call_name(node)
                tail = call_name.rsplit(".", 1)[-1]

                is_env_get = False
                key: Any = None
                default: Any = None
                if isinstance(node.func, ast.Attribute):
                    owner = node.func.value
                    if node.func.attr == "get" and isinstance(owner, ast.Attribute):
                        is_env_get = (
                            owner.attr == "environ"
                            and isinstance(owner.value, ast.Name)
                            and owner.value.id == "os"
                        )
                    elif node.func.attr == "getenv" and isinstance(owner, ast.Name) and owner.id == "os":
                        is_env_get = True
                if is_env_get and node.args:
                    key = _literal(node.args[0])
                    default = _literal(node.args[1]) if len(node.args) > 1 else None
                    if isinstance(key, str):
                        env_owners[key].append(
                            {"path": path, "line": node.lineno, "default": default}
                        )

                if tail in MUTATION_HELPERS or call_name.endswith(".setattr"):
                    strings = _string_args(node)
                    target = strings[0] if strings else "<dynamic>"
                    if tail in {"_set_attr", "_set_core_attr"} and len(strings) >= 1:
                        target = strings[0]
                    elif tail == "setattr" and len(strings) >= 1:
                        target = strings[0]
                    dynamic_mutations += 1
                    mutation_owners[target].append(
                        {
                            "path": path,
                            "line": node.lineno,
                            "kind": "call",
                            "call": call_name,
                        }
                    )
                    if target in CRITICAL_CALLABLES or target in PROTECTED_PARAMETERS:
                        findings.append(
                            Finding(
                                "critical",
                                "critical_dynamic_mutation",
                                path,
                                node.lineno,
                                target,
                                f"{call_name} mutates protected runtime target",
                            )
                        )

                if tail == "add_url_rule" and node.args:
                    route = _literal(node.args[0])
                    if isinstance(route, str):
                        route_owners[route].append(
                            {"path": path, "line": node.lineno, "kind": "add_url_rule"}
                        )

        for node in unit.tree.body:
            targets: list[tuple[str, ast.AST | None, int]] = []
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = _target_name(target)
                    if name:
                        targets.append((name, node.value, node.lineno))
            elif isinstance(node, ast.AnnAssign):
                name = _target_name(node.target)
                if name:
                    targets.append((name, node.value, node.lineno))
            for name, value_node, line in targets:
                leaf = name.rsplit(".", 1)[-1]
                if leaf.isupper() and (leaf in PROTECTED_PARAMETERS or leaf.startswith(PARAMETER_PREFIXES) or TRADING_PARAMETER_RE.search(leaf)):
                    constant_owners[leaf].append(
                        {
                            "path": path,
                            "line": line,
                            "value": _literal(value_node),
                            "value_text": _literal_text(value_node),
                        }
                    )

        for node in ast.walk(unit.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = _target_name(target)
                    if not name:
                        continue
                    leaf = name.rsplit(".", 1)[-1]
                    if "." in name or "[" in name:
                        mutation_owners[leaf].append(
                            {"path": path, "line": node.lineno, "kind": "assignment", "target": name}
                        )
                        if leaf in CRITICAL_CALLABLES:
                            findings.append(
                                Finding(
                                    "critical",
                                    "critical_callable_replacement",
                                    path,
                                    node.lineno,
                                    leaf,
                                    f"direct assignment replaces {name}",
                                )
                            )
            elif isinstance(node, ast.AnnAssign):
                name = _target_name(node.target)
                if name and "." in name:
                    leaf = name.rsplit(".", 1)[-1]
                    mutation_owners[leaf].append(
                        {"path": path, "line": node.lineno, "kind": "assignment", "target": name}
                    )

        for node in ast.walk(unit.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and _call_name(decorator).rsplit(".", 1)[-1] == "route" and decorator.args:
                        route = _literal(decorator.args[0])
                        if isinstance(route, str):
                            route_owners[route].append(
                                {"path": path, "line": node.lineno, "kind": "decorator", "function": node.name}
                            )

        for node in _module_level_nodes(unit.tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node)
            tail = call_name.rsplit(".", 1)[-1]
            row = {"path": path, "line": getattr(node, "lineno", None), "call": call_name}
            module_level_calls.append(row)
            if tail == "Thread" or call_name.endswith("threading.Thread"):
                import_time_threads.append(row)
                findings.append(
                    Finding(
                        "warning",
                        "import_time_thread_creation",
                        path,
                        getattr(node, "lineno", None),
                        call_name,
                        "thread object is created at module import time",
                    )
                )
            if tail in IMPORT_TIME_ACTIVATION_TAILS:
                findings.append(
                    Finding(
                        "info",
                        "import_time_activation",
                        path,
                        getattr(node, "lineno", None),
                        call_name,
                        "activation call occurs outside a function or class",
                    )
                )

        for line, call in _network_calls_inside_loops(unit.tree):
            loop_network_calls.append({"path": path, "line": line, "call": call})

        if lines >= 1500:
            findings.append(
                Finding(
                    "warning",
                    "large_module",
                    path,
                    1,
                    path,
                    f"module spans {lines} lines",
                )
            )
        if broad_passes >= 5:
            findings.append(
                Finding(
                    "warning",
                    "suppressed_exceptions",
                    path,
                    1,
                    path,
                    f"module contains {broad_passes} broad exception handlers that only pass",
                )
            )

        file_metrics.append(
            {
                "path": path,
                "module": module,
                "lines": lines,
                "functions": function_count,
                "max_function_lines": max_function_lines,
                "dynamic_mutations": dynamic_mutations,
                "broad_exception_passes": broad_passes,
            }
        )

    cycles = _strongly_connected(graph)
    for cycle in cycles:
        findings.append(
            Finding(
                "warning",
                "import_cycle",
                cycle[0],
                None,
                " -> ".join(cycle),
                f"internal import cycle spans {len(cycle)} modules",
            )
        )

    env_conflicts: dict[str, list[dict[str, Any]]] = {}
    for key, owners in sorted(env_owners.items()):
        defaults = {json.dumps(row.get("default"), sort_keys=True, default=str) for row in owners}
        if len(defaults) > 1:
            env_conflicts[key] = owners
            severity = "critical" if key in PROTECTED_PARAMETERS else "warning"
            findings.append(
                Finding(
                    severity,
                    "conflicting_environment_defaults",
                    owners[0]["path"],
                    owners[0]["line"],
                    key,
                    f"environment key has {len(defaults)} different defaults across {len(owners)} owners",
                )
            )

    constant_conflicts: dict[str, list[dict[str, Any]]] = {}
    for name, owners in sorted(constant_owners.items()):
        paths = {row["path"] for row in owners}
        values = {row["value_text"] for row in owners}
        if len(paths) > 1 and len(values) > 1:
            constant_conflicts[name] = owners
            findings.append(
                Finding(
                    "warning",
                    "conflicting_parameter_owners",
                    owners[0]["path"],
                    owners[0]["line"],
                    name,
                    f"parameter has {len(values)} values across {len(paths)} modules",
                )
            )

    route_overlaps: dict[str, list[dict[str, Any]]] = {}
    for route, owners in sorted(route_owners.items()):
        paths = {row["path"] for row in owners}
        if len(paths) > 1:
            route_overlaps[route] = owners
            findings.append(
                Finding(
                    "warning",
                    "route_overlap",
                    owners[0]["path"],
                    owners[0]["line"],
                    route,
                    f"route literal is registered from {len(paths)} modules",
                )
            )

    mutation_overlaps: dict[str, list[dict[str, Any]]] = {}
    for target, owners in sorted(mutation_owners.items()):
        paths = {row["path"] for row in owners}
        if target != "<dynamic>" and len(paths) > 1:
            mutation_overlaps[target] = owners
            severity = "critical" if target in CRITICAL_CALLABLES or target in PROTECTED_PARAMETERS else "warning"
            findings.append(
                Finding(
                    severity,
                    "overlapping_mutation_owners",
                    owners[0]["path"],
                    owners[0]["line"],
                    target,
                    f"runtime target is mutated from {len(paths)} modules",
                )
            )

    duplicate_functions: list[dict[str, Any]] = []
    for digest, owners in sorted(function_hashes.items()):
        paths = {row["path"] for row in owners}
        if len(paths) > 1:
            row = {"body_hash": digest, "owners": owners}
            duplicate_functions.append(row)
            findings.append(
                Finding(
                    "info",
                    "duplicate_function_body",
                    owners[0]["path"],
                    owners[0]["line"],
                    digest,
                    f"same function body appears in {len(paths)} modules",
                )
            )

    version_families: dict[str, list[str]] = defaultdict(list)
    for path in units:
        stem = Path(path).stem
        family = VERSION_SUFFIX_RE.sub("", stem)
        version_families[family].append(path)
    overlapping_families = {
        family: sorted(paths)
        for family, paths in version_families.items()
        if len(paths) > 1
    }
    for family, paths in sorted(overlapping_families.items()):
        findings.append(
            Finding(
                "info",
                "parallel_version_family",
                paths[0],
                1,
                family,
                f"{len(paths)} similarly named modules may represent parallel implementations",
            )
        )

    findings.sort(key=lambda row: (row.severity, row.category, row.path, row.line or 0, row.target))
    critical = [row for row in findings if row.severity == "critical"]
    warnings = [row for row in findings if row.severity == "warning"]
    infos = [row for row in findings if row.severity == "info"]

    return {
        "summary": {
            "python_files": len(units),
            "total_lines": sum(row["lines"] for row in file_metrics),
            "internal_import_edges": sum(len(values) for values in graph.values()),
            "import_cycles": len(cycles),
            "module_level_calls": len(module_level_calls),
            "import_time_threads": len(import_time_threads),
            "watchdog_loops": len(watchdogs),
            "busy_watchdog_loops": sum(1 for row in watchdogs if row["busy"]),
            "dynamic_mutation_targets": len(mutation_owners),
            "mutation_overlaps": len(mutation_overlaps),
            "environment_keys": len(env_owners),
            "environment_default_conflicts": len(env_conflicts),
            "parameter_names": len(constant_owners),
            "parameter_owner_conflicts": len(constant_conflicts),
            "route_literals": len(route_owners),
            "route_overlaps": len(route_overlaps),
            "duplicate_function_groups": len(duplicate_functions),
            "parallel_version_families": len(overlapping_families),
            "broad_exception_passes": len(broad_exception_passes),
            "network_calls_inside_loops": len(loop_network_calls),
            "critical_findings": len(critical),
            "warning_findings": len(warnings),
            "info_findings": len(infos),
        },
        "findings": [row.as_dict() for row in findings],
        "dependency_graph": {key: sorted(values) for key, values in sorted(graph.items())},
        "import_cycles": cycles,
        "environment_owners": dict(sorted(env_owners.items())),
        "environment_conflicts": env_conflicts,
        "parameter_owners": dict(sorted(constant_owners.items())),
        "parameter_conflicts": constant_conflicts,
        "route_owners": dict(sorted(route_owners.items())),
        "route_overlaps": route_overlaps,
        "mutation_owners": dict(sorted(mutation_owners.items())),
        "mutation_overlaps": mutation_overlaps,
        "duplicate_function_groups": duplicate_functions,
        "parallel_version_families": overlapping_families,
        "module_level_calls": module_level_calls,
        "import_time_threads": import_time_threads,
        "watchdog_loops": watchdogs,
        "broad_exception_passes": broad_exception_passes,
        "network_calls_inside_loops": loop_network_calls,
        "file_metrics": sorted(file_metrics, key=lambda row: (-row["lines"], row["path"])),
    }


def _compare(current: dict[str, Any], base: dict[str, Any] | None) -> dict[str, Any]:
    if base is None:
        return {
            "base_available": False,
            "new_critical": [],
            "new_warnings": [],
            "resolved_critical": [],
            "resolved_warnings": [],
            "summary_delta": {},
        }

    current_findings = current.get("findings", [])
    base_findings = base.get("findings", [])
    current_by_sig = {row["signature"]: row for row in current_findings}
    base_by_sig = {row["signature"]: row for row in base_findings}

    def select(source: dict[str, dict[str, Any]], other: dict[str, dict[str, Any]], severity: str) -> list[dict[str, Any]]:
        return [
            source[key]
            for key in sorted(set(source) - set(other))
            if source[key].get("severity") == severity
        ]

    current_summary = current.get("summary", {})
    base_summary = base.get("summary", {})
    delta = {
        key: current_summary.get(key, 0) - base_summary.get(key, 0)
        for key in sorted(set(current_summary) | set(base_summary))
        if isinstance(current_summary.get(key, 0), (int, float))
        and isinstance(base_summary.get(key, 0), (int, float))
    }
    return {
        "base_available": True,
        "new_critical": select(current_by_sig, base_by_sig, "critical"),
        "new_warnings": select(current_by_sig, base_by_sig, "warning"),
        "resolved_critical": select(base_by_sig, current_by_sig, "critical"),
        "resolved_warnings": select(base_by_sig, current_by_sig, "warning"),
        "summary_delta": delta,
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["current"]["summary"]
    comparison = report["comparison"]
    lines = [
        "# Refactor and Structural Code Audit",
        "",
        f"- Status: **{report['status'].upper()}**",
        f"- Python: `{report['python_version']}`",
        f"- Base comparison: `{report.get('base') or 'full scheduled audit'}`",
        f"- Python files: **{summary['python_files']}**",
        f"- Total source lines: **{summary['total_lines']}**",
        f"- Critical findings: **{summary['critical_findings']}**",
        f"- Warning findings: **{summary['warning_findings']}**",
        f"- New critical findings: **{len(comparison['new_critical'])}**",
        f"- New warnings: **{len(comparison['new_warnings'])}**",
        "",
        "## Architecture Surface",
        "",
        f"- Internal import edges: {summary['internal_import_edges']}",
        f"- Import cycles: {summary['import_cycles']}",
        f"- Module-level calls: {summary['module_level_calls']}",
        f"- Import-time thread creation: {summary['import_time_threads']}",
        f"- Watchdog loops: {summary['watchdog_loops']} ({summary['busy_watchdog_loops']} busy)",
        f"- Mutation targets: {summary['dynamic_mutation_targets']}",
        f"- Overlapping mutation owners: {summary['mutation_overlaps']}",
        f"- Conflicting environment defaults: {summary['environment_default_conflicts']}",
        f"- Conflicting parameter owners: {summary['parameter_owner_conflicts']}",
        f"- Route overlaps: {summary['route_overlaps']}",
        f"- Duplicate function-body groups: {summary['duplicate_function_groups']}",
        f"- Parallel version families: {summary['parallel_version_families']}",
        f"- Broad exception/pass handlers: {summary['broad_exception_passes']}",
        f"- Network-like calls inside loops: {summary['network_calls_inside_loops']}",
        "",
    ]

    def finding_section(title: str, rows: list[dict[str, Any]], limit: int = 40) -> None:
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.extend(["None.", ""])
            return
        for row in rows[:limit]:
            location = row["path"] + (f":{row['line']}" if row.get("line") else "")
            lines.append(
                f"- **{row['category']}** — `{location}` — `{row['target']}`: {row['detail']}"
            )
        if len(rows) > limit:
            lines.append(f"- … {len(rows) - limit} additional findings are in the JSON artifact.")
        lines.append("")

    finding_section("New Critical Findings", comparison["new_critical"])
    finding_section("New Warnings", comparison["new_warnings"])

    current_findings = report["current"].get("findings", [])
    finding_section(
        "Highest-Severity Existing Findings",
        [row for row in current_findings if row.get("severity") in {"critical", "warning"}],
        limit=60,
    )

    lines.extend(
        [
            "## Interpretation",
            "",
            textwrap.dedent(
                """
                A warning is refactor debt, not proof of a runtime defect. A critical finding
                identifies a protected callable, hard-risk parameter, or conflicting protected
                default that deserves explicit review. Per-update validation fails only for newly
                introduced critical findings; scheduled audits inventory existing debt so it can be
                removed in controlled batches rather than through unsafe mass deletion.
                """
            ).strip(),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=None, help="Base Git commit for per-update comparison.")
    parser.add_argument("--json", default="refactor_audit_report.json")
    parser.add_argument("--markdown", default="refactor_audit_report.md")
    parser.add_argument("--fail-on-new-critical", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    current_units, current_parse = _parse_sources(_current_sources())
    current = _analyze(current_units, current_parse)

    base_report: dict[str, Any] | None = None
    if args.base and set(args.base) != {"0"}:
        base_sources = _ref_sources(args.base)
        if base_sources:
            base_units, base_parse = _parse_sources(base_sources)
            base_report = _analyze(base_units, base_parse)

    comparison = _compare(current, base_report)
    new_critical = comparison["new_critical"]
    status = "fail" if args.fail_on_new_critical and new_critical else "pass"
    report = {
        "status": status,
        "type": "refactor_structural_audit",
        "version": "refactor-audit-2026-08-03-v1",
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

    json_path = ROOT / args.json
    markdown_path = ROOT / args.markdown
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "summary": current["summary"],
        "comparison": {
            "base_available": comparison["base_available"],
            "new_critical": len(comparison["new_critical"]),
            "new_warnings": len(comparison["new_warnings"]),
            "resolved_critical": len(comparison["resolved_critical"]),
            "resolved_warnings": len(comparison["resolved_warnings"]),
        },
        "json_report": args.json,
        "markdown_report": args.markdown,
    }, indent=2, sort_keys=True))
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
