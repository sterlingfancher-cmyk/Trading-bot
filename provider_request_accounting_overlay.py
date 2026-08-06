"""Read-only accounting overlay for market-data provider request totals.

The provider-health counters can be sampled while another request is in flight.
This overlay makes that gap explicit instead of leaving operators to infer it
from totals. It does not call providers, change retries/backoff, alter strategy,
change risk or sizing, place orders, or change live/ML authority.
"""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "provider-request-accounting-overlay-2026-08-06-v1"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _i(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def accounting_payload(totals: Any) -> Dict[str, Any]:
    row = dict(_d(totals))
    requests = _i(row.get("requests"))
    # `timeouts` is treated as a failure subtype and therefore is not added a
    # second time. The other counters represent terminal or intentionally
    # skipped request outcomes.
    classified = sum(
        _i(row.get(key))
        for key in (
            "successes",
            "failures",
            "empty",
            "hygiene_blocked",
            "provider_circuit_skips",
            "symbol_backoff_skips",
        )
    )
    gap = max(0, requests - classified)
    return {
        "requests": requests,
        "classified_terminal_outcomes": classified,
        "in_flight_or_unclassified_requests": gap,
        "accounting_complete_at_snapshot": gap == 0,
        "timeouts_reported_separately": _i(row.get("timeouts")),
        "interpretation": (
            "A small positive gap can be a request that was in flight when the read-only status snapshot was taken."
        ),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_data_integrity_audit_overlay as audit_overlay
    except Exception as exc:
        return {
            "status": "error",
            "version": VERSION,
            "error": f"{type(exc).__name__}: {exc}",
        }

    current = getattr(audit_overlay, "build_integrity_section", None)
    if not callable(current):
        return {"status": "error", "version": VERSION, "error": "integrity_builder_missing"}
    if getattr(current, "_provider_request_accounting_overlay", None) == VERSION:
        _APPLIED = True
        return status_payload()

    @functools.wraps(current)
    def wrapped_build_integrity_section(runtime: Any = None):
        section = current(runtime)
        if not isinstance(section, dict):
            return section
        accounting = accounting_payload(section.get("provider_totals"))
        section["provider_request_accounting"] = accounting
        totals = dict(_d(section.get("provider_totals")))
        totals.update(
            {
                "classified_terminal_outcomes": accounting["classified_terminal_outcomes"],
                "in_flight_or_unclassified_requests": accounting["in_flight_or_unclassified_requests"],
                "accounting_complete_at_snapshot": accounting["accounting_complete_at_snapshot"],
            }
        )
        section["provider_totals"] = totals
        return section

    wrapped_build_integrity_section._provider_request_accounting_overlay = VERSION  # type: ignore[attr-defined]
    audit_overlay.build_integrity_section = wrapped_build_integrity_section
    _APPLIED = True
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "provider_request_accounting_overlay_status",
        "version": VERSION,
        "applied": _APPLIED,
        "authority": {
            "reporting_only": True,
            "changes_provider_behavior": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    # No additional route is needed; this enriches the existing daily audit and
    # data-integrity status surfaces.
    return apply(core)


try:
    apply(None)
except Exception:
    pass
