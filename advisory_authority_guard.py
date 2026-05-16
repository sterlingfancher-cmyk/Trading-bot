"""Advisory-authority guard.

Scans state payloads for accidental live-authority flags inside ML/adaptive
modules. This is a safety/governance layer only. It does not modify trading
logic; it reports unsafe authority exposure unless explicitly permitted by env.

Routes:
- /paper/advisory-authority-status
- /paper/live-authority-guard-status
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "advisory-authority-guard-2026-05-16"
ENABLED = os.environ.get("ADVISORY_AUTHORITY_GUARD_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
ALLOW_LIVE_AUTHORITY = os.environ.get("ALLOW_EXPERIMENTAL_LIVE_AUTHORITY", "false").lower() in {"1", "true", "yes", "on"}
REGISTERED_APP_IDS: set[int] = set()
AUTHORITY_KEYS = {
    "live_authority",
    "phase3a_live_authority_allowed",
    "execution_authority",
    "resize_authority",
    "stop_authority",
    "take_profit_authority",
    "promotion_enabled",
    "hard_enforcement_active",
}
ALLOWED_TRUE_PATH_SUFFIXES = {
    # FVG hard enforcement is allowed to appear true only if the operator explicitly promotes it.
    "opening_range_fvg.hard_enforcement_active",
}


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


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _scan(obj: Any, path: str = "state", out: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    if out is None:
        out = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}"
            if key in AUTHORITY_KEYS and bool(value) is True:
                allowed = any(child.endswith(suffix) for suffix in ALLOWED_TRUE_PATH_SUFFIXES)
                out.append({"path": child, "key": key, "value": value, "allowed_by_suffix": allowed})
            if isinstance(value, (dict, list)):
                _scan(value, child, out)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj[-1000:]):
            if isinstance(value, (dict, list)):
                _scan(value, f"{path}[{idx}]", out)
    return out


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    findings = _scan(state if isinstance(state, dict) else {})
    unsafe = [f for f in findings if not f.get("allowed_by_suffix")]
    if ALLOW_LIVE_AUTHORITY:
        status_level = "allowed_by_operator_env"
    elif unsafe:
        status_level = "warn"
    else:
        status_level = "ok"
    return {
        "status": "ok",
        "type": "advisory_authority_guard",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "allow_experimental_live_authority": ALLOW_LIVE_AUTHORITY,
        "status_level": status_level,
        "unsafe_authority_findings_count": len(unsafe),
        "all_authority_findings_count": len(findings),
        "unsafe_authority_findings": unsafe[-50:],
        "all_authority_findings_tail": findings[-50:],
        "recommendation": "Keep all adaptive modules advisory-only until sample-size and walk-forward gates pass." if not unsafe else "Review unsafe authority flags before allowing live adaptive control.",
        "live_authority": False,
    }


def apply(module: Any = None) -> Dict[str, Any]:
    return {"status": "ok", "version": VERSION, "enabled": ENABLED, "allow_experimental_live_authority": ALLOW_LIVE_AUTHORITY, "live_authority": False}


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

    if "/paper/advisory-authority-status" not in existing:
        flask_app.add_url_rule("/paper/advisory-authority-status", "paper_advisory_authority_status", status_route)
    if "/paper/live-authority-guard-status" not in existing:
        flask_app.add_url_rule("/paper/live-authority-guard-status", "paper_live_authority_guard_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/advisory-authority-status", "/paper/live-authority-guard-status"], "live_authority": False}
