"""Runtime-controls self-healing and diagnostics for Railway /data writes.

This module hardens runtime_controls.json writes without touching trading state.
It is intentionally advisory/non-trading: it only repairs the runtime-controls
metadata file and monkey-patches risk_bootstrap's atomic writer to avoid shared
.tmp file contention.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from typing import Any, Dict

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None

try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore

VERSION = "runtime-controls-self-heal-2026-05-16"
PATCHED = False
LAST_WRITE_DIAGNOSTIC: Dict[str, Any] = {}

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
RUNTIME_CONTROLS_FILE = os.path.join(STATE_DIR or ".", "runtime_controls.json")
MARKET_TZ_NAME = os.environ.get("MARKET_TZ", "America/Chicago")


def _now() -> dt.datetime:
    if pytz:
        return dt.datetime.now(pytz.timezone(MARKET_TZ_NAME))
    return dt.datetime.now()


def _now_text() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S %Z")


def _file_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _age_seconds(path: str) -> float | None:
    try:
        return round(max(0.0, time.time() - os.path.getmtime(path)), 3)
    except Exception:
        return None


def _safe_json(path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "path": path,
        "exists": os.path.exists(path),
        "size_bytes": _file_size(path),
        "json_ok": False,
        "json_type": None,
        "error": None,
    }
    if not out["exists"]:
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        out["json_ok"] = isinstance(obj, dict)
        out["json_type"] = type(obj).__name__
        out["keys_count"] = len(obj) if isinstance(obj, dict) else None
        out["top_level_keys"] = sorted(list(obj.keys()))[:25] if isinstance(obj, dict) else []
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _path_diag(path: str) -> Dict[str, Any]:
    parent = os.path.dirname(path) or "."
    return {
        "path": path,
        "exists": os.path.exists(path),
        "is_file": os.path.isfile(path),
        "is_dir": os.path.isdir(path),
        "size_bytes": _file_size(path),
        "age_seconds": _age_seconds(path),
        "readable": os.access(path, os.R_OK) if os.path.exists(path) else None,
        "writable": os.access(path, os.W_OK) if os.path.exists(path) else None,
        "parent": parent,
        "parent_exists": os.path.isdir(parent),
        "parent_readable": os.access(parent, os.R_OK) if os.path.exists(parent) else None,
        "parent_writable": os.access(parent, os.W_OK) if os.path.exists(parent) else None,
        "parent_executable": os.access(parent, os.X_OK) if os.path.exists(parent) else None,
    }


def _lock_check(parent: str) -> Dict[str, Any]:
    lock_path = os.path.join(parent or ".", "runtime_controls.json.lock")
    out: Dict[str, Any] = {
        "lock_path": lock_path,
        "fcntl_available": fcntl is not None,
        "lock_acquired": None,
        "lock_contention": False,
        "error": None,
    }
    if fcntl is None:
        return out
    try:
        os.makedirs(parent or ".", exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                out["lock_acquired"] = True
            except BlockingIOError:
                out["lock_acquired"] = False
                out["lock_contention"] = True
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _merged_runtime_payload(extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    current: Dict[str, Any] = {}
    try:
        with open(RUNTIME_CONTROLS_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            current = obj
    except Exception:
        current = {}

    repair_block = {
        "version": VERSION,
        "generated_local": _now_text(),
        "state_file": STATE_FILE,
        "runtime_controls_file": RUNTIME_CONTROLS_FILE,
        "self_heal": True,
    }
    if extra:
        repair_block.update(extra)

    current.update({
        "status": current.get("status", "ok"),
        "runtime_controls_file": RUNTIME_CONTROLS_FILE,
        "runtime_controls_repair": repair_block,
    })
    return current


def _robust_atomic_json_write(path: str, payload: Dict[str, Any]) -> bool:
    """Drop-in replacement for risk_bootstrap._atomic_json_write."""
    global LAST_WRITE_DIAGNOSTIC
    parent = os.path.dirname(path) or "."
    tmp = f"{path}.{os.getpid()}.{int(time.time() * 1000)}.tmp"
    diagnostic: Dict[str, Any] = {
        "version": VERSION,
        "path": path,
        "parent": parent,
        "generated_local": _now_text(),
        "method": "unique_tmp_os_replace",
        "ok": False,
        "errors": [],
        "parent_diag_before": _path_diag(parent),
    }

    try:
        os.makedirs(parent, exist_ok=True)
    except Exception as exc:
        diagnostic["errors"].append(f"makedirs_failed: {type(exc).__name__}: {exc}")

    try:
        stale_default_tmp = path + ".tmp"
        diagnostic["stale_default_tmp"] = {
            "path": stale_default_tmp,
            "exists": os.path.exists(stale_default_tmp),
            "size_bytes": _file_size(stale_default_tmp),
            "age_seconds": _age_seconds(stale_default_tmp),
        }
        if os.path.exists(stale_default_tmp) and (_age_seconds(stale_default_tmp) or 0) > 300:
            try:
                os.remove(stale_default_tmp)
                diagnostic["stale_default_tmp"]["removed"] = True
            except Exception as exc:
                diagnostic["stale_default_tmp"]["remove_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        diagnostic["errors"].append(f"stale_tmp_check_failed: {type(exc).__name__}: {exc}")

    lock_file = None
    try:
        if fcntl is not None:
            lock_path = os.path.join(parent, "runtime_controls.json.lock")
            lock_file = open(lock_path, "a+", encoding="utf-8")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            diagnostic["lock"] = {"used": True, "path": lock_path, "acquired": True}
        else:
            diagnostic["lock"] = {"used": False, "reason": "fcntl_unavailable"}

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

        reread = _safe_json(path)
        diagnostic["reread"] = reread
        diagnostic["ok"] = bool(reread.get("json_ok"))
        return bool(diagnostic["ok"])
    except Exception as exc:
        diagnostic["errors"].append(f"atomic_write_failed: {type(exc).__name__}: {exc}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
    finally:
        if lock_file is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
                lock_file.close()
            except Exception:
                pass
        diagnostic["parent_diag_after"] = _path_diag(parent)
        diagnostic["final_file_diag"] = _path_diag(path)
        LAST_WRITE_DIAGNOSTIC = diagnostic


def _repair_runtime_controls() -> Dict[str, Any]:
    payload = _merged_runtime_payload({"repair_attempted": True})
    ok = _robust_atomic_json_write(RUNTIME_CONTROLS_FILE, payload)
    return {
        "write_ok": ok,
        "write_diagnostic": LAST_WRITE_DIAGNOSTIC,
        "runtime_controls_json": _safe_json(RUNTIME_CONTROLS_FILE),
    }


def _status_payload(repair: bool = True) -> Dict[str, Any]:
    parent = os.path.dirname(RUNTIME_CONTROLS_FILE) or "."
    before_json = _safe_json(RUNTIME_CONTROLS_FILE)
    diagnosis: Dict[str, Any] = {
        "status": "ok",
        "type": "runtime_controls_repair_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "state_file": STATE_FILE,
        "runtime_controls_file": RUNTIME_CONTROLS_FILE,
        "state_file_diag": _path_diag(STATE_FILE),
        "runtime_controls_diag": _path_diag(RUNTIME_CONTROLS_FILE),
        "runtime_controls_json_before": before_json,
        "parent_diag": _path_diag(parent),
        "lock_check": _lock_check(parent),
        "last_write_diagnostic": LAST_WRITE_DIAGNOSTIC,
        "patched_risk_bootstrap_atomic_writer": PATCHED,
        "repair_attempted": repair,
    }

    if repair:
        diagnosis["repair"] = _repair_runtime_controls()
        diagnosis["runtime_controls_json_after"] = _safe_json(RUNTIME_CONTROLS_FILE)

    findings = []
    parent_diag = diagnosis["parent_diag"]
    if not os.path.exists(parent):
        findings.append("runtime_controls_parent_missing")
    elif not parent_diag.get("writable"):
        findings.append("runtime_controls_parent_not_writable")
    if before_json.get("exists") and not before_json.get("json_ok"):
        findings.append("runtime_controls_json_parse_failure")
    if diagnosis["lock_check"].get("lock_contention"):
        findings.append("runtime_controls_lock_contention")
    if repair and not diagnosis.get("repair", {}).get("write_ok"):
        findings.append("runtime_controls_repair_write_failed")
    if not findings:
        findings.append("runtime_controls_write_path_ok")

    diagnosis["findings"] = findings
    diagnosis["recommendation"] = (
        "Runtime-control writes are healthy after self-heal."
        if findings == ["runtime_controls_write_path_ok"]
        else "Review findings; if parent is not writable, check Railway volume mount and STATE_DIR configuration."
    )
    return diagnosis


def apply(core: Any | None = None) -> Dict[str, Any]:
    global PATCHED
    try:
        import risk_bootstrap  # type: ignore
        setattr(risk_bootstrap, "_atomic_json_write", _robust_atomic_json_write)
        PATCHED = True
        return {"status": "ok", "version": VERSION, "patched": True}
    except Exception as exc:
        return {"status": "warn", "version": VERSION, "patched": False, "error": str(exc)}


def register_routes(flask_app: Any, core: Any | None = None) -> None:
    from flask import jsonify, request

    def _json_status():
        repair = str(request.args.get("repair", "1")).lower() not in {"0", "false", "no"}
        return jsonify(_status_payload(repair=repair))

    routes = (
        ("/paper/runtime-controls-repair-status", "runtime_controls_repair_status"),
        ("/paper/runtime-controls-write-status", "runtime_controls_write_status"),
        ("/paper/runtime-controls-self-heal-status", "runtime_controls_self_heal_status"),
    )
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    for path, endpoint in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, _json_status)
