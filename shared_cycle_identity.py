"""Authority-neutral shared cycle identity for paper observability.

Creates one immutable cycle_id at scanner invocation and propagates that identity
through transactional state records produced by the same runtime cycle. This module
adds metadata only. It does not alter scanner inputs/results, candidates, thresholds,
risk, sizing, orders, ML authority, or live authority.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import uuid
from typing import Any, Dict

VERSION = "shared-cycle-identity-2026-07-22-v1"
_REGISTERED_APP_IDS: set[int] = set()
_PATCHED_MODULE_IDS: set[int] = set()
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}

_TARGET_KEYS = (
    "scanner_audit",
    "decision_audit",
    "blocked_entry_reason_audit",
    "entry_pipeline_xray",
    "entry_journal",
    "post_harvest",
    "post_harvest_audit",
    "rotation_audit",
)


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_state"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_cycle_id() -> str:
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    return f"cycle-{stamp}-{uuid.uuid4().hex[:8]}"


def _active_cycle(core: Any) -> str | None:
    value = getattr(core, "CURRENT_CYCLE_ID", None)
    return str(value) if value else None


def _stamp_row(row: Any, cycle_id: str) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("cycle_id") is not None:
        return False
    row["cycle_id"] = cycle_id
    return True


def _stamp_state_delta(before: Dict[str, Any], after: Dict[str, Any], cycle_id: str) -> list[str]:
    stamped: list[str] = []
    for key in _TARGET_KEYS:
        current = after.get(key)
        if not isinstance(current, dict):
            continue
        previous = before.get(key)
        changed = current != previous
        if changed and _stamp_row(current, cycle_id):
            stamped.append(key)
        latest = current.get("latest_cycle")
        if changed and _stamp_row(latest, cycle_id):
            stamped.append(f"{key}.latest_cycle")
        last_cycle = current.get("last_cycle")
        if changed and _stamp_row(last_cycle, cycle_id):
            stamped.append(f"{key}.last_cycle")
    return stamped


def _patch_update_state(core: Any) -> bool:
    current = getattr(core, "update_state", None)
    if not callable(current):
        return False
    if getattr(current, "_shared_cycle_identity_version", None) == VERSION:
        return True
    original = current

    def wrapped_update_state(updater, *, source="unspecified", expected_revision=None):
        cycle_id = _active_cycle(core) or getattr(core, "LAST_CYCLE_ID", None)
        if not cycle_id:
            return original(updater, source=source, expected_revision=expected_revision)

        def stamped_updater(state):
            before = dict(state) if isinstance(state, dict) else {}
            working = dict(state) if isinstance(state, dict) else {}
            updated = updater(working)
            after = updated if isinstance(updated, dict) else working
            stamped = _stamp_state_delta(before, after, str(cycle_id))
            if stamped:
                with _LOCK:
                    _LAST["last_stamped_records"] = stamped
                    _LAST["last_stamp_source"] = source
                    _LAST["last_stamp_cycle_id"] = str(cycle_id)
                    _LAST["last_stamp_local"] = _now(core)
            return after

        return original(stamped_updater, source=source, expected_revision=expected_revision)

    wrapped_update_state._shared_cycle_identity_version = VERSION  # type: ignore[attr-defined]
    wrapped_update_state._shared_cycle_identity_original = original  # type: ignore[attr-defined]
    core.update_state = wrapped_update_state
    return True


def _patch_scan_signals(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current):
        return False
    if getattr(current, "_shared_cycle_identity_version", None) == VERSION:
        return True
    original = current

    def wrapped(*args, **kwargs):
        cycle_id = _new_cycle_id()
        started = _now(core)
        core.CURRENT_CYCLE_ID = cycle_id
        core.LAST_CYCLE_ID = cycle_id
        with _LOCK:
            _LAST.update({
                "cycle_id": cycle_id,
                "started_local": started,
                "status": "running",
                "scan_callable": getattr(original, "__qualname__", getattr(original, "__name__", str(original))),
            })
        try:
            result = original(*args, **kwargs)
            with _LOCK:
                _LAST["status"] = "completed"
                _LAST["completed_local"] = _now(core)
            return result
        except Exception as exc:
            with _LOCK:
                _LAST["status"] = "error"
                _LAST["completed_local"] = _now(core)
                _LAST["error_type"] = type(exc).__name__
                _LAST["error_message"] = str(exc)
            raise
        finally:
            core.CURRENT_CYCLE_ID = None

    wrapped._shared_cycle_identity_version = VERSION  # type: ignore[attr-defined]
    wrapped._shared_cycle_identity_original = original  # type: ignore[attr-defined]
    core.scan_signals = wrapped
    return True


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION}
    update_patched = _patch_update_state(core)
    scan_patched = _patch_scan_signals(core)
    _PATCHED_MODULE_IDS.add(id(core))
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "update_state_patched": update_patched,
        "scan_signals_patched_for_identity_only": scan_patched,
        "authority": _authority(),
    }


def _state_cycles(core: Any) -> Dict[str, Any]:
    try:
        state = core.load_state()
    except Exception:
        state = getattr(core, "portfolio", {})
    state = state if isinstance(state, dict) else {}
    out: Dict[str, Any] = {}
    for key in _TARGET_KEYS:
        row = state.get(key)
        if isinstance(row, dict):
            out[key] = row.get("cycle_id") or (row.get("latest_cycle") or {}).get("cycle_id") or (row.get("last_cycle") or {}).get("cycle_id")
    return out


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    cycles = _state_cycles(core) if core is not None else {}
    non_null = [str(value) for value in cycles.values() if value]
    aligned = len(non_null) >= 2 and len(set(non_null)) == 1
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "shared_cycle_identity",
        "version": VERSION,
        "current_cycle_id": _active_cycle(core) if core is not None else None,
        "last_cycle_id": getattr(core, "LAST_CYCLE_ID", None) if core is not None else None,
        "state_cycle_ids": cycles,
        "records_with_cycle_id": len(non_null),
        "same_cycle_alignment": aligned,
        "latest_runtime": dict(_LAST),
        "authority": _authority(),
        "next_gate": "Confirm decision and blocker audits receive the same cycle_id after a completed scanner/entry cycle.",
    }


def _authority() -> Dict[str, bool]:
    return {
        "alters_scan_arguments": False,
        "alters_scan_result": False,
        "changes_thresholds": False,
        "changes_risk_or_sizing": False,
        "places_orders": False,
        "changes_ml_authority": False,
        "changes_live_authority": False,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return install(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    path = "/paper/shared-cycle-identity-status"
    if path not in existing:
        flask_app.add_url_rule(path, "shared_cycle_identity_status", lambda: jsonify(status_payload(core or _mod())))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
