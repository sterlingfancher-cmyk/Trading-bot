"""Canonical strategy-label propagation layer.

Advisory/metadata only. Backfills and propagates canonical strategy-label
fields across trades, positions, ML datasets, and trade-quality telemetry so
future strategy promotion/demotion has stable labels to evaluate.

This module does not change signals, orders, allocation, stops, exits, or risk
controls.

Routes:
- /paper/strategy-label-propagation-status
- /paper/canonical-strategy-label-status
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from typing import Any, Dict, List, Tuple

VERSION = "strategy-label-propagation-2026-05-16"
ENABLED = os.environ.get("STRATEGY_LABEL_PROPAGATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
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


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _slug(text: Any) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "unknown"


def _field_text(row: Dict[str, Any]) -> str:
    parts = []
    for key in ("strategy", "strategy_id", "setup_family", "entry_model", "exit_model", "risk_model", "reason", "entry_reason", "exit_reason", "market_mode", "side", "journal_source"):
        value = row.get(key)
        if value is not None:
            parts.append(str(value).lower())
    return " ".join(parts)


def _infer_setup_family(row: Dict[str, Any]) -> str:
    text = _field_text(row)
    if "fvg" in text or "fair_value" in text or "opening_range" in text:
        return "opening_range_fvg"
    if "vwap" in text and "ema" in text:
        return "vwap_ema_reclaim"
    if "vwap" in text:
        return "vwap_reclaim"
    if "classic" in text:
        return "classic_signal"
    if "risk_reward" in text or "fib" in text or "fibonacci" in text:
        return "risk_reward_fibonacci"
    if "rotation" in text:
        return "rotation_review"
    if "ml" in text:
        return "ml_shadow_signal"
    if "short" in text:
        return "short_momentum_guarded"
    if row.get("action") == "exit" or row.get("exit_reason"):
        return "legacy_exit_observation"
    return "legacy_momentum_signal"


def _infer_entry_model(row: Dict[str, Any], setup_family: str) -> str:
    text = _field_text(row)
    if "vwap" in text and "ema" in text:
        return "vwap_ema_confirmation"
    if setup_family == "opening_range_fvg":
        return "opening_range_fvg_reclaim"
    if "classic" in text:
        return "classic_signal_hard_gate"
    if "pullback" in text or "ma20" in text:
        return "ma20_pullback_reclaim"
    if "short" in text:
        return "short_entry_guarded"
    return "legacy_score_entry"


def _infer_exit_model(row: Dict[str, Any]) -> str:
    text = _field_text(row)
    if "profit_lock" in text and "breakeven" in text:
        return "profit_lock_breakeven"
    if "stop" in text:
        return "stop_loss_or_trailing_stop"
    if "partial" in text:
        return "partial_profit_take"
    if "rotation" in text:
        return "rotation_exit_review"
    if "exit" in text:
        return _slug(row.get("exit_reason") or row.get("reason") or "legacy_exit")[:80]
    return "open_position_exit_pending"


def _infer_risk_model(row: Dict[str, Any]) -> str:
    text = _field_text(row)
    if "self_defense" in text:
        return "self_defense_risk_control"
    if "fvg" in text or "opening_range" in text:
        return "opening_range_fvg_pilot_guard"
    if "risk_reward" in text or "fib" in text:
        return "risk_reward_structure_guard"
    if "classic" in text:
        return "classic_signal_hard_gate"
    return "standard_position_risk_control"


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower()


def _strategy_id(setup_family: str, entry_model: str, exit_model: str, risk_model: str, side: str) -> str:
    return f"{_slug(setup_family)}__{_slug(entry_model)}__{_slug(exit_model)}__{_slug(risk_model)}__{_slug(side)}__v1"[:180]


def label_row(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    before = {k: row.get(k) for k in REQUIRED_FIELDS}
    setup_family = row.get("setup_family") or _infer_setup_family(row)
    entry_model = row.get("entry_model") or _infer_entry_model(row, str(setup_family))
    exit_model = row.get("exit_model") or _infer_exit_model(row)
    risk_model = row.get("risk_model") or _infer_risk_model(row)
    side = _side(row)
    strategy_id = row.get("strategy_id") or _strategy_id(str(setup_family), str(entry_model), str(exit_model), str(risk_model), side)
    row.setdefault("setup_family", setup_family)
    row.setdefault("entry_model", entry_model)
    row.setdefault("exit_model", exit_model)
    row.setdefault("risk_model", risk_model)
    row.setdefault("strategy_id", strategy_id)
    row.setdefault("strategy_label_source", "strategy_label_propagation")
    row.setdefault("strategy_label_version", VERSION)
    after = {k: row.get(k) for k in REQUIRED_FIELDS}
    return before != after


def _iter_label_targets(state: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    targets: List[Tuple[str, Dict[str, Any]]] = []
    for idx, row in enumerate(_list(state.get("trades"))):
        if isinstance(row, dict):
            targets.append((f"trades[{idx}]", row))
    positions = state.get("positions")
    if isinstance(positions, dict):
        for sym, row in positions.items():
            if isinstance(row, dict):
                row.setdefault("symbol", str(sym).upper())
                targets.append((f"positions.{sym}", row))
    ml2 = _dict(state.get("ml_phase2"))
    for idx, row in enumerate(_list(ml2.get("dataset"))):
        if isinstance(row, dict):
            targets.append((f"ml_phase2.dataset[{idx}]", row))
    tq = _dict(state.get("trade_quality_telemetry"))
    for key in ("recent_quality_tail", "recent_quality_rows"):
        for idx, row in enumerate(_list(tq.get(key))):
            if isinstance(row, dict):
                targets.append((f"trade_quality_telemetry.{key}[{idx}]", row))
    return targets


def propagate(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    changed = 0
    targets = _iter_label_targets(state)
    examples = []
    for path, row in targets:
        did = label_row(row)
        changed += 1 if did else 0
        if len(examples) < 15:
            examples.append({"path": path, "symbol": row.get("symbol"), "strategy_id": row.get("strategy_id"), "setup_family": row.get("setup_family"), "entry_model": row.get("entry_model"), "exit_model": row.get("exit_model"), "risk_model": row.get("risk_model")})
    complete = 0
    partial = 0
    missing = 0
    for _, row in targets:
        present = [bool(row.get(field)) for field in REQUIRED_FIELDS]
        if all(present):
            complete += 1
        elif any(present):
            partial += 1
        else:
            missing += 1
    total = len(targets)
    section = state.setdefault("strategy_label_propagation", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "targets_checked": total,
        "rows_changed": changed,
        "complete_rows": complete,
        "partial_rows": partial,
        "missing_rows": missing,
        "complete_coverage_pct": round((complete / total) * 100.0, 2) if total else 0.0,
        "recent_examples": examples,
        "canonical_fields": REQUIRED_FIELDS,
        "recommendation": "Use these canonical labels for future walk-forward strategy rotation and promotion/demotion scoring.",
    })
    return section


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = propagate(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_label_propagation") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "type": "strategy_label_propagation_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "targets_checked": section.get("targets_checked"),
        "rows_changed": section.get("rows_changed"),
        "complete_rows": section.get("complete_rows"),
        "partial_rows": section.get("partial_rows"),
        "missing_rows": section.get("missing_rows"),
        "complete_coverage_pct": section.get("complete_coverage_pct"),
        "recent_examples": section.get("recent_examples", []),
        "recommendation": section.get("recommendation"),
    }


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_authority": False}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                try:
                    if ENABLED and isinstance(state, dict):
                        propagate(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("strategy_label_propagation", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._strategy_label_propagation_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "STRATEGY_LABEL_PROPAGATION_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "live_authority": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    apply(module)
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

    if "/paper/strategy-label-propagation-status" not in existing:
        flask_app.add_url_rule("/paper/strategy-label-propagation-status", "paper_strategy_label_propagation_status", status_route)
    if "/paper/canonical-strategy-label-status" not in existing:
        flask_app.add_url_rule("/paper/canonical-strategy-label-status", "paper_canonical_strategy_label_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/strategy-label-propagation-status", "/paper/canonical-strategy-label-status"], "live_authority": False}
