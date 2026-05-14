"""JSON-safe, direct-persistence wrapper for the state-journal repair endpoint.

This patch intentionally bypasses the app/core save/load path for the repair route.
The prior apply path could report success while the persisted state file still showed
AAOI as open, because the repair was interacting with a stale or wrapped core state
object. This wrapper forces repair reads/writes to the mounted state.json file and
returns JSON-safe diagnostics instead of allowing a Flask 500.

2026-05-13 follow-up:
The repair can write the correct state.json, but a still-running/stale in-memory
app state can immediately save the old open-position view back over the repaired
file. This module now also wraps core.save_state. If an outgoing save would
reintroduce a state/journal full-exit mismatch while the persisted file is already
clean, the stale write is blocked and the core module is resynced from disk.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
from typing import Any, Dict

VERSION = "state-journal-apply-direct-persist-2026-05-13-memory-sync"
_PATCHED: set[int] = set()
_CORE_SAVE_PATCHED: set[int] = set()
_LAST_STALE_WRITE_BLOCK: Dict[str, Any] = {}


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
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
        try:
            folder_fd = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(folder_fd)
            finally:
                os.close(folder_fd)
        except Exception:
            pass
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


def _sync_core_state(core: Any | None, state: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort sync of app-level in-memory state after direct disk repair.

    app.py has historically kept runtime state in memory while also persisting to
    state.json. A direct file repair must update both surfaces or the next
    save_state/run_cycle can resurrect the stale position.
    """
    if core is None or not isinstance(state, dict):
        return {"synced": False, "reason": "core_or_state_missing"}
    synced_attrs = []
    candidate_attrs = (
        "STATE",
        "state",
        "PAPER_STATE",
        "paper_state",
        "ACCOUNT_STATE",
        "account_state",
        "BOT_STATE",
        "bot_state",
    )
    for attr in candidate_attrs:
        try:
            current = getattr(core, attr, None)
            if isinstance(current, dict):
                current.clear()
                current.update(copy.deepcopy(state))
                synced_attrs.append(attr)
        except Exception:
            continue
    # Some code paths may not expose a single named global. Keep a canonical
    # repaired copy available for diagnostics and future patches without forcing
    # app.py itself to know this module exists.
    try:
        setattr(core, "STATE_JOURNAL_REPAIRED_STATE", copy.deepcopy(state))
        setattr(core, "STATE_JOURNAL_REPAIRED_STATE_LOCAL", _now_text())
    except Exception:
        pass
    return {"synced": bool(synced_attrs), "synced_attrs": synced_attrs}


