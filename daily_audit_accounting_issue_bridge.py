"""Reporting-only bridge that exposes the first accounting integrity defect.

Stable Paper normally keeps /paper/daily-audit compact. During an integrity
failure, counts alone are insufficient to identify the exact persisted execution
row. This bridge augments the compact payload with the first coverage issue,
first economic issue, and reconstructed open-position symbols.

No state repair, execution, strategy, sizing, risk, live, or ML authority is
changed.
"""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "daily-audit-accounting-issue-bridge-2026-08-11-v1"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _first_safe(value: Any) -> Any:
    rows = _l(value)
    return rows[0] if rows else None


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import final_daily_audit_compactor as compactor
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(compactor, "compact_payload", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "compact_payload_missing"}

    if getattr(current, "_accounting_issue_bridge_version", None) == VERSION:
        _APPLIED = True
        return status_payload()

    prior = getattr(current, "_accounting_issue_bridge_prior", current)

    @functools.wraps(prior)
    def wrapped(payload: Dict[str, Any], runtime_core: Any = None) -> Dict[str, Any]:
        out = prior(payload, runtime_core)
        if not isinstance(out, dict):
            return out

        sections = _d(payload.get("sections"))
        integrity = _d(sections.get("10b_market_data_and_path_integrity"))
        accounting = _d(integrity.get("paper_accounting_integrity"))
        rebuilt = _d(accounting.get("reconstructed"))
        economics = _d(integrity.get("paper_ledger_economic_integrity"))

        target = _d(out.get("accounting_integrity"))
        target["first_coverage_issue"] = _first_safe(rebuilt.get("coverage_issues"))
        target["first_economic_issue"] = _first_safe(
            economics.get("economic_issues") or rebuilt.get("economic_issues")
        )
        target["reconstructed_open_positions"] = sorted(
            str(symbol) for symbol in _d(rebuilt.get("open_positions")).keys()
        )
        target["parsed_trade_rows"] = rebuilt.get("parsed_trade_rows")
        out["accounting_integrity"] = target
        return out

    wrapped._accounting_issue_bridge_version = VERSION  # type: ignore[attr-defined]
    wrapped._accounting_issue_bridge_prior = prior  # type: ignore[attr-defined]
    compactor.compact_payload = wrapped
    _APPLIED = True
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "reporting_only": True,
        "surfaces_first_coverage_issue": True,
        "surfaces_first_economic_issue": True,
        "surfaces_reconstructed_open_positions": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
