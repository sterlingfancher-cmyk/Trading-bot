"""MAE/MFE integration bridge.

Advisory-only bridge that feeds intratrade path telemetry into:
- trade-quality scoring metadata
- adaptive stop recommendations
- dynamic take-profit recommendations
- future ML ranking features

This module does not place orders, modify positions, close trades, change
allocation, or override risk controls. It writes recommendations and feature
metadata only.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "mae-mfe-integration-bridge-2026-05-16-route-fix"
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


def _paths(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    section = _dict(state.get("intratrade_path_capture"))
    return {str(k).upper(): v for k, v in _dict(section.get("paths")).items() if isinstance(v, dict)}


def _closed_paths(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _list(_dict(state.get("intratrade_path_capture")).get("closed_path_archive")) if isinstance(row, dict)]


def _risk_recommendation(path: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(path.get("symbol") or "").upper()
    side = str(path.get("side") or "long").lower()
    mae = _f(path.get("mae_pct"), 0.0)
    mfe = _f(path.get("mfe_pct"), 0.0)
    duration = _f(path.get("duration_seconds"), 0.0)
    current = _f(path.get("current_price"), 0.0)
    entry = _f(path.get("entry_price"), 0.0)

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

    quality_signal = "strong_path" if (mfe >= 1.5 and mae > -0.75) else "weak_path" if (mae <= -1.25 and mfe < 0.75) else "neutral_path"
    return {
        "symbol": symbol,
        "side": side,
        "entry_price": round(entry, 4) if entry else None,
        "current_price": round(current, 4) if current else None,
        "mae_pct": round(mae, 4),
        "mfe_pct": round(mfe, 4),
        "path_efficiency": efficiency,
        "duration_seconds": int(duration),
        "quality_signal": quality_signal,
        "adaptive_stop_recommendation": stop_bias,
        "dynamic_take_profit_recommendation": take_profit_bias,
        "live_authority": False,
        "note": "Recommendation only; live order logic is unchanged.",
    }


def _feature_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    mae = _f(rec.get("mae_pct"), 0.0)
    mfe = _f(rec.get("mfe_pct"), 0.0)
    eff = rec.get("path_efficiency")
    return {
        "symbol": rec.get("symbol"),
        "side": rec.get("side"),
        "mae_pct": mae,
        "mfe_pct": mfe,
        "path_efficiency": eff,
        "path_quality_signal": rec.get("quality_signal"),
        "adaptive_stop_recommendation": rec.get("adaptive_stop_recommendation"),
        "dynamic_take_profit_recommendation": rec.get("dynamic_take_profit_recommendation"),
        "ml_feature_ready": bool(mfe != 0.0 or mae != 0.0),
    }


def integrate(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    active_paths = _paths(state)
    active_recs = [_risk_recommendation(path) for path in active_paths.values()]
    closed_features = [_feature_row(_risk_recommendation(path)) for path in _closed_paths(state)[-100:]]
    active_features = [_feature_row(rec) for rec in active_recs]

    ml2 = _dict(state.get("ml_phase2"))
    dataset = _list(ml2.get("dataset"))
    by_symbol = {str(row.get("symbol") or "").upper(): row for row in active_features + closed_features if isinstance(row, dict)}
    enriched = 0
    for row in dataset:
        if not isinstance(row, dict):
            continue
        feature = by_symbol.get(str(row.get("symbol") or "").upper())
        if feature:
            row.setdefault("mae_mfe_features", {}).update(feature)
            row["mae_mfe_feature_enriched"] = True
            enriched += 1

    tq = state.setdefault("trade_quality_telemetry", {})
    tq["mae_mfe_integration"] = {
        "version": VERSION,
        "active_recommendations_count": len(active_recs),
        "ml_rows_enriched": enriched,
        "last_updated_local": _now(mod),
        "live_authority": False,
    }

    section = state.setdefault("mae_mfe_integration", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "active_recommendations": active_recs[-25:],
        "active_features": active_features[-25:],
        "closed_features_tail": closed_features[-25:],
        "ml_rows_enriched": enriched,
        "summary": {
            "active_positions_with_path": len(active_recs),
            "strong_path_count": sum(1 for r in active_recs if r.get("quality_signal") == "strong_path"),
            "weak_path_count": sum(1 for r in active_recs if r.get("quality_signal") == "weak_path"),
            "trail_winner_count": sum(1 for r in active_recs if r.get("dynamic_take_profit_recommendation") == "trail_winner"),
            "tighten_stop_count": sum(1 for r in active_recs if str(r.get("adaptive_stop_recommendation", "")).startswith("tighten")),
        },
        "recommended_actions": [
            "Keep stop/take-profit outputs advisory until path telemetry is validated across enough trades.",
            "Use MAE/MFE features to improve ML ranking confidence, not execution authority yet.",
            "Promote only after Phase 3A readiness gates pass and walk-forward validation confirms improvement.",
        ],
    })
    return section


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = integrate(state, mod) if ENABLED else _dict(state.get("mae_mfe_integration"))
    return {
        "status": "ok",
        "type": "mae_mfe_integration_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "summary": section.get("summary"),
        "active_recommendations_count": len(_list(section.get("active_recommendations"))),
        "ml_rows_enriched": section.get("ml_rows_enriched", 0),
        "active_recommendations": section.get("active_recommendations", []),
        "recommended_actions": section.get("recommended_actions", []),
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
                        integrate(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("mae_mfe_integration", {})["last_error"] = str(exc)
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

    def status_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    if "/paper/mae-mfe-integration-status" not in existing:
        flask_app.add_url_rule("/paper/mae-mfe-integration-status", "paper_mae_mfe_integration_status", status_route)
    if "/paper/adaptive-exit-recommendations" not in existing:
        flask_app.add_url_rule("/paper/adaptive-exit-recommendations", "paper_adaptive_exit_recommendations", status_route)
    if "/paper/adaptive_exit_recommendations" not in existing:
        flask_app.add_url_rule("/paper/adaptive_exit_recommendations", "paper_adaptive_exit_recommendations_legacy", status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/mae-mfe-integration-status", "/paper/adaptive-exit-recommendations"], "live_authority": False}
