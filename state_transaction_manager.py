"""Transactional state update API for the paper-trading runtime.

Adds core.update_state(updater, source=...) so modules can perform a locked
read-modify-write transaction instead of loading and later replacing the entire
state from a stale snapshot. Existing load_state/save_state behavior remains
available for compatibility.

This module changes persistence mechanics only. It does not alter trading,
risk, sizing, candidates, orders, or authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Callable, Dict

VERSION = "state-transaction-manager-2026-07-21-v1"
_PATCHED_MODULE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_LAST_TRANSACTION: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_state"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_file(core: Any, io: Any) -> str:
    try:
        return str(getattr(core, "STATE_FILE", None) or io.STATE_FILE)
    except Exception:
        return str(io.STATE_FILE)


def _revision(state: Dict[str, Any]) -> int:
    try:
        return int(state.get("_state_revision") or 0)
    except Exception:
        return 0


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST_TRANSACTION
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    if id(core) in _PATCHED_MODULE_IDS and callable(getattr(core, "update_state", None)):
        return {"status": "ok", "version": VERSION, "already_installed": True}

    try:
        import state_io_hardening as io
    except Exception as exc:
        return {"status": "pending", "version": VERSION, "reason": f"state_io_unavailable:{type(exc).__name__}:{exc}"}

    path = _state_file(core, io)

    def update_state(
        updater: Callable[[Dict[str, Any]], Dict[str, Any] | None],
        *,
        source: str = "unspecified",
        expected_revision: int | None = None,
    ) -> Dict[str, Any]:
        global _LAST_TRANSACTION
        if not callable(updater):
            raise TypeError("updater must be callable")

        with io._THREAD_LOCK:
            with io._FileLock(exclusive=True):
                try:
                    current = io._read_once(path) if os.path.exists(path) and io._size(path) > 0 else {}
                except Exception:
                    current = io.safe_load_json_file(path, default={}, allow_backups=True)
                if not isinstance(current, dict):
                    current = {}

                before_revision = _revision(current)
                if expected_revision is not None and int(expected_revision) != before_revision:
                    result = {
                        "status": "conflict",
                        "version": VERSION,
                        "source": source,
                        "expected_revision": int(expected_revision),
                        "actual_revision": before_revision,
                        "written": False,
                    }
                    _LAST_TRANSACTION = result
                    return result

                working = dict(current)
                updated = updater(working)
                next_state = updated if isinstance(updated, dict) else working
                if not isinstance(next_state, dict):
                    raise TypeError("updater must return a dict or None")

                if next_state == current:
                    result = {
                        "status": "ok",
                        "version": VERSION,
                        "source": source,
                        "revision": before_revision,
                        "written": False,
                        "no_change": True,
                    }
                    _LAST_TRANSACTION = result
                    return result

                next_revision = before_revision + 1
                next_state["_state_revision"] = next_revision
                next_state["_state_updated_local"] = _now()
                next_state["_state_update_source"] = source

                backup = io.backup_current_state()
                io.atomic_json_write(path, next_state)
                try:
                    core.portfolio = next_state
                except Exception:
                    pass

                result = {
                    "status": "ok",
                    "version": VERSION,
                    "source": source,
                    "previous_revision": before_revision,
                    "revision": next_revision,
                    "written": True,
                    "backup": backup,
                }
                _LAST_TRANSACTION = result
                return result

    update_state._state_transaction_manager_version = VERSION  # type: ignore[attr-defined]
    core.update_state = update_state
    core.STATE_TRANSACTION_MANAGER_VERSION = VERSION
    _PATCHED_MODULE_IDS.add(id(core))
    return {
        "status": "ok",
        "version": VERSION,
        "installed": True,
        "state_file": path,
        "authority_changed": False,
        "logic_changed": False,
    }


def inspect(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    state: Dict[str, Any] = {}
    if core is not None:
        try:
            loaded = core.load_state()
            state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            state = getattr(core, "portfolio", {}) if isinstance(getattr(core, "portfolio", {}), dict) else {}
    return {
        "status": "ok" if core is not None else "pending",
        "type": "state_transaction_manager_status",
        "version": VERSION,
        "installed": bool(core is not None and callable(getattr(core, "update_state", None))),
        "revision": _revision(state),
        "last_transaction": dict(_LAST_TRANSACTION),
        "transactional_read_modify_write": True,
        "optimistic_revision_check_supported": True,
        "authority_changed": False,
        "logic_changed": False,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return install(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return install(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return inspect(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-transaction-status" not in existing:
        flask_app.add_url_rule(
            "/paper/state-transaction-status",
            "state_transaction_status",
            lambda: jsonify(inspect(core or _mod())),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
