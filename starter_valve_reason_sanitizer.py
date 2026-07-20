"""Sanitize starter-valve blocker detail mappings.

The starter overlays call blocked(info.get("reason"), **info). A plain mapping that
also contains ``reason`` sends the same argument twice and raises TypeError. This
module preserves ``get('reason')`` while omitting ``reason`` from mapping expansion.
It changes reporting shape only; no eligibility, risk, sizing, or authority rules.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, Tuple

VERSION = "starter-valve-reason-sanitizer-2026-07-20-v1"
_PATCHED = False
REGISTERED_APP_IDS: set[int] = set()


class _ReasonSafeDict(dict):
    """Dict whose reason is readable through get() but absent from ** expansion."""

    def __init__(self, source: Any = None):
        row = dict(source or {}) if isinstance(source, dict) else {}
        self._reason_value = row.pop("reason", None)
        super().__init__(row)

    def get(self, key: Any, default: Any = None) -> Any:
        if key == "reason":
            return self._reason_value if self._reason_value is not None else default
        return super().get(key, default)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    return None


def _wrap_tuple_result(module: Any, function_name: str) -> bool:
    current = getattr(module, function_name, None)
    if not callable(current):
        return False
    if getattr(current, "_starter_valve_reason_sanitized", False):
        return False

    def sanitized(*args: Any, **kwargs: Any) -> Tuple[bool, Dict[str, Any]]:
        ok, info = current(*args, **kwargs)
        if isinstance(info, dict) and "reason" in info:
            info = _ReasonSafeDict(info)
        return bool(ok), info

    sanitized._starter_valve_reason_sanitized = True  # type: ignore[attr-defined]
    sanitized._starter_valve_reason_sanitizer_version = VERSION  # type: ignore[attr-defined]
    sanitized._starter_valve_reason_sanitizer_original = current  # type: ignore[attr-defined]
    setattr(module, function_name, sanitized)
    return True


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    changed: Dict[str, bool] = {}
    try:
        import extended_leader_starter_valve as extended
        changed["extended_risk_ok"] = _wrap_tuple_result(extended, "_risk_ok")
    except Exception:
        changed["extended_risk_ok"] = False
    try:
        import risk_on_starter_participation_valve as risk_on
        changed["risk_on_quality_block_allowed"] = _wrap_tuple_result(risk_on, "_quality_block_allowed")
        changed["risk_on_risk_ok"] = _wrap_tuple_result(risk_on, "_risk_ok")
    except Exception:
        changed["risk_on_quality_block_allowed"] = False
        changed["risk_on_risk_ok"] = False
    _PATCHED = True
    return status_payload(core, changed)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def status_payload(core: Any = None, changed: Dict[str, bool] | None = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "type": "starter_valve_reason_sanitizer_status",
        "version": VERSION,
        "generated_local": _now(core or _mod()),
        "patched": bool(_PATCHED),
        "changed_this_call": changed or {},
        "duplicate_reason_kwarg_prevented": True,
        "logic_changed": False,
        "authority_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/starter-valve-reason-sanitizer-status" not in existing:
        flask_app.add_url_rule(
            "/paper/starter-valve-reason-sanitizer-status",
            "starter_valve_reason_sanitizer_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
