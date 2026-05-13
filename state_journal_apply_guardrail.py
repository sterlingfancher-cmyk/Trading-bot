"""JSON-safe, direct-persistence wrapper for the state-journal repair endpoint.

This patch intentionally bypasses the app/core save/load path for the repair route.
The prior apply path could report success while the persisted state file still showed
AAOI as open, because the repair was interacting with a stale or wrapped core state
object. This wrapper forces repair reads/writes to the mounted state.json file and
returns JSON-safe diagnostics instead of allowing a Flask 500.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from typing import Any, Dict

VERSION = "state-journal-apply-direct-persist-2026-05-13"
_PATCHED: set[int] = set()


def _now_text() -> str:
    try:
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


def _load_json_direct(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _atomic_write_json_direct(path: str, obj: Dict[str, Any]) -> Dict[str, Any]:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state_journal_direct_persist_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True, default=str, allow_nan=False)
            f.write("\n")
        os.replace(tmp, path)
        return {
            "saved_by": "direct_atomic_write_jsonsafe",
            "state_file": path,
            "jsonsafe_patch_version": VERSION,
            "size_bytes": os.path.getsize(path) if os.path.exists(path) else None,
        }
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def apply(guard_module: Any, core: Any | None = None) -> Dict[str, Any]:
    if guard_module is None:
        return {"status": "error", "version": VERSION, "error": "guard_module_missing"}
    if id(guard_module) in _PATCHED:
        return {"status": "ok", "version": VERSION, "already_patched": True}

    original_repair = getattr(guard_module, "repair_state_from_journal", None)
    original_status = getattr(guard_module, "status_payload", None)
    original_build_guard = getattr(guard_module, "build_guard", None)
    if not callable(original_repair):
        return {"status": "error", "version": VERSION, "error": "repair_function_missing"}

    state_file = getattr(guard_module, "STATE_FILE", None)
    if not state_file:
        return {"status": "error", "version": VERSION, "error": "state_file_missing"}

    # Force the repair module to persist directly to /data/state.json instead of
    # going through app/core wrappers that may hold a stale in-memory state object.
    def direct_load_state(active_core: Any | None = None) -> Dict[str, Any]:
        return _load_json_direct(str(state_file))

    def direct_save_state(state: Dict[str, Any], active_core: Any | None = None) -> Dict[str, Any]:
        safe_state = _json_safe(state)
        return _atomic_write_json_direct(str(state_file), safe_state)

    try:
        guard_module._load_state = direct_load_state
        guard_module._save_state = direct_save_state
        guard_module.STATE_JOURNAL_DIRECT_PERSIST_PATCH_VERSION = VERSION
    except Exception:
        pass

    def call_original_repair(apply_flag: bool) -> Any:
        # Always pass core=None so repair/post-repair verification reloads the
        # persisted file, not a potentially stale app module state.
        try:
            return original_repair(apply=apply_flag, core=None)
        except TypeError as exc:
            text = str(exc)
            if "unexpected keyword argument 'core'" in text:
                try:
                    return original_repair(apply=apply_flag)
                except TypeError:
                    return original_repair(apply_flag)
            if "unexpected keyword argument 'apply'" in text:
                return original_repair(apply_flag)
            raise

    def call_original_status() -> Any:
        if callable(original_status):
            try:
                return original_status(core=None)
            except TypeError:
                return original_status()
        if callable(original_build_guard):
            try:
                return original_build_guard(core=None)
            except TypeError:
                return original_build_guard()
        return {"status": "error", "error": "status_function_missing"}

    def wrapped_repair_state_from_journal(apply: bool = False, core: Any | None = None) -> Dict[str, Any]:
        try:
            result = call_original_repair(bool(apply))
            if isinstance(result, dict):
                result["jsonsafe_patch_version"] = VERSION
                result["direct_persist_patch_active"] = True
                result["state_file"] = str(state_file)
            return _json_safe(result)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_repair",
                "version": getattr(guard_module, "REPAIR_VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "direct_persist_patch_active": True,
                "generated_local": _now_text(),
                "apply": bool(apply),
                "error": repr(exc),
                "message": "Repair failed inside the direct-persistence apply path. No successful repair should be assumed unless post_repair_guard reports active=false.",
            }

    def wrapped_status_payload(core: Any | None = None) -> Dict[str, Any]:
        try:
            payload = call_original_status()
            if isinstance(payload, dict):
                payload["jsonsafe_patch_version"] = VERSION
                payload["direct_persist_patch_active"] = True
                payload["state_file"] = str(state_file)
            return _json_safe(payload)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_reconciliation_guard",
                "version": getattr(guard_module, "VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "direct_persist_patch_active": True,
                "generated_local": _now_text(),
                "error": repr(exc),
            }

    guard_module.repair_state_from_journal = wrapped_repair_state_from_journal
    guard_module.status_payload = wrapped_status_payload
    guard_module.STATE_JOURNAL_JSONSAFE_PATCH_VERSION = VERSION
    _PATCHED.add(id(guard_module))
    return {"status": "ok", "version": VERSION, "patched": True, "state_file": str(state_file)}
