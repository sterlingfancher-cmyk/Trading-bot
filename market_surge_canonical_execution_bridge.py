"""Route market-surge paper entries through the canonical execution boundary.

The original market-surge deployment path mutated paper positions/cash and then
appended custom rows directly to ``state.trades``.  That bypassed ``core.record_trade``
and therefore bypassed the canonical append-only execution ledger.

This bridge replaces only that custom trade-row append function.  Position
selection, sizing, surge eligibility, stop/trailing behavior, risk limits, and
paper-only authority are unchanged.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List

VERSION = "market-surge-canonical-execution-bridge-2026-08-11-v1"
_APPLIED_CORE_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    try:
        import market_surge_deployment_mode as surge
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    record_trade = getattr(core, "record_trade", None)
    if not callable(record_trade):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "core.record_trade_missing"}

    current = getattr(surge, "_append_trade_rows", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "market_surge._append_trade_rows_missing"}

    if getattr(current, "_canonical_execution_bridge_version", None) == VERSION:
        _APPLIED_CORE_IDS.add(id(core))
        return status_payload(core)

    prior = getattr(current, "_canonical_execution_bridge_prior", current)

    @functools.wraps(prior)
    def canonical_append_trade_rows(pf: Dict[str, Any], executed_entries: List[Dict[str, Any]], now_text: str) -> None:
        if not executed_entries:
            return

        for row in executed_entries:
            symbol = str(row.get("symbol") or "").upper().strip()
            price = _f(row.get("entry"), 0.0)
            shares = _f(row.get("shares"), 0.0)
            if not symbol or price <= 0.0 or shares <= 0.0:
                # Fail closed: do not fabricate a malformed execution row.  The
                # surrounding surge executor will preserve its paper state and
                # the normal integrity audit will surface the mismatch.
                continue

            extra = {
                "source": "market_surge_deployment_mode",
                "type": "paper_market_surge_deployment",
                "original_execution_time": now_text,
                "bucket": row.get("bucket"),
                "selection_reason": row.get("selection_reason"),
                "allocation_dollars": row.get("allocation_dollars"),
                "allocation_pct": row.get("allocation_pct"),
                "account_risk_pct": row.get("account_risk_pct"),
                "planned_stop": row.get("planned_stop"),
                "trade_authority": "paper_only_state_entry",
                "live_trade_authority": "none",
                "ml_authority": "shadow_only",
                "market_surge_version": getattr(surge, "VERSION", None),
                "canonical_surge_bridge_version": VERSION,
            }
            record_trade("entry", symbol, "long", price, shares, extra)

    canonical_append_trade_rows._canonical_execution_bridge_version = VERSION  # type: ignore[attr-defined]
    canonical_append_trade_rows._canonical_execution_bridge_prior = prior  # type: ignore[attr-defined]
    surge._append_trade_rows = canonical_append_trade_rows
    _APPLIED_CORE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    try:
        import market_surge_deployment_mode as surge
        fn = getattr(surge, "_append_trade_rows", None)
        hooked = getattr(fn, "_canonical_execution_bridge_version", None) == VERSION
    except Exception:
        hooked = False
    return {
        "status": "ok" if hooked else "pending",
        "overall": "pass" if hooked else "warn",
        "type": "market_surge_canonical_execution_bridge_status",
        "version": VERSION,
        "hook_applied": bool(hooked),
        "routes_entries_through_record_trade": bool(hooked),
        "authority": {
            "paper_execution_boundary_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_sizing": False,
            "changes_risk_limits": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
