"""Housekeeping overlay for a known no-data/delisted symbol.

Adds ORLA to the existing yfinance static no-data set so discovery/provider
paths filter it before a Yahoo request. No trading thresholds or authority are
changed.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "orla-hygiene-overlay-2026-08-10-v1"


def apply(core: Any = None) -> Dict[str, Any]:
    try:
        import yfinance_data_hygiene as hygiene
        blocked = getattr(hygiene, "_DEFAULT_BLOCKED_SYMBOLS", None)
        if isinstance(blocked, set):
            blocked.add("ORLA")
        patch = getattr(hygiene, "_patch_runtime_sources", None)
        if callable(patch):
            patch(core)
        return status_payload()
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}


def status_payload() -> Dict[str, Any]:
    try:
        import yfinance_data_hygiene as hygiene
        active = "ORLA" in set(hygiene.static_blocked_symbols())
    except Exception:
        active = False
    return {
        "status": "ok" if active else "warn",
        "overall": "pass" if active else "warn",
        "type": "orla_hygiene_overlay_status",
        "version": VERSION,
        "orla_static_blocked": active,
        "authority": {
            "provider_hygiene_only": True,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
