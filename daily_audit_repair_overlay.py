"""Augment the curated daily audit with repaired lifecycle/persistence contracts."""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "daily-audit-repair-overlay-2026-08-04-v1"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _recalculate(payload: Dict[str, Any], module: Any) -> None:
    sections = _d(payload.get("sections"))
    statuses = [_d(sections.get(key)).get("status") for key in list(sections)[:10]]
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    payload["overall"] = overall
    sections["11_conclusion"] = {
        "status": overall,
        "pass_count": statuses.count("pass"),
        "warn_count": statuses.count("warn"),
        "fail_count": statuses.count("fail"),
        "checked_sections": len(statuses),
    }
    try:
        sections["12_next_action"] = module._next_action(sections)
    except Exception:
        pass


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_operational_audit as daily
        import cycle_completion_contract as cycle
        import state_persistence_contract as persistence
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(daily, "build_payload", None)
    if not callable(current):
        return {"status": "error", "version": VERSION, "error": "daily_build_payload_missing"}
    if getattr(current, "_daily_audit_repair_overlay", False):
        _APPLIED = True
        return status_payload(core)

    @functools.wraps(current)
    def wrapped_build_payload(runtime: Any = None):
        active_core = runtime or core
        payload = current(active_core)
        if not isinstance(payload, dict):
            return payload
        sections = _d(payload.get("sections"))

        cycle_row = cycle.status_payload(active_core)
        runner = _d(sections.get("02_auto_runner_liveness"))
        runner["cycle_contract"] = cycle_row
        reasons = [str(item) for item in runner.get("reasons", []) if item]
        in_progress = bool(cycle_row.get("cycle_in_progress"))
        stale = bool(cycle_row.get("cycle_stale"))
        if in_progress and not stale:
            reasons = [item for item in reasons if item != "latest_completed_cycle_missing"]
            runner["status"] = "pass" if not reasons else "warn"
        elif stale:
            if "cycle_stale_in_progress" not in reasons:
                reasons.insert(0, "cycle_stale_in_progress")
            runner["status"] = "fail"
        elif cycle_row.get("last_completed_cycle_local"):
            reasons = [item for item in reasons if item != "latest_completed_cycle_missing"]
            runner["status"] = "pass" if not reasons else "warn"
        runner["reasons"] = reasons
        runner["current_cycle_phase"] = cycle_row.get("cycle_phase")
        runner["current_cycle_age_seconds"] = cycle_row.get("cycle_age_seconds")
        runner["last_completed_cycle_contract"] = cycle_row.get("last_completed_cycle_local")
        runner["last_completed_cycle_duration_seconds"] = cycle_row.get("last_completed_cycle_duration_seconds")

        state_row = persistence.status_payload(active_core)
        state = _d(sections.get("09_state_persistence_backup_recovery"))
        state["persistence_contract"] = state_row
        state["persistent_mount_detected"] = state_row.get("persistent_mount_detected")
        state["migration"] = state_row.get("migration")
        state["reloaded_richer_persistent_state"] = state_row.get("reloaded_richer_persistent_state")
        state_reasons = [str(item) for item in state.get("reasons", []) if item]
        if state_row.get("persistent_mount_detected"):
            state_reasons = [item for item in state_reasons if item != "persistent_volume_not_configured"]
            if state_row.get("backup_exists"):
                state_reasons = [item for item in state_reasons if item != "state_backup_not_observed"]
            state["status"] = "pass" if not state_reasons else "warn"
        else:
            if "persistent_volume_not_configured" not in state_reasons:
                state_reasons.insert(0, "persistent_volume_not_configured")
            state["status"] = "warn"
        state["reasons"] = state_reasons

        payload["repair_overlay_version"] = VERSION
        _recalculate(payload, daily)
        return payload

    wrapped_build_payload._daily_audit_repair_overlay = True  # type: ignore[attr-defined]
    daily.build_payload = wrapped_build_payload
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "daily_audit_repair_overlay",
        "version": VERSION,
        "applied": _APPLIED,
        "authority": {
            "classification_and_reporting_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/daily-audit-repair-overlay-status" not in existing:
        flask_app.add_url_rule(
            "/paper/daily-audit-repair-overlay-status",
            "daily_audit_repair_overlay_status",
            lambda: jsonify(status_payload(core)),
        )
    apply(core)
