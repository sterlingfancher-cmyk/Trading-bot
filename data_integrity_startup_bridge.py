"""Deterministic startup bridge for data-integrity runtime modules.

Imported by the WSGI entry point. This module applies bounded integrity and
observability modules and registers their status routes. The paper-accounting
guard is allowed to reconcile paper state from the execution ledger; no module
here places orders or changes live/ML authority.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "data-integrity-startup-bridge-2026-08-07-v6-multi-asset-shadow"
MODULES = (
    "paper_accounting_integrity_guard",
    "paper_accounting_readonly_status",
    "intratrade_path_capture",
    "mae_mfe_integration",
    "daily_data_integrity_audit_overlay",
    "paper_accounting_audit_bridge",
    "provider_request_accounting_overlay",
    "daily_audit_response_reconciliation",
    "multi_asset_shadow_ranker",
)


def apply(core: Any = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for name in MODULES:
        try:
            module = __import__(name)
            fn = getattr(module, "apply", None)
            if callable(fn):
                try:
                    results[name] = fn(core)
                except TypeError:
                    results[name] = fn()
            else:
                results[name] = {"status": "no_apply"}
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "version": VERSION, "modules": results}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for name in MODULES:
        try:
            module = __import__(name)
            fn = getattr(module, "register_routes", None)
            if callable(fn):
                try:
                    results[name] = fn(flask_app, core)
                except TypeError:
                    results[name] = fn(flask_app)
            else:
                results[name] = {"status": "no_routes"}
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "version": VERSION, "modules": results}
