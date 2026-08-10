"""Expose paper-accounting integrity inside the existing daily integrity section."""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "paper-accounting-audit-bridge-2026-08-10-v2-economic-ledger"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_data_integrity_audit_overlay as audit
        import paper_accounting_integrity_guard as guard
        import paper_ledger_economic_integrity as economics
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(audit, "build_integrity_section", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "integrity_builder_missing"}
    if getattr(current, "_paper_accounting_audit_bridge", None) == VERSION:
        _APPLIED = True
        return status_payload()

    prior = getattr(current, "_paper_accounting_audit_bridge_prior", current)

    @functools.wraps(prior)
    def wrapped(runtime: Any = None):
        active = runtime or core
        section = prior(active)
        if not isinstance(section, dict):
            return section

        accounting = guard.status_payload(active)
        economic = economics.status_payload(active)
        section["paper_accounting_integrity"] = accounting
        section["paper_ledger_economic_integrity"] = economic

        reasons = list(section.get("reasons") or [])
        accounting_ok = accounting.get("overall") == "pass" and accounting.get("coverage_complete") is True
        economic_ok = economic.get("overall") == "pass" and economic.get("promotion_evidence_eligible") is True

        if not accounting_ok:
            if "paper_accounting_integrity_not_reconciled" not in reasons:
                reasons.insert(0, "paper_accounting_integrity_not_reconciled")
            section["status"] = "fail"

        if not economic_ok:
            if "paper_ledger_economic_integrity_failed" not in reasons:
                reasons.insert(0, "paper_ledger_economic_integrity_failed")
            section["status"] = "fail"

            forward = _d(section.get("forward_validation"))
            forward["promotion_evidence_eligible"] = False
            forward["promotion_block_reason"] = "paper_ledger_economic_integrity_failed"
            section["forward_validation"] = forward

            mae = _d(section.get("mae_mfe_integrity"))
            mae["promotion_evidence_eligible"] = False
            mae["promotion_block_reason"] = "paper_ledger_economic_integrity_failed"
            section["mae_mfe_integrity"] = mae

        section["reasons"] = reasons
        return section

    wrapped._paper_accounting_audit_bridge = VERSION  # type: ignore[attr-defined]
    wrapped._paper_accounting_audit_bridge_prior = prior  # type: ignore[attr-defined]
    audit.build_integrity_section = wrapped
    _APPLIED = True
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "paper_accounting_audit_bridge_status",
        "version": VERSION,
        "applied": _APPLIED,
        "authority": {
            "reporting_only": True,
            "places_orders": False,
            "changes_strategy": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
