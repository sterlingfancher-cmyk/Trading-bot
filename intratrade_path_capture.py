"""Intratrade price-path capture for MAE/MFE learning.

Shadow/advisory only. This module records high/low/current price behavior for
open positions so MAE/MFE can become real telemetry instead of placeholder
fields. It does not place trades, close trades, change position sizing, or
override risk controls.

Routes:
- /paper/intratrade-path-status
- /paper/position-path-status

State section:
- state["intratrade_path_capture"]
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "intratrade-path-capture-2026-05-16"
ENABLED = os.environ.get("INTRATRADE_PATH_CAPTURE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
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


def _epoch_now() -> float:
    try:
        return dt.datetime.now().timestamp()
    except Exception:
        return 0.0


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _positions(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    positions = state.get("positions")
    if isinstance(positions, dict):
        return {str(sym).upper(): pos for sym, pos in positions.items() if isinstance(pos, dict)}
    return {}


def _entry_price(pos: Dict[str, Any]) -> float:
    return _f(pos.get("entry_price"), _f(pos.get("avg_entry_price"), _f(pos.get("price"), _f(pos.get("cost_basis"), 0.0))))


def _side(pos: Dict[str, Any]) -> str:
    return str(pos.get("side") or pos.get("direction") or "long").lower()


def _shares(pos: Dict[str, Any]) -> float:
    return _f(pos.get("shares"), _f(pos.get("qty"), _f(pos.get("quantity"), 0.0)))


def _entry_time(pos: Dict[str, Any]) -> float | None:
    for key in ("entry_time", "opened_time", "time", "timestamp"):
        value = pos.get(key)
        if value is not None:
            return _f(value, 0.0)
    return None


def _safe_latest_price(mod: Any, symbol: str, pos: Dict[str, Any]) -> float:
    for fn_name in ("latest_price", "get_latest_price", "safe_latest_price"):
        try:
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                price = _f(fn(symbol), 0.0)
                if price > 0:
                    return price
        except Exception:
            pass
    for key in ("last_price", "current_price", "market_price", "price"):
        price = _f(pos.get(key), 0.0)
        if price > 0:
            return price
    return _entry_price(pos)


def _pct_for_side(current: float, entry: float, side: str) -> float:
    if entry <= 0 or current <= 0:
        return 0.0
    if side == "short":
        return (entry / current - 1.0) * 100.0
    return (current / entry - 1.0) * 100.0


def update_paths(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    mod = mod or _module()
    section = state.setdefault("intratrade_path_capture", {})
    section.setdefault("paths", {})
    paths = _dict(section.get("paths"))
    section["paths"] = paths

    now_epoch = _epoch_now()
    now_text = _now(mod)
    positions = _positions(state)
    active_symbols = set(positions.keys())
    updated = 0

    for symbol, pos in positions.items():
        entry = _entry_price(pos)
        if entry <= 0:
            continue
        side = _side(pos)
        price = _safe_latest_price(mod, symbol, pos) if mod is not None else _f(pos.get("price"), entry)
        if price <= 0:
            price = entry
        path = _dict(paths.get(symbol))
        if not path:
            path = {
                "symbol": symbol,
                "side": side,
                "entry_price": round(entry, 4),
                "shares": round(_shares(pos), 6),
                "entry_time": _entry_time(pos),
                "opened_local": pos.get("opened_local") or pos.get("entry_local") or now_text,
                "high_since_entry": round(max(entry, price), 4),
                "low_since_entry": round(min(entry, price), 4),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,
                "time_to_mfe_seconds": 0,
                "time_to_mae_seconds": 0,
                "created_local": now_text,
            }
        prior_high = _f(path.get("high_since_entry"), entry)
        prior_low = _f(path.get("low_since_entry"), entry)
        new_high = max(prior_high, price)
        new_low = min(prior_low, price)
        entry_time = path.get("entry_time")
        duration = 0
        if entry_time:
            duration = max(0, int(now_epoch - _f(entry_time, now_epoch)))

        if side == "short":
            favorable_price = new_low
            adverse_price = new_high
        else:
            favorable_price = new_high
            adverse_price = new_low
        mfe = _pct_for_side(favorable_price, entry, side)
        mae = _pct_for_side(adverse_price, entry, side)

        if new_high != prior_high or new_low != prior_low:
            if abs(mfe) >= abs(_f(path.get("mfe_pct"), 0.0)):
                path["time_to_mfe_seconds"] = duration
            if abs(mae) >= abs(_f(path.get("mae_pct"), 0.0)):
                path["time_to_mae_seconds"] = duration

        path.update({
            "symbol": symbol,
            "side": side,
            "entry_price": round(entry, 4),
            "current_price": round(price, 4),
            "high_since_entry": round(new_high, 4),
            "low_since_entry": round(new_low, 4),
            "mfe_pct": round(max(0.0, mfe), 4),
            "mae_pct": round(min(0.0, mae), 4),
            "duration_seconds": duration,
            "last_updated_local": now_text,
            "vwap_drift_pct": path.get("vwap_drift_pct"),
            "ema_hold_status": path.get("ema_hold_status"),
            "live_authority": False,
        })
        paths[symbol] = path
        updated += 1

    closed = [sym for sym in list(paths.keys()) if sym not in active_symbols]
    archive = section.setdefault("closed_path_archive", [])
    for sym in closed:
        item = paths.pop(sym)
        if isinstance(item, dict):
            item["closed_local"] = now_text
            archive.append(item)
    section["closed_path_archive"] = archive[-500:]

    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": now_text,
        "active_positions_tracked": len(paths),
        "closed_paths_archived": len(section.get("closed_path_archive", [])),
        "updated_count": updated,
        "recommended_actions": [
            "Use intratrade path data to convert MAE/MFE telemetry from placeholder to real outcome labels.",
            "Keep this advisory only until enough path observations exist across multiple regimes.",
            "Next step after enough path data: feed MAE/MFE into trade-quality and ML readiness scoring.",
        ],
    })
    return section


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = update_paths(state, mod) if ENABLED else _dict(state.get("intratrade_path_capture"))
    paths = _dict(section.get("paths"))
    archive = _list(section.get("closed_path_archive"))
    return {
        "status": "ok",
        "type": "intratrade_path_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "active_positions_tracked": len(paths),
        "closed_paths_archived": len(archive),
        "active_paths": list(paths.values())[-25:],
        "closed_path_tail": archive[-25:],
        "recommended_actions": section.get("recommended_actions") or [],
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
                        update_paths(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("intratrade_path_capture", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._intratrade_path_capture_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "INTRATRADE_PATH_CAPTURE_VERSION", VERSION)
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

    if "/paper/intratrade-path-status" not in existing:
        flask_app.add_url_rule("/paper/intratrade-path-status", "paper_intratrade_path_status", status_route)
    if "/paper/position-path-status" not in existing:
        flask_app.add_url_rule("/paper/position-path-status", "paper_position_path_status", status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/intratrade-path-status", "/paper/position-path-status"], "live_authority": False}
