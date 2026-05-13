"""JSON-safe wrapper for the state-journal repair endpoint."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict

VERSION = "state-journal-apply-jsonsafe-2026-05-13"
_PATCHED: set[int] = set()


def _now_text() -> str:
    try:
        import os
        import pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_safe(obj: Any) -> Dict[str, Any]:
    try:
        safe = json.loads(json.dumps(obj, default=str, allow_nan=False))
        return safe if isinstance(safe, dict) else {"status": "ok", "value": safe}
    except Exception as exc:
        return {
            "status": "error",
            "type": "state_journal_repair",
            "jsonsafe_patch_version": VERSION,
            "generated_local": _now_text(),
            "message": "Repair returned data that could not be serialized safely.",
            "json_safety_error": repr(exc),
            "raw_type": str(type(obj)),
            "raw_preview": repr(obj)[:1500],
        }


def apply(guard_module: Any, core: Any | None = None) -> Dict[str, Any]:
    if guard_module is None:
        return {"status": "error", "version": VERSION, "error": "guard_module_missing"}
    if id(guard_module) in _PATCHED:
        return {"status": "ok", "version": VERSION, "already_patched": True}

    original_repair = getattr(guard_module, "repair_state_from_journal", None)
    original_status = getattr(guard_module, "status_payload", None)
    if not callable(original_repair):
        return {"status": "error", "version": VERSION, "error": "repair_function_missing"}

    def wrapped_repair_state_from_journal(apply: bool = False, core: Any | None = None) -> Dict[str, Any]:
        try:
            result = original_repair(apply=apply, core=core)
            if isinstance(result, dict):
                result["jsonsafe_patch_version"] = VERSION
            return _json_safe(result)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_repair",
                "version": getattr(guard_module, "REPAIR_VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "generated_local": _now_text(),
                "apply": bool(apply),
                "error": repr(exc),
                "message": "Repair failed inside the wrapped apply path. Do not assume state changed unless the response says it was saved and verified.",
            }

    def wrapped_status_payload(core: Any | None = None) -> Dict[str, Any]:
        try:
            payload = original_status(core=core) if callable(original_status) else guard_module.build_guard(core=core)
            if isinstance(payload, dict):
                payload["jsonsafe_patch_version"] = VERSION
            return _json_safe(payload)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_reconciliation_guard",
                "version": getattr(guard_module, "VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "generated_local": _now_text(),
                "error": repr(exc),
            }

    guard_module.repair_state_from_journal = wrapped_repair_state_from_journal
    guard_module.status_payload = wrapped_status_payload
    guard_module.STATE_JOURNAL_JSONSAFE_PATCH_VERSION = VERSION
    _PATCHED.add(id(guard_module))
    return {"status": "ok", "version": VERSION, "patched": True}