def _guard_for_state(guard_module: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        journal_file = getattr(guard_module, "TRADE_JOURNAL_FILE", "trade_journal.json")
        journal = _load_json_direct(str(journal_file))
        return guard_module.build_guard(state=state, journal=journal, core=None)
    except Exception as exc:
        return {"status": "error", "active": None, "error": repr(exc)}


def _install_core_stale_write_guard(core: Any | None, guard_module: Any, state_file: str) -> Dict[str, Any]:
    """Protect repaired state from stale in-memory overwrites.

    If the app tries to save a state that has an open-position/full-exit mismatch
    while the persisted state file is already clean, the save is stale. We block
    it and resync the core module from the clean file.
    """
    if core is None or not hasattr(core, "save_state"):
        return {"status": "not_applied", "reason": "core_save_state_missing", "version": VERSION}
    if id(core) in _CORE_SAVE_PATCHED:
        return {"status": "ok", "already_patched": True, "version": VERSION}

    original_save_state = getattr(core, "save_state")
    if not callable(original_save_state):
        return {"status": "not_applied", "reason": "core_save_state_not_callable", "version": VERSION}

    def protected_save_state(state: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        global _LAST_STALE_WRITE_BLOCK
        if isinstance(state, dict):
            candidate_guard = _guard_for_state(guard_module, state)
            disk_state = _load_json_direct(str(state_file))
            disk_guard = _guard_for_state(guard_module, disk_state)
            if bool(candidate_guard.get("active")) and not bool(disk_guard.get("active")):
                _LAST_STALE_WRITE_BLOCK = {
                    "status": "blocked",
                    "type": "state_journal_stale_write_guard",
                    "version": VERSION,
                    "generated_local": _now_text(),
                    "reason": "blocked_stale_in_memory_state_from_reintroducing_repaired_journal_mismatch",
                    "candidate_blocked_symbols": candidate_guard.get("blocked_symbols", []),
                    "disk_reconciliation_status": disk_guard.get("reconciliation_status"),
                    "state_file": str(state_file),
                    "core_sync": _sync_core_state(core, disk_state),
                }
                try:
                    setattr(core, "STATE_JOURNAL_LAST_STALE_WRITE_BLOCK", dict(_LAST_STALE_WRITE_BLOCK))
                except Exception:
                    pass
                return None
        return original_save_state(state, *args, **kwargs)

    try:
        protected_save_state._state_journal_stale_write_guard = True  # type: ignore[attr-defined]
        setattr(core, "save_state", protected_save_state)
        setattr(core, "STATE_JOURNAL_STALE_WRITE_GUARD_VERSION", VERSION)
        _CORE_SAVE_PATCHED.add(id(core))
        return {"status": "ok", "version": VERSION, "patched": True, "state_file": str(state_file)}
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": repr(exc)}


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

    stale_write_guard_status = _install_core_stale_write_guard(core, guard_module, str(state_file))

    # Force the repair module to persist directly to /data/state.json instead of
    # going through app/core wrappers that may hold a stale in-memory state object.
    def direct_load_state(active_core: Any | None = None) -> Dict[str, Any]:
        return _load_json_direct(str(state_file))

    def direct_save_state(state: Dict[str, Any], active_core: Any | None = None) -> Dict[str, Any]:
        safe_state = _json_safe(state)
        save_info = _atomic_write_json_direct(str(state_file), safe_state)
        save_info["core_sync"] = _sync_core_state(core, safe_state)
        return save_info

    try:
        guard_module._load_state = direct_load_state
        guard_module._save_state = direct_save_state
        guard_module.STATE_JOURNAL_DIRECT_PERSIST_PATCH_VERSION = VERSION
        guard_module.STATE_JOURNAL_STALE_WRITE_GUARD_STATUS = stale_write_guard_status
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
                result["stale_write_guard_status"] = stale_write_guard_status
                result["last_stale_write_block"] = dict(_LAST_STALE_WRITE_BLOCK)
                result["state_file"] = str(state_file)
            return _json_safe(result)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_repair",
                "version": getattr(guard_module, "REPAIR_VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "direct_persist_patch_active": True,
                "stale_write_guard_status": stale_write_guard_status,
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
                payload["stale_write_guard_status"] = stale_write_guard_status
                payload["last_stale_write_block"] = dict(_LAST_STALE_WRITE_BLOCK)
                payload["state_file"] = str(state_file)
            return _json_safe(payload)
        except Exception as exc:
            return {
                "status": "error",
                "type": "state_journal_reconciliation_guard",
                "version": getattr(guard_module, "VERSION", "unknown"),
                "jsonsafe_patch_version": VERSION,
                "direct_persist_patch_active": True,
                "stale_write_guard_status": stale_write_guard_status,
                "generated_local": _now_text(),
                "error": repr(exc),
            }

    guard_module.repair_state_from_journal = wrapped_repair_state_from_journal
    guard_module.status_payload = wrapped_status_payload
    guard_module.STATE_JOURNAL_JSONSAFE_PATCH_VERSION = VERSION
    _PATCHED.add(id(guard_module))
    return {
        "status": "ok",
        "version": VERSION,
        "patched": True,
        "state_file": str(state_file),
        "stale_write_guard_status": stale_write_guard_status,
    }
