"""Bounded timestamped state snapshots for deploy-safe paper account recovery.

This runtime layer wraps the already-hardened save_state callable. A snapshot is
created only after the canonical state save succeeds and only when the candidate
is monotonic relative to the newest retained snapshot:

- execution/trade count may never decrease
- for equal execution counts, runner telemetry may never move backward
- execution-count advances snapshot immediately
- otherwise, periodic checkpoints are rate-limited

Snapshots are diagnostic/recovery artifacts only. This module does not restore
state automatically and does not alter strategy, sizing, thresholds, risk, ML,
or order authority.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Tuple

VERSION = "state-snapshot-archive-2026-07-28-v1"
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
SNAPSHOT_DIR = os.path.join(STATE_DIR, "state_snapshots")
MANIFEST_FILE = os.path.join(SNAPSHOT_DIR, "manifest.json")
MAX_SNAPSHOTS = max(3, int(os.environ.get("STATE_SNAPSHOT_MAX_COUNT", "8")))
MIN_CHECKPOINT_SECONDS = max(300, int(os.environ.get("STATE_SNAPSHOT_MIN_SECONDS", "1800")))

_LOCK = threading.RLock()
_PATCHED_MODULE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_LAST_STATUS: Dict[str, Any] = {}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _trade_count(state: Dict[str, Any]) -> int:
    trades = state.get("trades")
    return len(trades) if isinstance(trades, list) else 0


def _runner_rank(state: Dict[str, Any]) -> float:
    auto = state.get("auto_runner") if isinstance(state.get("auto_runner"), dict) else {}
    values = [
        auto.get("last_successful_run_ts"),
        auto.get("last_run_ts"),
        auto.get("last_attempt_ts"),
        auto.get("last_skip_ts"),
    ]
    return max((_safe_float(v) for v in values), default=0.0)


def _rank(state: Dict[str, Any]) -> Tuple[int, float]:
    return _trade_count(state), _runner_rank(state)


def _load_manifest() -> Dict[str, Any]:
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_manifest(payload: Dict[str, Any]) -> None:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    tmp = MANIFEST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, MANIFEST_FILE)


def _entries(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = manifest.get("snapshots")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _newest_entry(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [row for row in rows if os.path.exists(str(row.get("path") or ""))]
    if not valid:
        return {}
    return max(valid, key=lambda row: (_safe_float(row.get("created_ts")), int(row.get("trades_count") or 0)))


def _prune(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [row for row in rows if os.path.exists(str(row.get("path") or ""))]
    rows.sort(key=lambda row: _safe_float(row.get("created_ts")), reverse=True)
    keep = rows[:MAX_SNAPSHOTS]
    for row in rows[MAX_SNAPSHOTS:]:
        try:
            os.remove(str(row.get("path") or ""))
        except Exception:
            pass
    return keep


def archive_state(state: Dict[str, Any], state_file: str) -> Dict[str, Any]:
    global _LAST_STATUS
    if not isinstance(state, dict):
        return {"status": "skipped", "reason": "state_not_dict", "version": VERSION}

    with _LOCK:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        manifest = _load_manifest()
        rows = _entries(manifest)
        newest = _newest_entry(rows)
        candidate_trades, candidate_runner = _rank(state)
        newest_trades = int(newest.get("trades_count") or 0)
        newest_runner = _safe_float(newest.get("runner_timestamp_rank"))
        newest_created = _safe_float(newest.get("created_ts"))
        now_ts = time.time()

        if newest and candidate_trades < newest_trades:
            status = {
                "status": "blocked",
                "reason": "trade_count_regression",
                "candidate_trades": candidate_trades,
                "newest_trades": newest_trades,
                "version": VERSION,
            }
            _LAST_STATUS = status
            return status
        if newest and candidate_trades == newest_trades and candidate_runner < newest_runner:
            status = {
                "status": "blocked",
                "reason": "runner_timestamp_regression",
                "candidate_runner_timestamp_rank": candidate_runner,
                "newest_runner_timestamp_rank": newest_runner,
                "version": VERSION,
            }
            _LAST_STATUS = status
            return status

        execution_advanced = not newest or candidate_trades > newest_trades
        checkpoint_due = not newest or now_ts - newest_created >= MIN_CHECKPOINT_SECONDS
        if not execution_advanced and not checkpoint_due:
            status = {
                "status": "skipped",
                "reason": "checkpoint_rate_limited",
                "trades_count": candidate_trades,
                "seconds_until_checkpoint": max(0, int(MIN_CHECKPOINT_SECONDS - (now_ts - newest_created))),
                "version": VERSION,
            }
            _LAST_STATUS = status
            return status

        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        runner_token = int(candidate_runner) if candidate_runner > 0 else 0
        filename = f"state_t{candidate_trades:06d}_r{runner_token}_{stamp}.json"
        destination = os.path.join(SNAPSHOT_DIR, filename)
        tmp = destination + ".tmp"

        if state_file and os.path.exists(state_file):
            shutil.copy2(state_file, tmp)
            with open(tmp, "rb") as handle:
                os.fsync(handle.fileno())
        else:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"), default=str)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(tmp, destination)

        row = {
            "path": destination,
            "filename": filename,
            "created_ts": now_ts,
            "created_local": _now_text(),
            "trades_count": candidate_trades,
            "runner_timestamp_rank": candidate_runner,
            "positions_count": len(state.get("positions") or {}) if isinstance(state.get("positions"), dict) else 0,
            "size_bytes": os.path.getsize(destination),
            "reason": "execution_advanced" if execution_advanced else "periodic_checkpoint",
        }
        rows.append(row)
        rows = _prune(rows)
        manifest = {
            "status": "ok",
            "type": "state_snapshot_manifest",
            "version": VERSION,
            "updated_local": _now_text(),
            "max_snapshots": MAX_SNAPSHOTS,
            "min_checkpoint_seconds": MIN_CHECKPOINT_SECONDS,
            "monotonic_trade_guard": True,
            "monotonic_runner_timestamp_guard": True,
            "snapshots": rows,
        }
        _write_manifest(manifest)
        status = {
            "status": "ok",
            "version": VERSION,
            "snapshot_written": destination,
            "snapshot_reason": row["reason"],
            "trades_count": candidate_trades,
            "runner_timestamp_rank": candidate_runner,
            "retained_count": len(rows),
        }
        _LAST_STATUS = status
        return status


def install(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "reason": "core_missing", "version": VERSION}
    if id(core) in _PATCHED_MODULE_IDS:
        return {"status": "ok", "already_installed": True, "version": VERSION}

    original_save = getattr(core, "save_state", None)
    if not callable(original_save):
        return {"status": "pending", "reason": "save_state_missing", "version": VERSION}
    state_file = str(getattr(core, "STATE_FILE", os.path.join(STATE_DIR, "state.json")))

    def snapshotting_save_state(state, *args, **kwargs):
        result = original_save(state, *args, **kwargs)
        try:
            archive_state(state if isinstance(state, dict) else dict(state or {}), state_file)
        except Exception as exc:
            global _LAST_STATUS
            _LAST_STATUS = {"status": "error", "version": VERSION, "error": repr(exc)}
        return result

    snapshotting_save_state._state_snapshot_archive = True  # type: ignore[attr-defined]
    snapshotting_save_state._state_snapshot_original = original_save  # type: ignore[attr-defined]
    core.save_state = snapshotting_save_state
    _PATCHED_MODULE_IDS.add(id(core))
    return {"status": "ok", "version": VERSION, "patched": True, "state_file": state_file}


def status_payload(core: Any = None) -> Dict[str, Any]:
    manifest = _load_manifest()
    rows = _prune(_entries(manifest))
    newest = _newest_entry(rows)
    current = getattr(core, "portfolio", {}) if core is not None else {}
    current = current if isinstance(current, dict) else {}
    return {
        "status": "ok",
        "type": "state_snapshot_archive_status",
        "version": VERSION,
        "installed": bool(core is not None and id(core) in _PATCHED_MODULE_IDS),
        "snapshot_dir": SNAPSHOT_DIR,
        "manifest_file": MANIFEST_FILE,
        "retained_count": len(rows),
        "max_snapshots": MAX_SNAPSHOTS,
        "min_checkpoint_seconds": MIN_CHECKPOINT_SECONDS,
        "monotonic_trade_guard": True,
        "monotonic_runner_timestamp_guard": True,
        "current_rank": {"trades_count": _trade_count(current), "runner_timestamp_rank": _runner_rank(current)},
        "newest_snapshot": newest or None,
        "last_archive_event": dict(_LAST_STATUS),
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/state-snapshot-archive-status" not in existing:
        flask_app.add_url_rule(
            "/paper/state-snapshot-archive-status",
            "state_snapshot_archive_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core)
