"""State-size watchdog for telemetry growth control.

Advisory/governance only. This module checks persistent state size and reports
when telemetry growth approaches operational thresholds. It does not prune,
mutate, or restore state automatically.

Routes:
- /paper/state-size-watchdog
- /paper/telemetry-retention-status
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "state-size-watchdog-2026-05-16"
ENABLED = os.environ.get("STATE_SIZE_WATCHDOG_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
WARN_MB = float(os.environ.get("STATE_SIZE_WARN_MB", "25"))
CRITICAL_MB = float(os.environ.get("STATE_SIZE_CRITICAL_MB", "50"))
REGISTERED_APP_IDS: set[int] = set()


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_path(mod: Any = None) -> str:
    candidates = []
    if mod is not None:
        for key in ("STATE_FILE", "STATE_PATH", "state_file"):
            value = getattr(mod, key, None)
            if value:
                candidates.append(str(value))
    candidates.extend([
        os.environ.get("STATE_FILE", ""),
        os.environ.get("STATE_PATH", ""),
        "/data/state.json",
        "state.json",
    ])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0] if candidates and candidates[0] else "/data/state.json"


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _section_lengths(state: Dict[str, Any]) -> Dict[str, Any]:
    sections = {}
    for key in (
        "trades",
        "history",
        "ml_phase2",
        "ml_phase25",
        "trade_quality_telemetry",
        "intratrade_path_capture",
        "mae_mfe_integration",
        "adaptive_ml_research",
        "adaptive_portfolio_intelligence",
        "scanner_audit",
    ):
        value = state.get(key)
        if isinstance(value, list):
            sections[key] = {"kind": "list", "rows": len(value)}
        elif isinstance(value, dict):
            item = {"kind": "dict", "keys": len(value)}
            if isinstance(value.get("dataset"), list):
                item["dataset_rows"] = len(value.get("dataset"))
            if isinstance(value.get("paths"), dict):
                item["paths"] = len(value.get("paths"))
            if isinstance(value.get("closed_path_archive"), list):
                item["closed_path_archive_rows"] = len(value.get("closed_path_archive"))
            sections[key] = item
    return sections


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    mod = mod or _module()
    path = _state_path(mod)
    size_bytes = os.path.getsize(path) if path and os.path.exists(path) else 0
    size_mb = round(size_bytes / (1024 * 1024), 3)
    if size_mb >= CRITICAL_MB:
        level = "critical"
        recommendation = "Pause new telemetry expansion and prune/archive state before adding more modules."
    elif size_mb >= WARN_MB:
        level = "warn"
        recommendation = "Add retention limits or archive old telemetry before state growth becomes operationally risky."
    else:
        level = "ok"
        recommendation = "State size is within current telemetry-growth limits."
    return {
        "status": "ok",
        "type": "state_size_watchdog",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "state_file": path,
        "state_size_bytes": size_bytes,
        "state_size_mb": size_mb,
        "warn_mb": WARN_MB,
        "critical_mb": CRITICAL_MB,
        "level": level,
        "recommendation": recommendation,
        "retention_policy": {
            "telemetry_archive_limit_default": 500,
            "ml_feature_row_limit_recommended": 10000,
            "automatic_pruning_enabled": False,
        },
        "section_lengths": _section_lengths(state if isinstance(state, dict) else {}),
        "live_authority": False,
    }


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    return {"status": "ok", "version": VERSION, "enabled": ENABLED, "live_authority": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    if "/paper/state-size-watchdog" not in existing:
        flask_app.add_url_rule("/paper/state-size-watchdog", "paper_state_size_watchdog", status_route)
    if "/paper/telemetry-retention-status" not in existing:
        flask_app.add_url_rule("/paper/telemetry-retention-status", "paper_telemetry_retention_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/state-size-watchdog", "/paper/telemetry-retention-status"], "live_authority": False}
