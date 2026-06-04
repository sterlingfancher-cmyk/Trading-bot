"""MAE/MFE integration bridge.

Advisory-only bridge that refreshes real intratrade path telemetry and feeds it
into:
- trade-quality scoring metadata
- adaptive stop recommendations
- dynamic take-profit recommendations
- future ML ranking features
- Phase 2.5 readiness gates

This module does not place orders, modify positions, close trades, change
allocation, or override risk controls. It writes recommendations and feature
metadata only. It never invents synthetic MAE/MFE values.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "mae-mfe-integration-2026-06-04-telemetry-complete"
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


def _refresh_intratrade_paths(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    try:
        import intratrade_path_capture
        if hasattr(intratrade_path_capture, "update_paths"):
            section = intratrade_path_capture.update_paths(state, mod)
            return {"status": "ok", "version": section.get("version"), "active_positions_tracked": section.get("active_positions_tracked"), "closed_paths_archived": section.get("closed_paths_archived")}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "not_available"}


def _paths(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    section = _dict(state.get("intratrade_path_capture"))
    return {str(k).upper(): v for k, v in _dict(section.get("paths")).items() if isinstance(v, dict)}


def _closed_paths(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _list(_dict(state.get("intratrade_path_capture")).get("closed_path_archive")) if isinstance(row, dict)]


def _path_key(path: Dict[str, Any]) -> Tuple[str, str]:
    return (str(path.get("symbol") or "").upper(), str(path.get("side") or "long").lower())


def _risk_recommendation(path: Dict[str, Any], source: str = "active_path") -> Dict[str, Any]:
    symbol = str(path.get("symbol") or "").upper()
    side = str(path.get("side") or "long").lower()
    mae = _f(path.get("mae_pct"), 0.0)
    mfe = _f(path.get("mfe_pct"), 0.0)
    duration = _f(path.get("duration_seconds"), 0.0)
    current = _f(path.get("current_price"), _f(path.get("exit_price"), 0.0))
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
        "source": source,
        "entry_price": round(entry, 4) if entry else None,
        "current_price": round(current, 4) if current else None,
        "mae_pct": round(mae, 4),
        "mfe_pct": round(mfe, 4),
        "path_efficiency": efficiency,
        "duration_seconds": int(duration),
        "quality_signal": quality_signal,
        "adaptive_stop_recommendation": stop_bias,
        "dynamic_take_profit_recommendation": take_profit_bias,
        "opened_local": path.get("opened_local"),
        "closed_local": path.get("closed_local"),
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
        "source": rec.get("source"),
        "mae_pct": mae,
        "mfe_pct": mfe,
        "path_efficiency": eff,
        "path_quality_signal": rec.get("quality_signal"),
        "adaptive_stop_recommendation": rec.get("adaptive_stop_recommendation"),
        "dynamic_take_profit_recommendation": rec.get("dynamic_take_profit_recommendation"),
        "ml_feature_ready": bool(mfe != 0.0 or mae != 0.0),
        "live_authority": False,
    }


def _trade_outcome_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _list(state.get("trades")):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        has_pnl = row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None
        if action in {"exit", "sell", "close"} or "exit" in reason or "stop" in reason or has_pnl:
            rows.append(row)
    return rows


def _build_feature_index(active_features: List[Dict[str, Any]], closed_features: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in closed_features + active_features:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("symbol") or "").upper(), str(row.get("side") or "long").lower())
        if key[0]:
            by_key[key] = row
    return by_key


def integrate(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    refresh = _refresh_intratrade_paths(state, mod)
    active_paths = _paths(state)
    closed_path_rows = _closed_paths(state)
    active_recs = [_risk_recommendation(path, "active_path") for path in active_paths.values()]
    closed_recs = [_risk_recommendation(path, "closed_path") for path in closed_path_rows[-250:]]
    closed_features = [_feature_row(rec) for rec in closed_recs]
    active_features = [_feature_row(rec) for rec in active_recs]
    by_symbol_side = _build_feature_index(active_features, closed_features)

    ml2 = _dict(state.get("ml_phase2"))
    dataset = _list(ml2.get("dataset"))
    enriched = 0
    rows_with_feature_ready = 0
    for row in dataset:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("symbol") or "").upper(), str(row.get("side") or "long").lower())
        feature = by_symbol_side.get(key) or by_symbol_side.get((key[0], "long"))
        if feature:
            row.setdefault("mae_mfe_features", {}).update(feature)
            row["mae_mfe_feature_enriched"] = True
            enriched += 1
            if feature.get("ml_feature_ready"):
                rows_with_feature_ready += 1

    trade_rows_enriched = 0
    for row in _trade_outcome_rows(state):
        sym = str(row.get("symbol") or row.get("ticker") or "").upper()
        side = str(row.get("side") or "long").lower()
        feature = by_symbol_side.get((sym, side)) or by_symbol_side.get((sym, "long"))
        if feature:
            row.setdefault("mae_mfe_features", {}).update(feature)
            row["mae_mfe_feature_enriched"] = True
            trade_rows_enriched += 1

    path_rows_available = len(active_features) + len(closed_features)
    ready_features = [r for r in active_features + closed_features if r.get("ml_feature_ready")]
    tq = state.setdefault("trade_quality_telemetry", {})
    tq["mae_mfe_integration"] = {
        "version": VERSION,
        "active_recommendations_count": len(active_recs),
        "closed_recommendations_count": len(closed_recs),
        "path_rows_available": path_rows_available,
        "ready_feature_rows": len(ready_features),
        "ml_rows_enriched": enriched,
        "trade_rows_enriched": trade_rows_enriched,
        "last_updated_local": _now(mod),
        "live_authority": False,
    }

    section = state.setdefault("mae_mfe_integration", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "intratrade_refresh": refresh,
        "active_recommendations": active_recs[-25:],
        "closed_recommendations_tail": closed_recs[-25:],
        "active_features": active_features[-25:],
        "closed_features_tail": closed_features[-25:],
        "ml_rows_enriched": enriched,
        "ml_rows_with_ready_features": rows_with_feature_ready,
        "trade_rows_enriched": trade_rows_enriched,
        "telemetry_rows_available": path_rows_available,
        "mae_mfe_complete": bool(len(ready_features) > 0),
        "summary": {
            "active_positions_with_path": len(active_recs),
            "closed_paths_with_path": len(closed_recs),
            "telemetry_rows_available": path_rows_available,
            "ready_feature_rows": len(ready_features),
            "strong_path_count": sum(1 for r in active_recs if r.get("quality_signal") == "strong_path"),
            "weak_path_count": sum(1 for r in active_recs if r.get("quality_signal") == "weak_path"),
            "trail_winner_count": sum(1 for r in active_recs if r.get("dynamic_take_profit_recommendation") == "trail_winner"),
            "tighten_stop_count": sum(1 for r in active_recs if str(r.get("adaptive_stop_recommendation", "")).startswith("tighten")),
            "ml_rows_enriched": enriched,
            "trade_rows_enriched": trade_rows_enriched,
        },
        "recommended_actions": [
            "Keep stop/take-profit outputs advisory until path telemetry is validated across enough trades.",
            "Use MAE/MFE features to improve ML ranking confidence, not execution authority yet.",
            "Review weak_path and tighten_stop candidates before changing stop or redeployment rules.",
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
        "mae_mfe_complete": section.get("mae_mfe_complete", False),
        "summary": section.get("summary"),
        "active_recommendations_count": len(_list(section.get("active_recommendations"))),
        "closed_recommendations_count": len(_list(section.get("closed_recommendations_tail"))),
        "telemetry_rows_available": section.get("telemetry_rows_available", 0),
        "ml_rows_enriched": section.get("ml_rows_enriched", 0),
        "trade_rows_enriched": section.get("trade_rows_enriched", 0),
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


try:
    apply(_module())
except Exception:
    pass
