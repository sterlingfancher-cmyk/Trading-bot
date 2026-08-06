"""Symbol-specific intratrade path capture for MAE/MFE research.

The capture is advisory-only. It records path observations for open positions,
but rejects prices that are inconsistent with the position's own symbol-specific
price, entry basis, or lifecycle identity. A new position fingerprint always
starts a new path. Invalid historical paths are preserved as quarantined evidence
and are never marked training eligible.

No orders, exits, sizing, strategy thresholds, risk controls, live authority, or
ML authority are changed.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "intratrade-path-capture-2026-08-06-v2-symbol-isolated"
CALCULATION_VERSION = "entry-relative-mae-mfe-v2"
ENABLED = os.environ.get("INTRATRADE_PATH_CAPTURE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
MAX_OBSERVATION_MOVE_PCT = max(10.0, float(os.environ.get("INTRATRADE_MAX_OBSERVATION_MOVE_PCT", "50")))
MAX_SOURCE_DIVERGENCE_PCT = max(2.0, float(os.environ.get("INTRATRADE_MAX_SOURCE_DIVERGENCE_PCT", "15")))
MIN_VALID_OBSERVATIONS_FOR_TRAINING = max(2, int(os.environ.get("INTRATRADE_MIN_VALID_OBSERVATIONS", "3")))
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
        return {str(sym).upper(): pos for sym, pos in list(positions.items()) if isinstance(pos, dict)}
    return {}


def _entry_price(pos: Dict[str, Any]) -> float:
    return _f(pos.get("entry"), _f(pos.get("entry_price"), _f(pos.get("avg_entry_price"), _f(pos.get("cost_basis"), 0.0))))


def _side(pos: Dict[str, Any]) -> str:
    return str(pos.get("side") or pos.get("direction") or "long").lower()


def _shares(pos: Dict[str, Any]) -> float:
    return _f(pos.get("shares"), _f(pos.get("qty"), _f(pos.get("quantity"), 0.0)))


def _entry_time(pos: Dict[str, Any]) -> float | None:
    for key in ("entry_time", "opened_time", "time", "timestamp"):
        value = pos.get(key)
        if value is not None:
            number = _f(value, 0.0)
            return number if number > 0 else None
    return None


def _path_id(symbol: str, side: str, entry_time: float | None, entry_price: float) -> str:
    return f"{symbol}|{side}|{int(entry_time or 0)}|{entry_price:.6f}"


def _position_price(pos: Dict[str, Any]) -> Tuple[float, str]:
    for key in ("last_price", "current_price", "market_price", "mark_price"):
        price = _f(pos.get(key), 0.0)
        if price > 0:
            return price, f"position.{key}"
    return 0.0, ""


def _move_pct(price: float, entry: float) -> float:
    return abs((price / entry - 1.0) * 100.0) if price > 0 and entry > 0 else float("inf")


def _plausible(price: float, entry: float) -> bool:
    return price > 0 and entry > 0 and _move_pct(price, entry) <= MAX_OBSERVATION_MOVE_PCT


def _safe_latest_price(mod: Any, symbol: str, pos: Dict[str, Any], entry: float) -> Tuple[float, str, List[Dict[str, Any]]]:
    rejected: List[Dict[str, Any]] = []
    position_price, position_source = _position_price(pos)
    if position_price > 0 and not _plausible(position_price, entry):
        rejected.append({
            "source": position_source,
            "price": round(position_price, 6),
            "reason": "position_price_outside_entry_relative_integrity_bound",
        })
        position_price = 0.0
    if position_price > 0:
        return position_price, position_source, rejected
    for fn_name in ("latest_price", "get_latest_price", "safe_latest_price"):
        try:
            fn = getattr(mod, fn_name, None)
            if not callable(fn):
                continue
            price = _f(fn(symbol), 0.0)
            if price <= 0:
                continue
            if not _plausible(price, entry):
                rejected.append({
                    "source": f"core.{fn_name}",
                    "price": round(price, 6),
                    "reason": "core_price_outside_entry_relative_integrity_bound",
                })
                continue
            return price, f"core.{fn_name}", rejected
        except Exception as exc:
            rejected.append({"source": f"core.{fn_name}", "reason": f"provider_exception:{type(exc).__name__}"})
    return entry, "entry_price_fallback", rejected


def _pct_for_side(current: float, entry: float, side: str) -> float:
    if entry <= 0 or current <= 0:
        return 0.0
    if side == "short":
        return (entry / current - 1.0) * 100.0
    return (current / entry - 1.0) * 100.0


def _strategy_metadata(pos: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "strategy_id": pos.get("strategy_id"),
        "setup_family": pos.get("setup_family"),
        "entry_model": pos.get("entry_model"),
        "exit_model": pos.get("exit_model"),
        "risk_model": pos.get("risk_model"),
        "strategy_label_source": pos.get("strategy_label_source"),
        "strategy_label_version": pos.get("strategy_label_version"),
        "entry_score": pos.get("score"),
        "sector": pos.get("sector"),
        "bucket": pos.get("bucket"),
    }


def _path_bounds_valid(path: Dict[str, Any], entry: float) -> bool:
    high = _f(path.get("high_since_entry"), entry)
    low = _f(path.get("low_since_entry"), entry)
    return high >= low > 0 and _plausible(high, entry) and _plausible(low, entry)


def _archive_item(archive: List[Any], item: Dict[str, Any], now_text: str, reason: str) -> None:
    row = dict(item)
    row.update({
        "closed_local": row.get("closed_local") or now_text,
        "archived_by": VERSION,
        "archive_reason": reason,
    })
    archive.append(row)


def update_paths(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    mod = mod or _module()
    section = state.setdefault("intratrade_path_capture", {})
    section.setdefault("paths", {})
    paths = _dict(section.get("paths"))
    section["paths"] = paths
    archive = _list(section.setdefault("closed_path_archive", []))
    now_epoch = _epoch_now()
    now_text = _now(mod)
    positions = _positions(state)
    active_symbols = set(positions.keys())
    updated = 0
    skipped: List[Dict[str, Any]] = []
    rejected_observations: List[Dict[str, Any]] = []
    integrity_resets = 0
    for symbol, pos in list(positions.items()):
        entry = _entry_price(pos)
        if entry <= 0:
            skipped.append({"symbol": symbol, "reason": "missing_entry_price"})
            continue
        side = _side(pos)
        entry_time = _entry_time(pos)
        identity = _path_id(symbol, side, entry_time, entry)
        price, price_source, rejected = _safe_latest_price(mod, symbol, pos, entry) if mod is not None else (entry, "entry_price_fallback", [])
        for row in rejected:
            rejected_observations.append({"symbol": symbol, **row, "entry_price": round(entry, 6)})
        path = _dict(paths.get(symbol))
        old_identity = str(path.get("path_id") or "")
        if path and old_identity != identity:
            path["integrity_status"] = "quarantined"
            path["training_eligible"] = False
            path["ml_feature_ready"] = False
            _archive_item(archive, path, now_text, "entry_identity_changed")
            path = {}
            integrity_resets += 1
        elif path and not _path_bounds_valid(path, entry):
            path["integrity_status"] = "quarantined"
            path["training_eligible"] = False
            path["ml_feature_ready"] = False
            path["integrity_reason"] = "historical_path_bounds_implausible"
            _archive_item(archive, path, now_text, "historical_path_bounds_implausible")
            path = {}
            integrity_resets += 1
        if not path:
            path = {
                "path_id": identity,
                "symbol": symbol,
                "side": side,
                "entry_price": round(entry, 6),
                "shares": round(_shares(pos), 6),
                "entry_time": entry_time,
                "opened_local": pos.get("opened_local") or pos.get("entry_local") or now_text,
                "high_since_entry": round(max(entry, price), 6),
                "low_since_entry": round(min(entry, price), 6),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,
                "time_to_mfe_seconds": 0,
                "time_to_mae_seconds": 0,
                "created_local": now_text,
                "observation_count": 0,
                "invalid_observation_count": 0,
            }
        prior_high = _f(path.get("high_since_entry"), entry)
        prior_low = _f(path.get("low_since_entry"), entry)
        observation_valid = _plausible(price, entry)
        if observation_valid:
            new_high = max(prior_high, price)
            new_low = min(prior_low, price)
            path["observation_count"] = int(path.get("observation_count") or 0) + 1
        else:
            new_high = prior_high
            new_low = prior_low
            path["invalid_observation_count"] = int(path.get("invalid_observation_count") or 0) + 1
            rejected_observations.append({
                "symbol": symbol,
                "source": price_source,
                "price": round(price, 6),
                "entry_price": round(entry, 6),
                "reason": "observation_outside_entry_relative_integrity_bound",
            })
        duration = max(0, int(now_epoch - _f(entry_time, now_epoch))) if entry_time else 0
        favorable_price, adverse_price = (new_low, new_high) if side == "short" else (new_high, new_low)
        mfe = _pct_for_side(favorable_price, entry, side)
        mae = _pct_for_side(adverse_price, entry, side)
        if new_high != prior_high or new_low != prior_low:
            if abs(mfe) >= abs(_f(path.get("mfe_pct"), 0.0)):
                path["time_to_mfe_seconds"] = duration
            if abs(mae) >= abs(_f(path.get("mae_pct"), 0.0)):
                path["time_to_mae_seconds"] = duration
        for key, value in _strategy_metadata(pos).items():
            if value is not None:
                path[key] = value
        valid_count = int(path.get("observation_count") or 0)
        invalid_count = int(path.get("invalid_observation_count") or 0)
        training_eligible = bool(
            valid_count >= MIN_VALID_OBSERVATIONS_FOR_TRAINING
            and invalid_count == 0
            and _path_bounds_valid({"high_since_entry": new_high, "low_since_entry": new_low}, entry)
            and price_source.startswith("position.")
        )
        path.update({
            "path_id": identity,
            "symbol": symbol,
            "side": side,
            "entry_price": round(entry, 6),
            "current_price": round(price, 6),
            "current_price_source": price_source,
            "high_since_entry": round(new_high, 6),
            "low_since_entry": round(new_low, 6),
            "mfe_pct": round(max(0.0, mfe), 4),
            "mae_pct": round(min(0.0, mae), 4),
            "duration_seconds": duration,
            "last_updated_local": now_text,
            "calculation_version": CALCULATION_VERSION,
            "integrity_status": "valid" if training_eligible else "collecting" if invalid_count == 0 else "quarantined",
            "integrity_reason": None if invalid_count == 0 else "invalid_price_observation",
            "training_eligible": training_eligible,
            "ml_feature_ready": training_eligible,
            "live_authority": False,
        })
        paths[symbol] = path
        updated += 1
    for sym in [symbol for symbol in list(paths.keys()) if symbol not in active_symbols]:
        item = paths.pop(sym)
        if isinstance(item, dict):
            eligible = bool(item.get("training_eligible")) and item.get("integrity_status") == "valid"
            item["training_eligible"] = eligible
            item["ml_feature_ready"] = eligible
            _archive_item(archive, item, now_text, "position_closed")
    compact: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in archive:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        identity = str(row.get("path_id") or _path_id(
            str(row.get("symbol") or "").upper(),
            str(row.get("side") or "long").lower(),
            _f(row.get("entry_time"), 0.0) or None,
            _f(row.get("entry_price"), 0.0),
        ))
        row["path_id"] = identity
        entry = _f(row.get("entry_price"), 0.0)
        if entry <= 0 or not _path_bounds_valid(row, entry):
            row.update({
                "integrity_status": "quarantined",
                "integrity_reason": row.get("integrity_reason") or "archived_path_bounds_implausible",
                "training_eligible": False,
                "ml_feature_ready": False,
            })
        if identity in seen:
            continue
        seen.add(identity)
        compact.append(row)
    section["closed_path_archive"] = compact[-500:]
    active_values = list(paths.values())
    archive_values = section["closed_path_archive"]
    invalid_rows = sum(1 for row in active_values + archive_values if row.get("integrity_status") == "quarantined")
    eligible_rows = sum(1 for row in active_values + archive_values if row.get("training_eligible") is True)
    section.update({
        "version": VERSION,
        "calculation_version": CALCULATION_VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": now_text,
        "active_positions_tracked": len(paths),
        "closed_paths_archived": len(archive_values),
        "updated_count": updated,
        "skipped_positions": skipped[-25:],
        "rejected_observations": rejected_observations[-50:],
        "integrity_resets": integrity_resets,
        "invalid_or_quarantined_rows": invalid_rows,
        "training_eligible_rows": eligible_rows,
        "regression_guards": {
            "position_owned_price_preferred": True,
            "entry_identity_resets_path": True,
            "implausible_historical_bounds_quarantined": True,
            "symbol_only_feature_matching_prohibited": True,
        },
    })
    return section


def status_payload(mod: Any = None, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = _dict(state.get("intratrade_path_capture"))
    paths = list(_dict(section.get("paths")).values())
    archive = [row for row in _list(section.get("closed_path_archive")) if isinstance(row, dict)]
    invalid = [row for row in paths + archive if row.get("integrity_status") == "quarantined"]
    eligible = [row for row in paths + archive if row.get("training_eligible") is True]
    return {
        "status": "ok",
        "overall": "warn" if invalid else "pass",
        "type": "intratrade_path_integrity_status",
        "version": VERSION,
        "calculation_version": CALCULATION_VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "active_positions_tracked": len(paths),
        "closed_paths_archived": len(archive),
        "invalid_or_quarantined_rows": len(invalid),
        "training_eligible_rows": len(eligible),
        "rejected_observations": _list(section.get("rejected_observations"))[-25:],
        "invalid_rows_tail": invalid[-10:],
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
    section = update_paths(state, mod) if ENABLED else _dict(state.get("intratrade_path_capture"))
    status = status_payload(mod, state)
    status.update({
        "type": "intratrade_path_status",
        "updated_count": section.get("updated_count", 0),
        "skipped_positions": section.get("skipped_positions", []),
        "active_paths": list(_dict(section.get("paths")).values())[-25:],
        "closed_path_tail": _list(section.get("closed_path_archive"))[-25:],
    })
    return status


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
    def integrity_route():
        state, mod = _load_state(module)
        return jsonify(status_payload(mod, state))
    if "/paper/intratrade-path-status" not in existing:
        flask_app.add_url_rule("/paper/intratrade-path-status", "paper_intratrade_path_status", status_route)
    if "/paper/position-path-status" not in existing:
        flask_app.add_url_rule("/paper/position-path-status", "paper_position_path_status", status_route)
    if "/paper/intratrade-path-integrity-status" not in existing:
        flask_app.add_url_rule("/paper/intratrade-path-integrity-status", "paper_intratrade_path_integrity_status", integrity_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "live_authority": False}
