"""Deploy-safe persistent state recovery guard.

This module runs before app.py is imported by wsgi.py. It may restore a damaged or
truncated state file, but it must never roll a paper account backward to a backup
with fewer executions or older runner telemetry.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from typing import Any, Dict

VERSION = "state-recovery-guard-2026-07-28-v2-monotonic"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
STATE_BACKUP_LATEST = os.path.join(STATE_DIR, "state_backup_latest.json")
STATE_BACKUP_LARGEST = os.path.join(STATE_DIR, "state_backup_largest.json")
STATE_RECOVERY_STATUS = os.path.join(STATE_DIR, "state_recovery_status.json")

MIN_RESTORE_SIZE_RATIO = float(os.environ.get("STATE_RECOVERY_MIN_SIZE_RATIO", "0.80"))
MIN_SCORE_EDGE = int(os.environ.get("STATE_RECOVERY_MIN_SCORE_EDGE", "2"))
RESTORE_ENABLED = os.environ.get("STATE_RECOVERY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

_LAST_STATUS: Dict[str, Any] = {}
_REGISTERED_APP_IDS: set[int] = set()


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_mkdir(path: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def _file_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _write_json(path: str, payload: Dict[str, Any]) -> bool:
    try:
        _safe_mkdir(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _timestamp_rank(state: Dict[str, Any]) -> float:
    """Best monotonic runner timestamp available in a state snapshot."""
    ar = state.get("auto_runner") if isinstance(state.get("auto_runner"), dict) else {}
    for key in (
        "last_successful_run_ts",
        "last_run_ts",
        "last_attempt_ts",
        "last_skip_ts",
    ):
        try:
            value = float(ar.get(key) or 0.0)
            if value > 0:
                return value
        except Exception:
            pass
    return 0.0


def _state_quality(state: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    trades = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    history = state.get("history", []) if isinstance(state.get("history"), list) else []
    reports = state.get("reports", {}) if isinstance(state.get("reports"), dict) else {}
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    scanner = state.get("scanner_audit", {}) if isinstance(state.get("scanner_audit"), dict) else {}
    recent_trades = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    has_account = any(k in state for k in ["cash", "equity", "peak"])
    has_trading_data = bool(trades or recent_trades or history or reports or positions or scanner)

    score = 0
    score += 3 if has_account else 0
    score += 3 if has_trading_data else 0
    score += min(len(trades), 20)
    score += min(len(recent_trades), 10)
    score += min(len(history), 100) // 10
    score += 3 if reports else 0
    # Open positions are operational state, not evidence that a snapshot is newer.
    # They intentionally do not increase recovery quality.

    return {
        "path": path,
        "exists": bool(path and os.path.exists(path)),
        "size_bytes": _file_size(path) if path else 0,
        "valid": bool(has_account or has_trading_data),
        "score": score,
        "trades_count": len(trades),
        "recent_trades_count": len(recent_trades),
        "history_count": len(history),
        "reports_present": bool(reports),
        "positions_count": len(positions),
        "scanner_audit_present": bool(scanner),
        "has_account_fields": has_account,
        "runner_timestamp_rank": _timestamp_rank(state),
    }


def _is_restore_candidate(current_q: Dict[str, Any], backup_q: Dict[str, Any]) -> Dict[str, Any]:
    if not RESTORE_ENABLED:
        return {"should_restore": False, "reason": "restore_disabled"}
    if not backup_q.get("valid") or backup_q.get("size_bytes", 0) <= 0:
        return {"should_restore": False, "reason": "backup_not_valid"}
    if current_q.get("positions_count", 0) > 0:
        return {"should_restore": False, "reason": "current_state_has_open_positions"}

    current_trades = int(current_q.get("trades_count", 0) or 0)
    backup_trades = int(backup_q.get("trades_count", 0) or 0)
    current_runner_ts = float(current_q.get("runner_timestamp_rank", 0.0) or 0.0)
    backup_runner_ts = float(backup_q.get("runner_timestamp_rank", 0.0) or 0.0)

    # Hard monotonicity rules: recovery may repair corruption, never rewrite history.
    if backup_trades < current_trades:
        return {
            "should_restore": False,
            "reason": "backup_has_fewer_trades_than_current",
            "current_trades": current_trades,
            "backup_trades": backup_trades,
        }
    if current_runner_ts > 0 and backup_runner_ts > 0 and backup_runner_ts < current_runner_ts:
        return {
            "should_restore": False,
            "reason": "backup_runner_telemetry_is_older",
            "current_runner_timestamp_rank": current_runner_ts,
            "backup_runner_timestamp_rank": backup_runner_ts,
        }

    current_size = int(current_q.get("size_bytes", 0) or 0)
    backup_size = int(backup_q.get("size_bytes", 0) or 0)
    current_score = int(current_q.get("score", 0) or 0)
    backup_score = int(backup_q.get("score", 0) or 0)
    size_ratio = current_size / backup_size if backup_size > 0 else 1.0
    backup_has_more_trades = backup_trades > current_trades
    backup_has_more_history = int(backup_q.get("history_count", 0) or 0) > int(current_q.get("history_count", 0) or 0)
    backup_is_newer = backup_runner_ts > current_runner_ts
    score_edge = backup_score - current_score
    materially_smaller = size_ratio < MIN_RESTORE_SIZE_RATIO
    materially_better = backup_has_more_trades or backup_is_newer or (score_edge >= MIN_SCORE_EDGE and backup_has_more_history)

    if materially_smaller and materially_better:
        return {
            "should_restore": True,
            "reason": "current_state_smaller_and_backup_monotonically_newer",
            "size_ratio": round(size_ratio, 4),
            "score_edge": score_edge,
            "backup_has_more_trades": backup_has_more_trades,
            "backup_has_more_history": backup_has_more_history,
            "backup_is_newer": backup_is_newer,
        }

    return {
        "should_restore": False,
        "reason": "current_state_not_weak_or_backup_not_newer",
        "size_ratio": round(size_ratio, 4),
        "score_edge": score_edge,
        "backup_has_more_trades": backup_has_more_trades,
        "backup_has_more_history": backup_has_more_history,
        "backup_is_newer": backup_is_newer,
    }


def preflight_recover() -> Dict[str, Any]:
    global _LAST_STATUS
    current = _load_json(STATE_FILE)
    backup = _load_json(STATE_BACKUP_LARGEST)
    current_q = _state_quality(current, STATE_FILE)
    backup_q = _state_quality(backup, STATE_BACKUP_LARGEST)
    decision = _is_restore_candidate(current_q, backup_q)

    status: Dict[str, Any] = {
        "status": "ok",
        "type": "state_recovery_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "state_file": STATE_FILE,
        "backup_largest_file": STATE_BACKUP_LARGEST,
        "backup_latest_file": STATE_BACKUP_LATEST,
        "recovery_status_file": STATE_RECOVERY_STATUS,
        "restore_enabled": RESTORE_ENABLED,
        "current_state_quality_before": current_q,
        "largest_backup_quality": backup_q,
        "decision": decision,
        "restored": False,
        "pre_restore_backup_file": None,
        "monotonic_trade_guard": True,
        "monotonic_runner_timestamp_guard": True,
        "positions_do_not_increase_backup_quality": True,
    }

    if decision.get("should_restore"):
        try:
            _safe_mkdir(STATE_FILE)
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_restore_backup = os.path.join(STATE_DIR, f"state_pre_restore_{ts}.json")
            if os.path.exists(STATE_FILE):
                shutil.copy2(STATE_FILE, pre_restore_backup)
                status["pre_restore_backup_file"] = pre_restore_backup
            shutil.copy2(STATE_BACKUP_LARGEST, STATE_FILE)
            shutil.copy2(STATE_BACKUP_LARGEST, STATE_BACKUP_LATEST)
            status["restored"] = True
            status["current_state_quality_after"] = _state_quality(_load_json(STATE_FILE), STATE_FILE)
        except Exception as exc:
            status["status"] = "error"
            status["restored"] = False
            status["error"] = str(exc)
    else:
        status["current_state_quality_after"] = current_q

    _LAST_STATUS = status
    _write_json(STATE_RECOVERY_STATUS, status)
    return status


def get_status() -> Dict[str, Any]:
    status = _load_json(STATE_RECOVERY_STATUS)
    if not status:
        status = dict(_LAST_STATUS) if _LAST_STATUS else preflight_recover()
    status["current_state_quality_now"] = _state_quality(_load_json(STATE_FILE), STATE_FILE)
    status["largest_backup_quality_now"] = _state_quality(_load_json(STATE_BACKUP_LARGEST), STATE_BACKUP_LARGEST)
    status["generated_local_now"] = _now_text()
    return status


def register_routes(flask_app: Any) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-recovery-status" not in existing:
        flask_app.add_url_rule("/paper/state-recovery-status", "state_recovery_status_guard", lambda: jsonify(get_status()))
    _REGISTERED_APP_IDS.add(id(flask_app))


try:
    preflight_recover()
except Exception:
    pass
