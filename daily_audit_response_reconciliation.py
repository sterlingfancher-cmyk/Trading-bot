"""Final read-only reconciliation for daily-audit HTTP responses.

Wrapper installation order can change during deferred startup. This guard runs
at the Flask response boundary so both compact and full daily-audit payloads
retain the 11-operational-check contract after every reporting overlay.

It changes no strategy, thresholds, sizing, risk controls, orders, provider
behavior, live authority, or ML authority.
"""
from __future__ import annotations

import json
from typing import Any, Dict

VERSION = "daily-audit-response-reconciliation-2026-08-06-v1"
_APPLIED = False
_REGISTERED_APP_IDS: set[int] = set()
_VALID = {"pass", "warn", "fail"}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _i(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _overall(pass_count: int, warn_count: int, fail_count: int) -> str:
    if fail_count:
        return "fail"
    if warn_count:
        return "warn"
    return "pass"


def _reconcile_full(payload: Dict[str, Any]) -> Dict[str, Any]:
    sections = _d(payload.get("sections"))
    operational_keys = [
        key for key in sections if key not in {"11_conclusion", "12_next_action"}
    ]
    if not operational_keys:
        return payload

    statuses = []
    for key in operational_keys:
        status = str(_d(sections.get(key)).get("status") or "").lower()
        statuses.append(status if status in _VALID else "warn")

    pass_count = statuses.count("pass")
    warn_count = statuses.count("warn")
    fail_count = statuses.count("fail")
    overall = _overall(pass_count, warn_count, fail_count)
    sections["11_conclusion"] = {
        "status": overall,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "checked_sections": len(operational_keys),
    }
    payload["overall"] = overall
    payload["daily_audit_response_reconciliation_version"] = VERSION
    return payload


def _reconcile_compact(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = _d(payload.get("section_summary"))
    if not summary:
        return payload

    pass_count = _i(summary.get("pass"))
    warn_count = _i(summary.get("warn"))
    fail_count = _i(summary.get("fail"))
    classified = pass_count + warn_count + fail_count
    integrity_status = str(
        _d(payload.get("data_integrity")).get("status") or ""
    ).lower()

    # The legacy repair layer counted the ten pre-integrity sections. Add the
    # integrity result exactly once when that legacy count reaches the response.
    if classified == 10 and integrity_status in _VALID:
        if integrity_status == "pass":
            pass_count += 1
        elif integrity_status == "warn":
            warn_count += 1
        else:
            fail_count += 1
        classified += 1

    summary.update(
        {
            "checked": classified,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
        }
    )
    payload["overall"] = _overall(pass_count, warn_count, fail_count)
    payload["daily_audit_response_reconciliation_version"] = VERSION
    return payload


def reconcile_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    payload_type = str(payload.get("type") or "")
    if payload_type == "daily_operational_audit":
        return _reconcile_full(payload)
    if payload_type == "daily_operational_audit_compact":
        return _reconcile_compact(payload)
    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "daily_audit_response_reconciliation_status",
        "version": VERSION,
        "applied": _APPLIED,
        "registered_app_count": len(_REGISTERED_APP_IDS),
        "authority": {
            "reporting_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_provider_behavior": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if id(flask_app) in _REGISTERED_APP_IDS:
        _APPLIED = True
        return status_payload()

    from flask import request

    @flask_app.after_request
    def daily_audit_response_reconciliation(response):
        try:
            if (
                request.path == "/paper/daily-audit"
                and response.status_code < 400
                and response.is_json
            ):
                payload = response.get_json(silent=True)
                reconciled = reconcile_payload(payload)
                if isinstance(reconciled, dict):
                    response.set_data(
                        json.dumps(
                            reconciled,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        )
                    )
                    response.mimetype = "application/json"
        except Exception:
            # Never turn a successful read-only audit into an HTTP failure.
            pass
        return response

    _REGISTERED_APP_IDS.add(id(flask_app))
    _APPLIED = True
    return status_payload()
