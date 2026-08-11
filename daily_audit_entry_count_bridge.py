"""Reporting-only bridge for the compact Stable Paper daily audit.

The scanner section can omit ``entries_count`` even when the latest auto-runner
cycle persisted an ``entries`` list.  This bridge fills only that missing report
field from ``portfolio.auto_runner.last_result.entries`` and clears the obsolete
``entry_count_missing`` next-action when the fallback is available.

It does not alter scanner decisions, signals, execution, sizing, risk controls,
strategy thresholds, live authority, or ML authority.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "daily-audit-entry-count-bridge-2026-08-11-v1"
_REGISTERED: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _portfolio(core: Any) -> Dict[str, Any]:
    state = getattr(core, "portfolio", None) if core is not None else None
    return state if isinstance(state, dict) else {}


def _latest_cycle_entry_count(core: Any) -> int | None:
    state = _portfolio(core)
    auto = _d(state.get("auto_runner"))
    last = _d(auto.get("last_result"))
    entries = last.get("entries")
    if isinstance(entries, list):
        return len(entries)
    return None


def patch_payload(payload: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    sections = _d(payload.get("sections"))
    scanner = _d(sections.get("05_scanner_signals_entries_rejections"))
    if scanner.get("entries_count") is not None:
        return payload

    fallback = _latest_cycle_entry_count(core)
    if fallback is None:
        return payload

    scanner["entries_count"] = fallback
    scanner["entries_count_source"] = "auto_runner.last_result.entries"
    sections["05_scanner_signals_entries_rejections"] = scanner

    next_action = _d(sections.get("12_next_action"))
    if next_action.get("reason") == "entry_count_missing":
        next_action.update({
            "status": "ok",
            "priority": "normal",
            "reason": "latest_cycle_entry_count_available",
            "action": "Continue normal Stable Paper validation; latest-cycle entry count is available from the auto-runner result.",
        })
        sections["12_next_action"] = next_action

    payload["sections"] = sections
    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "reporting_only": True,
        "latest_cycle_entry_count": _latest_cycle_entry_count(core),
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "warn", "overall": "warn", "version": VERSION}
    app_id = id(flask_app)
    if app_id not in _REGISTERED:
        from flask import request

        @flask_app.after_request
        def _fill_missing_entry_count(response):
            try:
                if request.path != "/paper/daily-audit" or request.args.get("full") == "1":
                    return response
                payload = response.get_json(silent=True)
                if not isinstance(payload, dict):
                    return response
                patched = patch_payload(payload, core)
                response.set_data(flask_app.json.dumps(patched))
                response.content_type = "application/json"
                response.content_length = len(response.get_data())
            except Exception:
                return response
            return response

        _REGISTERED.add(app_id)
    return apply(core)
