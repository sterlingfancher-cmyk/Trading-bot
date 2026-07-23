"""Diagnostic-only state provenance and monotonicity monitor.

Tracks state source metadata, revision, file identity, and cumulative metric high-water
marks in a sidecar file. It detects backward movement without mutating trading state,
positions, signals, risk controls, sizing, orders, or authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import threading
from typing import Any, Dict

VERSION = "state-provenance-monitor-2026-07-23-v1"
_REGISTERED_APP_IDS: set[int] = set()
_PATCHED_MODULE_IDS: set[int] = set()
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}


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


def _state_path(core: Any) -> str:
    return str(getattr(core, "STATE_FILE", None) or os.environ.get("STATE_FILE") or "state.json")


def _sidecar_path(core: Any) -> str:
    state_path = _state_path(core)
    folder = os.path.dirname(os.path.abspath(state_path)) or "."
    return os.path.join(folder, "state_provenance_status.json")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    trades = state.get("trades") if isinstance(state.get("trades"), list) else []
    perf = state.get("performance") if isinstance(state.get("performance"), dict) else {}
    journal = state.get("trade_journal") if isinstance(state.get("trade_journal"), dict) else {}
    summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
    realized = state.get("realized_pnl") if isinstance(state.get("realized_pnl"), dict) else {}
    return {
        "state_revision": _safe_int(state.get("_state_revision"), 0),
        "execution_rows": _safe_int(summary.get("execution_rows_count"), len(trades)),
        "wins_total": _safe_int(perf.get("wins_total"), _safe_int(summary.get("wins_total"), _safe_int(state.get("wins_total"), 0))),
        "losses_total": _safe_int(perf.get("losses_total"), _safe_int(summary.get("losses_total"), _safe_int(state.get("losses_total"), 0))),
        "realized_total": _safe_float(perf.get("realized_pnl_total"), _safe_float(summary.get("realized_total"), _safe_float(realized.get("total"), _safe_float(state.get("realized_pnl_total"), 0.0)))),
        "equity": _safe_float(state.get("equity"), 0.0),
        "positions_count": len(state.get("positions")) if isinstance(state.get("positions"), dict) else 0,
    }


def _file_meta(path: str) -> Dict[str, Any]:
    out = {"path": path, "exists": False, "size_bytes": 0, "mtime_ns": None, "sha256_prefix": None}
    try:
        stat = os.stat(path)
        out.update({"exists": True, "size_bytes": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)})
        h = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        out["sha256_prefix"] = h.hexdigest()[:16]
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


def _read_sidecar(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_sidecar(path: str, payload: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        pass


def _source_hint(core: Any, state_path: str) -> Dict[str, Any]:
    hint = {"source": "core.load_state", "confidence": "medium"}
    try:
        import state_io_hardening as io
        event = getattr(io, "_LAST_STATUS", {}) if isinstance(getattr(io, "_LAST_STATUS", {}), dict) else {}
        if event.get("event") == "backup_read":
            hint = {"source": "backup_fallback", "path": event.get("source"), "confidence": "high"}
        elif os.path.exists(state_path):
            hint = {"source": "primary_state_file", "path": state_path, "confidence": "medium"}
        hint["state_io_last_event"] = event.get("event")
    except Exception:
        if os.path.exists(state_path):
            hint = {"source": "primary_state_file", "path": state_path, "confidence": "low"}
    return hint


def observe(core: Any = None, state: Dict[str, Any] | None = None, trigger: str = "status") -> Dict[str, Any]:
    global _LAST
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    if not isinstance(state, dict):
        try:
            loaded = core.load_state()
            state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            state = getattr(core, "portfolio", {}) if isinstance(getattr(core, "portfolio", {}), dict) else {}

    state_path = _state_path(core)
    sidecar_path = _sidecar_path(core)
    current = _metrics(state)
    prior_doc = _read_sidecar(sidecar_path)
    high = prior_doc.get("high_water_marks") if isinstance(prior_doc.get("high_water_marks"), dict) else {}
    previous = prior_doc.get("last_observation") if isinstance(prior_doc.get("last_observation"), dict) else {}

    monotonic_fields = ("state_revision", "execution_rows", "wins_total", "losses_total", "realized_total")
    regressions = []
    next_high: Dict[str, Any] = dict(high)
    for field in monotonic_fields:
        value = current.get(field)
        prior_high = high.get(field)
        if prior_high is not None and value is not None and float(value) < float(prior_high):
            regressions.append({"field": field, "current": value, "high_water": prior_high, "delta": round(float(value) - float(prior_high), 6)})
        if value is not None and (prior_high is None or float(value) > float(prior_high)):
            next_high[field] = value

    file_meta = _file_meta(state_path)
    source = _source_hint(core, state_path)
    observation = {
        "generated_local": _now(),
        "trigger": trigger,
        "metrics": current,
        "state_file": file_meta,
        "source_hint": source,
        "state_updated_local": state.get("_state_updated_local"),
        "state_update_source": state.get("_state_update_source"),
        "persistence_mode": getattr(core, "STATE_PERSISTENCE_MODE", None),
    }
    payload = {
        "status": "warn" if regressions else "ok",
        "overall": "warn" if regressions else "pass",
        "type": "state_provenance_status",
        "version": VERSION,
        "generated_local": observation["generated_local"],
        "regression_detected": bool(regressions),
        "regressions": regressions,
        "current": observation,
        "previous_observation": previous,
        "high_water_marks": next_high,
        "sidecar_file": sidecar_path,
        "authority": {
            "changes_trading_logic": False,
            "changes_risk_or_sizing": False,
            "changes_orders": False,
            "changes_state_payload": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
        "next_action": "Inspect state path/source and backup fallback if a regression is detected; do not overwrite trading state from this monitor.",
    }
    _write_sidecar(sidecar_path, {"version": VERSION, "high_water_marks": next_high, "last_observation": observation, "last_regressions": regressions})
    with _LOCK:
        _LAST = payload
    return payload


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    current = getattr(core, "load_state", None)
    if callable(current) and getattr(current, "_state_provenance_monitor_version", None) != VERSION:
        original = current
        def wrapped_load_state(*args, **kwargs):
            state = original(*args, **kwargs)
            try:
                observe(core, state if isinstance(state, dict) else {}, trigger="load_state")
            except Exception:
                pass
            return state
        wrapped_load_state._state_provenance_monitor_version = VERSION  # type: ignore[attr-defined]
        wrapped_load_state._state_provenance_monitor_original = original  # type: ignore[attr-defined]
        core.load_state = wrapped_load_state
    _PATCHED_MODULE_IDS.add(id(core))
    return {"status": "ok", "overall": "pass", "version": VERSION, "installed": True, "state_file": _state_path(core), "sidecar_file": _sidecar_path(core)}


def status_payload(core: Any = None) -> Dict[str, Any]:
    return observe(core or _mod(), trigger="status")


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
    if "/paper/state-provenance-status" not in existing:
        flask_app.add_url_rule("/paper/state-provenance-status", "state_provenance_status", lambda: jsonify(status_payload(core or _mod())))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
