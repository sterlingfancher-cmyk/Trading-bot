"""Integrity-gated MAE/MFE integration bridge.

Only path rows with a symbol-specific lifecycle identity, valid provenance, and
``training_eligible=true`` may enrich execution or shadow-ML records. Legacy
symbol-only matches are removed and quarantined. The bridge is advisory-only and
never changes orders, positions, sizing, strategy thresholds, hard risk, live
authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "mae-mfe-integration-2026-08-06-v2-exact-path-identity"
ENABLED = os.environ.get("MAE_MFE_INTEGRATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


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
        return str(mod.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _refresh_intratrade_paths(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    try:
        import intratrade_path_capture
        section = intratrade_path_capture.update_paths(state, mod)
        return {
            "status": "ok",
            "version": section.get("version"),
            "active_positions_tracked": section.get("active_positions_tracked"),
            "closed_paths_archived": section.get("closed_paths_archived"),
            "invalid_or_quarantined_rows": section.get("invalid_or_quarantined_rows"),
            "training_eligible_rows": section.get("training_eligible_rows"),
        }
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _paths(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    section = _dict(state.get("intratrade_path_capture"))
    active = [row for row in list(_dict(section.get("paths")).values()) if isinstance(row, dict)]
    closed = [row for row in list(_list(section.get("closed_path_archive"))) if isinstance(row, dict)]
    return active + closed[-500:]


def _path_valid(path: Dict[str, Any]) -> bool:
    return bool(
        path.get("path_id")
        and path.get("training_eligible") is True
        and path.get("ml_feature_ready") is True
        and path.get("integrity_status") == "valid"
        and _f(path.get("entry_price"), 0.0) > 0
        and _f(path.get("high_since_entry"), 0.0) >= _f(path.get("low_since_entry"), 0.0) > 0
        and -100.0 < _f(path.get("mae_pct"), 0.0) <= 0.0
        and 0.0 <= _f(path.get("mfe_pct"), 0.0) < 500.0
    )


def _risk_recommendation(path: Dict[str, Any], source: str) -> Dict[str, Any]:
    mae = _f(path.get("mae_pct"), 0.0)
    mfe = _f(path.get("mfe_pct"), 0.0)
    duration = _f(path.get("duration_seconds"), 0.0)
    efficiency = round(mfe / max(0.01, abs(mae)), 4) if (mfe > 0 or mae < 0) else None
    if mae <= -2.0 and mfe < 0.75:
        stop_bias = "tighten_or_exit_review"
    elif mae <= -1.25 and mfe < 1.0:
        stop_bias = "tighten"
    elif mfe >= 2.0 and abs(mae) <= 0.75:
        stop_bias = "allow_room"
    else:
        stop_bias = "standard"
    if mfe >= 3.0 and efficiency is not None and efficiency >= 2.0:
        take_profit_bias = "trail_winner"
    elif mfe >= 1.5 and mae > -0.75:
        take_profit_bias = "partial_profit_review"
    elif mfe < 0.5 and duration > 5400:
        take_profit_bias = "stale_position_review"
    else:
        take_profit_bias = "standard"
    quality = "strong_path" if (mfe >= 1.5 and mae > -0.75) else "weak_path" if (mae <= -1.25 and mfe < 0.75) else "neutral_path"
    return {
        "path_id": path.get("path_id"),
        "symbol": str(path.get("symbol") or "").upper(),
        "side": str(path.get("side") or "long").lower(),
        "source": source,
        "entry_price": round(_f(path.get("entry_price"), 0.0), 6),
        "entry_time": path.get("entry_time"),
        "current_price": round(_f(path.get("current_price"), _f(path.get("exit_price"), 0.0)), 6),
        "high_since_entry": path.get("high_since_entry"),
        "low_since_entry": path.get("low_since_entry"),
        "mae_pct": round(mae, 4),
        "mfe_pct": round(mfe, 4),
        "path_efficiency": efficiency,
        "duration_seconds": int(duration),
        "quality_signal": quality,
        "adaptive_stop_recommendation": stop_bias,
        "dynamic_take_profit_recommendation": take_profit_bias,
        "integrity_status": path.get("integrity_status"),
        "training_eligible": bool(path.get("training_eligible")),
        "calculation_version": path.get("calculation_version"),
        "current_price_source": path.get("current_price_source"),
        "opened_local": path.get("opened_local"),
        "closed_local": path.get("closed_local"),
        "live_authority": False,
    }


def _feature_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    eligible = bool(rec.get("training_eligible") and rec.get("integrity_status") == "valid" and rec.get("path_id"))
    return {
        "path_id": rec.get("path_id"),
        "symbol": rec.get("symbol"),
        "side": rec.get("side"),
        "source": rec.get("source"),
        "entry_price": rec.get("entry_price"),
        "entry_time": rec.get("entry_time"),
        "mae_pct": _f(rec.get("mae_pct"), 0.0),
        "mfe_pct": _f(rec.get("mfe_pct"), 0.0),
        "path_efficiency": rec.get("path_efficiency"),
        "path_quality_signal": rec.get("quality_signal"),
        "adaptive_stop_recommendation": rec.get("adaptive_stop_recommendation"),
        "dynamic_take_profit_recommendation": rec.get("dynamic_take_profit_recommendation"),
        "calculation_version": rec.get("calculation_version"),
        "current_price_source": rec.get("current_price_source"),
        "integrity_status": rec.get("integrity_status"),
        "training_eligible": eligible,
        "ml_feature_ready": eligible,
        "live_authority": False,
    }


def _action(row: Dict[str, Any]) -> str:
    return str(row.get("action") or row.get("type") or "").lower()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or "long").lower()


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper()


def _time(row: Dict[str, Any]) -> float:
    return _f(row.get("time"), _f(row.get("timestamp"), _f(row.get("entry_time"), 0.0)))


def _price(row: Dict[str, Any]) -> float:
    return _f(row.get("price"), _f(row.get("entry_price"), _f(row.get("fill_price"), 0.0)))


def _path_id(symbol: str, side: str, entry_time: float, entry_price: float) -> str:
    return f"{symbol}|{side}|{int(entry_time or 0)}|{entry_price:.6f}"


def _execution_instances(trades: List[Any]) -> Dict[int, str]:
    """Map row identity to an exact preceding-entry path identity."""
    open_entries: Dict[Tuple[str, str], Tuple[float, float, str]] = {}
    mapping: Dict[int, str] = {}
    rows = [row for row in list(trades) if isinstance(row, dict)]
    rows.sort(key=_time)
    for row in rows:
        symbol = _symbol(row)
        side = _side(row)
        if not symbol:
            continue
        action = _action(row)
        key = (symbol, side)
        if action in {"entry", "buy", "open", "short"}:
            entry_time = _time(row)
            entry_price = _price(row)
            if entry_time > 0 and entry_price > 0:
                identity = _path_id(symbol, side, entry_time, entry_price)
                open_entries[key] = (entry_time, entry_price, identity)
                mapping[id(row)] = identity
                row["execution_path_id"] = identity
        elif action in {"exit", "sell", "close", "partial_exit", "trim"} or row.get("pnl_pct") is not None:
            entry = open_entries.get(key)
            if entry:
                mapping[id(row)] = entry[2]
                row["execution_path_id"] = entry[2]
                if action not in {"partial_exit", "trim"}:
                    open_entries.pop(key, None)
    return mapping


def _quarantine_existing_feature(row: Dict[str, Any], reason: str) -> bool:
    existing = row.get("mae_mfe_features")
    had = isinstance(existing, dict) and bool(existing)
    if had:
        row["mae_mfe_features_quarantined"] = dict(existing)
    row["mae_mfe_features"] = {
        "ml_feature_ready": False,
        "training_eligible": False,
        "integrity_status": "quarantined",
        "quarantine_reason": reason,
        "live_authority": False,
    }
    row["mae_mfe_feature_enriched"] = False
    row["mae_mfe_quarantined"] = True
    return had


def integrate(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    refresh = _refresh_intratrade_paths(state, mod)
    paths = _paths(state)
    valid_paths = [path for path in paths if _path_valid(path)]
    invalid_paths = [path for path in paths if not _path_valid(path)]
    recs = [_risk_recommendation(path, "closed_path" if path.get("closed_local") else "active_path") for path in valid_paths]
    features = [_feature_row(rec) for rec in recs]
    by_path_id = {str(row.get("path_id")): row for row in features if row.get("path_id")}

    trades = [row for row in list(_list(state.get("trades"))) if isinstance(row, dict)]
    execution_map = _execution_instances(trades)
    quarantined_rows = 0
    trade_rows_enriched = 0
    for row in trades:
        identity = execution_map.get(id(row)) or str(row.get("execution_path_id") or "")
        feature = by_path_id.get(identity)
        if feature:
            row["mae_mfe_features"] = dict(feature)
            row["mae_mfe_feature_enriched"] = True
            row["mae_mfe_quarantined"] = False
            trade_rows_enriched += 1
        else:
            if _quarantine_existing_feature(row, "no_exact_valid_execution_path_match"):
                quarantined_rows += 1

    ml2 = _dict(state.get("ml_phase2"))
    dataset = [row for row in list(_list(ml2.get("dataset"))) if isinstance(row, dict)]
    ml_rows_enriched = 0
    ml_rows_quarantined = 0
    for row in dataset:
        identity = str(row.get("execution_path_id") or row.get("path_id") or "")
        feature = by_path_id.get(identity)
        executed = bool(row.get("executed") or row.get("execution_action") or row.get("trade_executed"))
        if executed and feature:
            row["mae_mfe_features"] = dict(feature)
            row["mae_mfe_feature_enriched"] = True
            row["mae_mfe_quarantined"] = False
            ml_rows_enriched += 1
        else:
            if _quarantine_existing_feature(row, "shadow_row_lacks_exact_valid_execution_path"):
                ml_rows_quarantined += 1

    tq = state.setdefault("trade_quality_telemetry", {})
    tq["mae_mfe_integration"] = {
        "version": VERSION,
        "valid_path_rows": len(valid_paths),
        "invalid_or_quarantined_path_rows": len(invalid_paths),
        "ml_rows_enriched": ml_rows_enriched,
        "ml_rows_quarantined": ml_rows_quarantined,
        "trade_rows_enriched": trade_rows_enriched,
        "trade_rows_quarantined": quarantined_rows,
        "last_updated_local": _now(mod),
        "live_authority": False,
    }

    section = state.setdefault("mae_mfe_integration", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "last_error": None,
        "intratrade_refresh": refresh,
        "valid_recommendations": recs[-25:],
        "valid_features": features[-25:],
        "valid_path_rows": len(valid_paths),
        "invalid_or_quarantined_path_rows": len(invalid_paths),
        "ml_rows_enriched": ml_rows_enriched,
        "ml_rows_quarantined": ml_rows_quarantined,
        "trade_rows_enriched": trade_rows_enriched,
        "trade_rows_quarantined": quarantined_rows,
        "mae_mfe_complete": bool(valid_paths),
        "regression_guards": {
            "symbol_only_feature_matching_disabled": True,
            "exact_execution_path_id_required": True,
            "invalid_paths_never_training_eligible": True,
            "dataset_iteration_uses_snapshot": True,
            "legacy_contaminated_features_quarantined": True,
        },
    })
    return section


def status_payload(mod: Any = None, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = _dict(state.get("mae_mfe_integration"))
    path_section = _dict(state.get("intratrade_path_capture"))
    last_error = section.get("last_error") or path_section.get("last_error")
    invalid = int(section.get("invalid_or_quarantined_path_rows") or path_section.get("invalid_or_quarantined_rows") or 0)
    ml_quarantined = int(section.get("ml_rows_quarantined") or 0)
    return {
        "status": "ok",
        "overall": "warn" if last_error else "pass",
        "type": "mae_mfe_integrity_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "valid_path_rows": int(section.get("valid_path_rows") or 0),
        "invalid_or_quarantined_path_rows": invalid,
        "ml_rows_enriched": int(section.get("ml_rows_enriched") or 0),
        "ml_rows_quarantined": ml_quarantined,
        "trade_rows_enriched": int(section.get("trade_rows_enriched") or 0),
        "trade_rows_quarantined": int(section.get("trade_rows_quarantined") or 0),
        "last_error": last_error,
        "regression_guards": section.get("regression_guards") or {},
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = integrate(state, mod) if ENABLED else _dict(state.get("mae_mfe_integration"))
    out = status_payload(mod, state)
    out.update({
        "type": "mae_mfe_integration_status",
        "mae_mfe_complete": section.get("mae_mfe_complete", False),
        "valid_recommendations": section.get("valid_recommendations", []),
    })
    return out


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
                        integrate(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("mae_mfe_integration", {})["last_error"] = f"{type(exc).__name__}: {exc}"
                    except Exception:
                        pass
                return original(state)
            patched_save_state._mae_mfe_integration_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "MAE_MFE_INTEGRATION_VERSION", VERSION)
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

    def integration_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    def integrity_route():
        state, mod = _load_state(module)
        return jsonify(status_payload(mod, state))

    for path, endpoint, view in (
        ("/paper/mae-mfe-integration-status", "paper_mae_mfe_integration_status", integration_route),
        ("/paper/mae-mfe-status", "paper_mae_mfe_status", integration_route),
        ("/paper/mae-mfe-integrity-status", "paper_mae_mfe_integrity_status", integrity_route),
    ):
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, view)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "live_authority": False}
