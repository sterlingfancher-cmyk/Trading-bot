"""Strategy-label schema validator.

Advisory only. Checks whether trade/scanner/ML rows contain canonical strategy
label fields needed for future strategy promotion/demotion.

Routes:
- /paper/strategy-label-schema-status
- /paper/setup-label-quality-status
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List, Tuple

VERSION = "strategy-label-schema-2026-05-16-route-fix"
REGISTERED_APP_IDS: set[int] = set()
REQUIRED_FIELDS = ["strategy_id", "setup_family", "entry_model", "exit_model", "risk_model"]


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


def _rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    trades = state.get("trades")
    if isinstance(trades, list):
        out.extend([r for r in trades if isinstance(r, dict)])
    ml2 = state.get("ml_phase2")
    if isinstance(ml2, dict) and isinstance(ml2.get("dataset"), list):
        out.extend([r for r in ml2.get("dataset", []) if isinstance(r, dict)])
    tq = state.get("trade_quality_telemetry")
    if isinstance(tq, dict) and isinstance(tq.get("recent_quality_tail"), list):
        out.extend([r for r in tq.get("recent_quality_tail", []) if isinstance(r, dict)])
    return out[-5000:]


def _coverage(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    fields = {}
    for field in REQUIRED_FIELDS:
        present = sum(1 for row in rows if row.get(field))
        fields[field] = {"present": present, "coverage_pct": round((present / n) * 100.0, 2) if n else 0.0}
    complete = sum(1 for row in rows if all(row.get(field) for field in REQUIRED_FIELDS))
    partial = sum(1 for row in rows if any(row.get(field) for field in REQUIRED_FIELDS) and not all(row.get(field) for field in REQUIRED_FIELDS))
    missing = n - complete - partial
    return {
        "rows_checked": n,
        "complete_rows": complete,
        "partial_rows": partial,
        "missing_rows": missing,
        "complete_coverage_pct": round((complete / n) * 100.0, 2) if n else 0.0,
        "field_coverage": fields,
    }


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    rows = _rows(state if isinstance(state, dict) else {})
    cov = _coverage(rows)
    if cov["rows_checked"] == 0:
        level = "no_rows"
    elif cov["complete_coverage_pct"] >= 90:
        level = "ok"
    elif cov["complete_coverage_pct"] >= 50:
        level = "partial"
    else:
        level = "needs_improvement"
    examples = []
    for row in rows[-25:]:
        examples.append({field: row.get(field) for field in REQUIRED_FIELDS if row.get(field)})
    return {
        "status": "ok",
        "type": "strategy_label_schema_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "level": level,
        "required_fields": REQUIRED_FIELDS,
        "coverage": cov,
        "recent_label_examples": examples[-10:],
        "recommended_canonical_shape": {
            "strategy_id": "vwap_fvg_reclaim_long_v1",
            "setup_family": "opening_range_fvg",
            "entry_model": "vwap_ema_reclaim",
            "exit_model": "profit_lock_breakeven_v1",
            "risk_model": "standard_trailing_stop_v1",
        },
        "recommendation": "Attach strategy labels at signal creation and carry them through entry, position, exit, journal, and ML rows.",
        "live_authority": False,
    }


def apply(module: Any = None) -> Dict[str, Any]:
    return {"status": "ok", "version": VERSION, "live_authority": False}


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

    if "/paper/strategy-label-schema-status" not in existing:
        flask_app.add_url_rule("/paper/strategy-label-schema-status", "paper_strategy_label_schema_status", status_route)
    if "/paper/setup-label-quality-status" not in existing:
        flask_app.add_url_rule("/paper/setup-label-quality-status", "paper_setup_label_quality_status", status_route)
    if "/paper/setup_label_quality_status" not in existing:
        flask_app.add_url_rule("/paper/setup_label_quality_status", "paper_setup_label_quality_status_legacy", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/strategy-label-schema-status", "/paper/setup-label-quality-status"], "live_authority": False}
