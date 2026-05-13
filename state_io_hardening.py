"""State I/O hardening for Railway paper-trading runtime.

This module patches the trading app at WSGI startup so worker timeouts cannot
leave /data/state.json half-written and so diagnostic layers do not crash when a
state read happens during a write/replace window.

Primary protections:
- atomic state writes: write state.json.tmp, fsync, os.replace
- latest/largest backups before replace
- thread + file locks around state reads/writes
- tolerant JSON reads with short retries and backup fallback
- non-overlapping run_cycle guard for manual /paper/run and auto runner safety
- lightweight /paper/state-io-status diagnostic route
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from typing import Any, Dict, Optional

VERSION = "state-io-hardening-2026-05-13"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
STATE_LOCK_FILE = os.path.join(STATE_DIR or ".", ".state_io.lock")
STATE_BACKUP_LATEST = os.path.join(STATE_DIR or ".", "state_backup_latest.json")
STATE_BACKUP_LARGEST = os.path.join(STATE_DIR or ".", "state_backup_largest.json")
STATE_BACKUP_PREWRITE = os.path.join(STATE_DIR or ".", "state_backup_prewrite.json")
STATE_IO_STATUS_FILE = os.path.join(STATE_DIR or ".", "state_io_status.json")

READ_RETRIES = int(os.environ.get("STATE_IO_READ_RETRIES", "4"))
READ_RETRY_SLEEP = float(os.environ.get("STATE_IO_READ_RETRY_SLEEP", "0.05"))

_THREAD_LOCK = threading.RLock()
_RUN_LOCK = threading.Lock()
_RUN_STATE: Dict[str, Any] = {
    "active": False,
    "started_ts": None,
    "started_local": None,
    "last_finished_ts": None,
    "last_finished_local": None,
    "last_runtime_seconds": None,
    "overlap_blocks": 0,
    "last_error": None,
}
_PATCHED_MODULE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_LAST_STATUS: Dict[str, Any] = {}

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _folder(path: str) -> str:
    return os.path.dirname(os.path.abspath(path)) or "."


def _ensure_parent(path: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def _json_default(obj: Any) -> str:
    try:
        return obj.isoformat()
    except Exception:
        return str(obj)


class _FileLock:
    def __init__(self, exclusive: bool):
        self.exclusive = exclusive
        self.handle = None

    def __enter__(self):
        _ensure_parent(STATE_LOCK_FILE)
        self.handle = open(STATE_LOCK_FILE, "a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH)
        return self.handle

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.handle is not None and fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                if self.handle is not None:
                    self.handle.close()
            except Exception:
                pass
        return False


def _quality(obj: Any) -> Dict[str, Any]:
    state = obj if isinstance(obj, dict) else {}
    trades = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    recent = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    history = state.get("history", []) if isinstance(state.get("history"), list) else []
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    reports = state.get("reports", {}) if isinstance(state.get("reports"), dict) else {}
    has_account = any(k in state for k in ("cash", "equity", "peak", "performance", "realized_pnl"))
    valid = bool(has_account or trades or recent or history or positions or reports or state.get("scanner_audit"))
    score = 0
    score += 3 if has_account else 0
    score += min(len(trades) + len(recent), 20)
    score += min(len(history), 50) // 10
    score += 2 if reports else 0
    score += 2 if positions else 0
    return {
        "valid": valid,
        "score": score,
        "trades_count": len(trades),
        "recent_trades_count": len(recent),
        "history_count": len(history),
        "positions_count": len(positions),
        "reports_present": bool(reports),
        "has_account_fields": bool(has_account),
    }


def _read_once(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}


def safe_load_json_file(path: str, default: Optional[Dict[str, Any]] = None, *, allow_backups: bool = True) -> Dict[str, Any]:
    default = default if isinstance(default, dict) else {}
    candidates = [path]
    if allow_backups and os.path.basename(path) == os.path.basename(STATE_FILE):
        candidates += [STATE_BACKUP_LATEST, STATE_BACKUP_LARGEST, STATE_BACKUP_PREWRITE]

    last_error = None
    with _THREAD_LOCK:
        with _FileLock(exclusive=False):
            for candidate in candidates:
                if not candidate or not os.path.exists(candidate) or _size(candidate) <= 0:
                    continue
                attempts = READ_RETRIES if candidate == path else 1
                for attempt in range(max(1, attempts)):
                    try:
                        data = _read_once(candidate)
                        if isinstance(data, dict):
                            if candidate != path:
                                _record_status("backup_read", {"source": candidate, "target": path})
                            return data
                    except Exception as exc:
                        last_error = repr(exc)
                        if attempt + 1 < attempts:
                            time.sleep(READ_RETRY_SLEEP)
            _record_status("read_failed", {"path": path, "last_error": last_error})
            return dict(default)


def _copy_if_valid(src: str, dst: str) -> bool:
    try:
        if not os.path.exists(src) or _size(src) <= 0:
            return False
        data = _read_once(src)
        if not _quality(data).get("valid"):
            return False
        _ensure_parent(dst)
        tmp = dst + ".tmp"
        with open(src, "rb") as r, open(tmp, "wb") as w:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                w.write(chunk)
            w.flush()
            os.fsync(w.fileno())
        os.replace(tmp, dst)
        return True
    except Exception:
        return False


def backup_current_state() -> Dict[str, Any]:
    with _THREAD_LOCK:
        latest = _copy_if_valid(STATE_FILE, STATE_BACKUP_LATEST)
        prewrite = _copy_if_valid(STATE_FILE, STATE_BACKUP_PREWRITE)
        largest = False
        try:
            if latest and _size(STATE_FILE) >= _size(STATE_BACKUP_LARGEST):
                largest = _copy_if_valid(STATE_FILE, STATE_BACKUP_LARGEST)
        except Exception:
            largest = False
        return {
            "latest_backup_written": bool(latest),
            "prewrite_backup_written": bool(prewrite),
            "largest_backup_written": bool(largest),
            "state_size_bytes": _size(STATE_FILE),
            "latest_backup_size_bytes": _size(STATE_BACKUP_LATEST),
            "largest_backup_size_bytes": _size(STATE_BACKUP_LARGEST),
        }


def atomic_json_write(path: str, payload: Dict[str, Any]) -> bool:
    _ensure_parent(path)
    folder = _folder(path)
    base = os.path.basename(path)
    tmp = os.path.join(folder, f".{base}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=_json_default, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        dir_fd = os.open(folder, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        pass
    return True


def _state_file_for_module(module: Any) -> str:
    try:
        return str(getattr(module, "STATE_FILE", STATE_FILE) or STATE_FILE)
    except Exception:
        return STATE_FILE


def _compact_status(module: Any) -> Dict[str, Any]:
    try:
        if hasattr(module, "compact_status_snapshot"):
            out = module.compact_status_snapshot(include_last_result=True)
            return out if isinstance(out, dict) else {"status": "ok", "snapshot": out}
    except Exception:
        pass
    state = safe_load_json_file(_state_file_for_module(module))
    return {
        "status": "ok",
        "source": "state_io_hardening_compact_fallback",
        "cash": state.get("cash"),
        "equity": state.get("equity"),
        "positions": list((state.get("positions") or {}).keys()) if isinstance(state.get("positions"), dict) else [],
        "performance": state.get("performance", {}),
        "risk_controls": state.get("risk_controls", {}),
    }


def _record_status(event: str, extra: Optional[Dict[str, Any]] = None) -> None:
    global _LAST_STATUS
    payload = {
        "status": "ok",
        "type": "state_io_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "event": event,
        "state_file": STATE_FILE,
        "state_size_bytes": _size(STATE_FILE),
        "state_backup_latest": STATE_BACKUP_LATEST,
        "state_backup_latest_size_bytes": _size(STATE_BACKUP_LATEST),
        "state_backup_largest": STATE_BACKUP_LARGEST,
        "state_backup_largest_size_bytes": _size(STATE_BACKUP_LARGEST),
        "run_state": dict(_RUN_STATE),
    }
    if extra:
        payload.update(extra)
    _LAST_STATUS = payload
    try:
        _ensure_parent(STATE_IO_STATUS_FILE)
        tmp = STATE_IO_STATUS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, default=_json_default)
        os.replace(tmp, STATE_IO_STATUS_FILE)
    except Exception:
        pass


def status_payload(module: Any | None = None) -> Dict[str, Any]:
    state_path = _state_file_for_module(module) if module is not None else STATE_FILE
    state = safe_load_json_file(state_path)
    return {
        "status": "ok",
        "type": "state_io_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "installed": bool(module is not None and id(module) in _PATCHED_MODULE_IDS),
        "state_file": state_path,
        "state_size_bytes": _size(state_path),
        "state_quality": _quality(state),
        "backups": {
            "latest": STATE_BACKUP_LATEST,
            "latest_size_bytes": _size(STATE_BACKUP_LATEST),
            "largest": STATE_BACKUP_LARGEST,
            "largest_size_bytes": _size(STATE_BACKUP_LARGEST),
            "prewrite": STATE_BACKUP_PREWRITE,
            "prewrite_size_bytes": _size(STATE_BACKUP_PREWRITE),
        },
        "protections": {
            "atomic_save_state": True,
            "retrying_json_reads": True,
            "backup_fallback_reads": True,
            "thread_and_file_locking": True,
            "non_overlapping_run_cycle": True,
        },
        "run_state": dict(_RUN_STATE),
        "last_status_event": _LAST_STATUS.get("event"),
    }


def patch_json_modules(*modules: Any) -> None:
    for module in modules:
        if module is None:
            continue
        try:
            if hasattr(module, "_load_json") and not getattr(module._load_json, "_state_io_hardened", False):
                def _hardened_load_json(path: str, __module=module):
                    return safe_load_json_file(path, default={})
                _hardened_load_json._state_io_hardened = True  # type: ignore[attr-defined]
                module._load_json = _hardened_load_json
        except Exception:
            pass
        try:
            if hasattr(module, "_load_json_file") and not getattr(module._load_json_file, "_state_io_hardened", False):
                def _hardened_load_json_file(path: str, __module=module):
                    return safe_load_json_file(path, default={})
                _hardened_load_json_file._state_io_hardened = True  # type: ignore[attr-defined]
                module._load_json_file = _hardened_load_json_file
        except Exception:
            pass


def install(module: Any) -> Dict[str, Any]:
    if module is None:
        return {"status": "not_applied", "reason": "module_missing", "version": VERSION}
    if id(module) in _PATCHED_MODULE_IDS:
        return {"status": "ok", "already_installed": True, "version": VERSION}

    state_file = _state_file_for_module(module)
    original_load_state = getattr(module, "load_state", None)
    original_save_state = getattr(module, "save_state", None)
    original_run_cycle = getattr(module, "run_cycle", None)

    def hardened_load_state(*args, **kwargs):
        if callable(original_load_state):
            try:
                return original_load_state(*args, **kwargs)
            except Exception as exc:
                _record_status("original_load_state_failed", {"error": repr(exc)})
        return safe_load_json_file(state_file, default={})

    def hardened_save_state(state, *args, **kwargs):
        if not isinstance(state, dict):
            state = dict(state or {}) if state is not None else {}
        with _THREAD_LOCK:
            with _FileLock(exclusive=True):
                backup = backup_current_state()
                atomic_json_write(state_file, state)
                _record_status("atomic_save_state", {
                    "backup": backup,
                    "state_quality_after": _quality(state),
                    "state_size_after": _size(state_file),
                })
        return None

    def guarded_run_cycle(*args, **kwargs):
        acquired = _RUN_LOCK.acquire(blocking=False)
        if not acquired:
            _RUN_STATE["overlap_blocks"] = int(_RUN_STATE.get("overlap_blocks") or 0) + 1
            _record_status("run_cycle_overlap_blocked", {"args_source": kwargs.get("source")})
            payload = _compact_status(module)
            payload.update({
                "status": "ok",
                "run_skipped": True,
                "skip_reason": "run_cycle_already_active",
                "state_io_version": VERSION,
            })
            return payload
        start = time.time()
        _RUN_STATE.update({
            "active": True,
            "started_ts": int(start),
            "started_local": _now_text(),
            "last_error": None,
        })
        try:
            result = original_run_cycle(*args, **kwargs) if callable(original_run_cycle) else _compact_status(module)
            return result
        except Exception as exc:
            _RUN_STATE["last_error"] = repr(exc)
            _record_status("run_cycle_error", {"error": repr(exc)})
            raise
        finally:
            runtime = round(time.time() - start, 3)
            _RUN_STATE.update({
                "active": False,
                "last_finished_ts": int(time.time()),
                "last_finished_local": _now_text(),
                "last_runtime_seconds": runtime,
            })
            try:
                _RUN_LOCK.release()
            except Exception:
                pass
            _record_status("run_cycle_finished", {"runtime_seconds": runtime})

    if callable(original_load_state):
        hardened_load_state._state_io_hardened = True  # type: ignore[attr-defined]
        module.load_state = hardened_load_state
    if callable(original_save_state):
        hardened_save_state._state_io_hardened = True  # type: ignore[attr-defined]
        module.save_state = hardened_save_state
    if callable(original_run_cycle):
        guarded_run_cycle._state_io_hardened = True  # type: ignore[attr-defined]
        module.run_cycle = guarded_run_cycle

    try:
        setattr(module, "STATE_IO_HARDENING_VERSION", VERSION)
        setattr(module, "safe_load_json_file", safe_load_json_file)
        setattr(module, "atomic_json_write", atomic_json_write)
    except Exception:
        pass

    _PATCHED_MODULE_IDS.add(id(module))
    _record_status("installed", {"state_file": state_file})
    return {
        "status": "ok",
        "version": VERSION,
        "patched": {
            "load_state": callable(original_load_state),
            "save_state": callable(original_save_state),
            "run_cycle": callable(original_run_cycle),
        },
        "state_file": state_file,
    }


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-io-status" not in existing:
        flask_app.add_url_rule("/paper/state-io-status", "state_io_status", lambda: jsonify(status_payload(module)))
    _REGISTERED_APP_IDS.add(id(flask_app))
