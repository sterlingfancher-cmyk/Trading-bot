"""Install Stable Paper accounting semantics before any reconciliation executes.

This bootstrap exists because the legacy integrity module historically ran before
bidirectional/timestamp compatibility layers.  The ordering is correctness-critical:
execution routing and final event semantics must own the accounting boundary before
any state reconciliation evaluates persisted clean-epoch rows.

Paper-only accounting/bootstrap.  No strategy, sizing, risk-limit, live, or ML
authority changes.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "stable-paper-accounting-bootstrap-2026-08-11-v1"
_APPLIED_CORE_IDS: set[int] = set()


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    results: Dict[str, Any] = {}
    ordered = (
        "canonical_execution_ledger",
        "market_surge_canonical_execution_bridge",
        "paper_bidirectional_accounting_guard",
        "paper_execution_timestamp_semantics",
    )
    for name in ordered:
        try:
            module = __import__(name)
            fn = getattr(module, "apply", None)
            results[name] = fn(core) if callable(fn) else {"status": "no_apply"}
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    failed = [name for name, row in results.items() if isinstance(row, dict) and row.get("status") == "error"]
    if failed:
        return {"status": "error", "overall": "fail", "version": VERSION, "failed_modules": failed, "modules": results}

    _APPLIED_CORE_IDS.add(id(core))
    return {"status": "ok", "overall": "pass", "version": VERSION, "ordered_before_reconcile": True, "modules": results}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
