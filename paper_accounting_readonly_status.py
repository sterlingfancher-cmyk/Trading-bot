"""Read-only status shim for paper-accounting integrity diagnostics."""
from __future__ import annotations

from typing import Any, Dict

VERSION = "paper-accounting-readonly-status-2026-08-07-v1"
_APPLIED = False


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    import paper_accounting_integrity_guard as guard

    def read_only_status(runtime: Any = None) -> Dict[str, Any]:
        active = runtime or core
        if active is None:
            return {"status": "pending", "overall": "warn", "version": guard.VERSION, "reason": "runtime_missing"}
        pf = guard._portfolio(active)
        rebuilt = guard.reconstruct_from_ledger(pf, active)
        discrepancies = guard._discrepancies(pf, rebuilt)
        clean = bool(rebuilt.get("coverage_complete")) and not discrepancies
        return {
            "status": "ok" if clean else "warn",
            "overall": "pass" if clean else "warn",
            "type": "paper_accounting_integrity_status",
            "version": guard.VERSION,
            "generated_local": guard._now(active),
            "coverage_complete": bool(rebuilt.get("coverage_complete")),
            "repaired": False,
            "discrepancies": discrepancies,
            "discrepancy_count": len(discrepancies),
            "reconstructed": rebuilt,
            "status_read_is_observational": True,
            "authority": {
                "reporting_only": True,
                "places_orders": False,
                "changes_strategy": False,
                "changes_thresholds": False,
                "changes_sizing_rules": False,
                "changes_live_or_ml_authority": False,
            },
        }

    guard.status_payload = read_only_status
    _APPLIED = True
    return {"status": "ok", "overall": "pass", "version": VERSION, "applied": True}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
