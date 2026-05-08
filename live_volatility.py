"""Live volatility-aware stop and allocation controls.

This module upgrades the advisory volatility-stop plan into runtime controls.
It is intentionally defensive: if any monkey patch fails, the core app keeps
running and the status endpoint reports the failed item.

Controls applied:
- Reduces bucket allocation on high-volatility themes.
- Widens default live stop / trail parameters to the volatility-stop cap.
- Wraps risk-parameter builder functions so returned stop_loss / trail values
  use the volatility-aware floor before the core engine evaluates trades.
- Adds /paper/live-volatility-status for verification.
"""
from __future__ import annotations

import datetime as dt
import functools
import inspect
import json
import math
import os
import sys
import time
from typing import Any, Dict, Iterable, List

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

VERSION = "live-volatility-stops-2026-05-08"
APPLIED: Dict[str, Any] = {}
REGISTERED_APP_IDS: set[int] = set()
_PATCHED_FUNCTION_IDS: set[int] = set()

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
MARKET_TZ_NAME = os.environ.get("MARKET_TZ", "America/Chicago")

LIVE_VOL_STOPS_ENABLED = os.environ.get("LIVE_VOL_STOPS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_VOL_ALLOC_ENABLED = os.environ.get("LIVE_VOL_ALLOC_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

VOL_STOP_MIN_PCT = float(os.environ.get("HYBRID_VOL_STOP_MIN_PCT", "0.012"))
VOL_STOP_MAX_PCT = float(os.environ.get("HYBRID_VOL_STOP_MAX_PCT", "0.028"))
VOL_STOP_DEFAULT_PCT = float(os.environ.get("HYBRID_LIVE_VOL_STOP_DEFAULT_PCT", str(VOL_STOP_MAX_PCT)))
VOL_STOP_MULTIPLIER = float(os.environ.get("HYBRID_VOL_STOP_MULTIPLIER", "1.35"))
HIGH_VOL_ALLOC_REDUCTION = float(os.environ.get("HYBRID_HIGH_VOL_ALLOC_REDUCTION", "0.65"))
MIN_BUCKET_ALLOC_FACTOR = float(os.environ.get("HYBRID_MIN_BUCKET_ALLOC_FACTOR", "0.20"))

# Bucket-level live allocation reductions. These are conservative because the
# prior session showed tight-stop churn in high-beta names.
BUCKET_ALLOC_REDUCTIONS = {
    "small_cap_momentum": float(os.environ.get("HYBRID_SMALL_CAP_LIVE_ALLOC_REDUCTION", str(HIGH_VOL_ALLOC_REDUCTION))),
    "bitcoin_ai_compute": float(os.environ.get("HYBRID_BITCOIN_COMPUTE_LIVE_ALLOC_REDUCTION", str(HIGH_VOL_ALLOC_REDUCTION))),
    "precious_metals": float(os.environ.get("HYBRID_METALS_LIVE_ALLOC_REDUCTION", str(HIGH_VOL_ALLOC_REDUCTION))),
    "semi_leaders": float(os.environ.get("HYBRID_SEMI_LIVE_ALLOC_REDUCTION", "0.75")),
    "cloud_cyber_software": float(os.environ.get("HYBRID_SOFTWARE_LIVE_ALLOC_REDUCTION", "0.75")),
    "data_center_infra": float(os.environ.get("HYBRID_DATA_CENTER_LIVE_ALLOC_REDUCTION", "0.75")),
}

_PRICE_CACHE: Dict[str, Any] = {"ts": 0.0, "profiles": {}}


def _now() -> dt.datetime:
    if pytz:
        return dt.datetime.now(pytz.timezone(MARKET_TZ_NAME))
    return dt.datetime.now()


def _now_text() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S %Z")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        folder = os.path.dirname(STATE_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _patch(module: Any, name: str, value: Any, mode: str = "set") -> None:
    old = getattr(module, name, None)
    new = value
    try:
        if old is not None:
            if mode == "min":
                new = min(old, value)
            elif mode == "max":
                new = max(old, value)
        setattr(module, name, new)
        APPLIED[name] = {"old": old, "new": new, "mode": mode, "applied": True}
    except Exception as exc:
        APPLIED[name] = {"old": old, "new": value, "mode": mode, "applied": False, "error": str(exc)}


def _patch_bucket_allocations(module: Any) -> None:
    if not LIVE_VOL_ALLOC_ENABLED:
        APPLIED["bucket_allocation_controls"] = {"enabled": False}
        return
    cfg = getattr(module, "BUCKET_CONFIG", None)
    if not isinstance(cfg, dict):
        APPLIED["bucket_allocation_controls"] = {"enabled": True, "applied": False, "reason": "BUCKET_CONFIG not found"}
        return

    applied = {}
    for bucket, reduction in BUCKET_ALLOC_REDUCTIONS.items():
        row = cfg.get(bucket)
        if not isinstance(row, dict):
            continue
        old = _f(row.get("alloc_factor"), 1.0)
        new = max(MIN_BUCKET_ALLOC_FACTOR, round(old * reduction, 4))
        row["alloc_factor"] = new
        applied[bucket] = {"old_alloc_factor": old, "new_alloc_factor": new, "reduction": reduction}
    APPLIED["bucket_allocation_controls"] = {
        "enabled": True,
        "applied": bool(applied),
        "bucket_changes": applied,
    }


def _patch_global_stop_names(module: Any) -> None:
    # These names may or may not exist in app.py; setting them is safe and gives
    # any direct global lookups a volatility-aware value.
    stop = max(VOL_STOP_MIN_PCT, min(VOL_STOP_MAX_PCT, VOL_STOP_DEFAULT_PCT))
    for name in [
        "STOP_LOSS",
        "STOP_LOSS_PCT",
        "LONG_STOP_LOSS",
        "LONG_STOP_LOSS_PCT",
        "DEFAULT_STOP_LOSS",
        "DEFAULT_STOP_LOSS_PCT",
    ]:
        _patch(module, name, -stop, "set")
    for name in ["TRAIL_LONG", "LONG_TRAIL", "TRAIL_LONG_PCT"]:
        _patch(module, name, 1.0 - stop, "set")
    for name in ["TRAIL_SHORT", "SHORT_TRAIL", "TRAIL_SHORT_PCT"]:
        _patch(module, name, 1.0 + stop, "set")
    _patch(module, "HYBRID_LIVE_VOLATILITY_VERSION", VERSION, "set")
    _patch(module, "HYBRID_LIVE_VOLATILITY_STOP_PCT", stop, "set")
    _patch(module, "HYBRID_LIVE_HIGH_VOL_ALLOC_REDUCTION", HIGH_VOL_ALLOC_REDUCTION, "set")


def _transform_risk_dict(obj: Any) -> Any:
    """Recursively widen stop/trail fields in returned risk-parameter dicts."""
    if isinstance(obj, list):
        return [_transform_risk_dict(x) for x in obj]
    if not isinstance(obj, dict):
        return obj

    out: Dict[str, Any] = {}
    for k, v in obj.items():
        out[k] = _transform_risk_dict(v)

    stop = max(VOL_STOP_MIN_PCT, min(VOL_STOP_MAX_PCT, VOL_STOP_DEFAULT_PCT))
    if LIVE_VOL_STOPS_ENABLED:
        if "stop_loss" in out:
            old = _f(out.get("stop_loss"), 0.0)
            if old < 0:
                out["stop_loss"] = -max(abs(old), stop)
            elif old > 0:
                out["stop_loss"] = max(old, stop)
            else:
                out["stop_loss"] = -stop
            out.setdefault("volatility_stop_applied", True)
            out.setdefault("volatility_stop_pct", round(stop, 6))
        if "trail_long" in out:
            old = _f(out.get("trail_long"), 1.0)
            out["trail_long"] = min(old, 1.0 - stop)
        if "trail_short" in out:
            old = _f(out.get("trail_short"), 1.0)
            out["trail_short"] = max(old, 1.0 + stop)
        if "risk_parameters" in out and isinstance(out["risk_parameters"], dict):
            rp = out["risk_parameters"]
            rp.setdefault("live_volatility_controls", {})
            rp["live_volatility_controls"].update({
                "enabled": True,
                "version": VERSION,
                "default_stop_pct": round(stop * 100, 2),
                "high_vol_alloc_reduction": HIGH_VOL_ALLOC_REDUCTION,
            })
    return out


def _function_mentions_stop_loss(fn: Any) -> bool:
    try:
        consts = " ".join(str(c) for c in getattr(fn, "__code__", None).co_consts)
    except Exception:
        consts = ""
    name = getattr(fn, "__name__", "").lower()
    haystack = f"{name} {consts}".lower()
    return ("stop_loss" in haystack or "trail_long" in haystack or "risk_parameters" in haystack) and (
        "risk" in haystack or "param" in haystack or "permission" in haystack
    )


def _patch_risk_parameter_functions(module: Any) -> None:
    if not LIVE_VOL_STOPS_ENABLED:
        APPLIED["risk_parameter_function_wrappers"] = {"enabled": False}
        return

    wrapped = []
    for name, fn in list(getattr(module, "__dict__", {}).items()):
        if not callable(fn) or getattr(fn, "_live_volatility_wrapped", False):
            continue
        if not inspect.isfunction(fn):
            continue
        if not _function_mentions_stop_loss(fn):
            continue
        if id(fn) in _PATCHED_FUNCTION_IDS:
            continue

        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, **kwargs):
            result = __fn(*args, **kwargs)
            return _transform_risk_dict(result)

        wrapper._live_volatility_wrapped = True  # type: ignore[attr-defined]
        try:
            setattr(module, name, wrapper)
            _PATCHED_FUNCTION_IDS.add(id(fn))
            wrapped.append(name)
        except Exception:
            pass

    APPLIED["risk_parameter_function_wrappers"] = {
        "enabled": True,
        "wrapped_count": len(wrapped),
        "wrapped_functions": wrapped[:30],
    }


def _state_symbols(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    positions = state.get("positions", {})
    if isinstance(positions, dict):
        out.extend(list(positions.keys()))
    scan = state.get("scanner_audit", {})
    if isinstance(scan, dict):
        for key in ["accepted_entries", "blocked_entries", "rejected_signals", "long_signals", "short_signals"]:
            rows = scan.get(key, [])
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, str):
                        out.append(row)
                    elif isinstance(row, dict) and row.get("symbol"):
                        out.append(str(row.get("symbol")))
    trades = state.get("trades", [])
    if isinstance(trades, list):
        for t in trades[-30:]:
            if isinstance(t, dict) and t.get("symbol"):
                out.append(str(t.get("symbol")))
    return list(dict.fromkeys([s.upper() for s in out if s]))[:40]


def _prices(symbols: Iterable[str]) -> Dict[str, List[float]]:
    if yf is None:
        return {}
    now = time.time()
    if now - _PRICE_CACHE.get("ts", 0.0) < 900 and _PRICE_CACHE.get("profiles"):
        return _PRICE_CACHE["profiles"]

    out: Dict[str, List[float]] = {}
    for sym in list(symbols):
        try:
            h = yf.Ticker(sym).history(period="1mo", interval="1d", auto_adjust=True)
            vals = [float(v) for v in h.get("Close", []).dropna().tolist()]
            if len(vals) >= 3:
                out[sym] = vals
        except Exception:
            pass
    _PRICE_CACHE["ts"] = now
    _PRICE_CACHE["profiles"] = out
    return out


def _vol(vals: List[float]) -> float:
    rets = []
    for i in range(1, len(vals)):
        if vals[i - 1] > 0:
            rets.append(vals[i] / vals[i - 1] - 1.0)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return math.sqrt(max(0.0, var))


def _vol_profile(symbol: str, vals: List[float]) -> Dict[str, Any]:
    daily_vol = _vol(vals[-11:])
    stop = max(VOL_STOP_MIN_PCT, min(VOL_STOP_MAX_PCT, daily_vol * VOL_STOP_MULTIPLIER))
    high_vol = stop >= 0.020
    return {
        "symbol": symbol,
        "daily_realized_vol_pct": round(daily_vol * 100, 2),
        "live_stop_pct": round(stop * 100, 2),
        "live_alloc_factor": HIGH_VOL_ALLOC_REDUCTION if high_vol else 1.0,
        "high_volatility": high_vol,
    }


def _live_status(module: Any | None = None) -> Dict[str, Any]:
    state = _load_state()
    symbols = _state_symbols(state)
    px = _prices(symbols)
    profiles = [_vol_profile(sym, vals) for sym, vals in px.items()]
    profiles.sort(key=lambda r: r.get("live_stop_pct", 0), reverse=True)
    return {
        "status": "ok",
        "version": VERSION,
        "generated_local": _now_text(),
        "state_file": STATE_FILE,
        "enabled": {
            "live_vol_stops": LIVE_VOL_STOPS_ENABLED,
            "live_vol_alloc": LIVE_VOL_ALLOC_ENABLED,
        },
        "applied_controls": APPLIED,
        "runtime_expectation": {
            "default_live_stop_pct": round(max(VOL_STOP_MIN_PCT, min(VOL_STOP_MAX_PCT, VOL_STOP_DEFAULT_PCT)) * 100, 2),
            "high_vol_alloc_reduction": HIGH_VOL_ALLOC_REDUCTION,
            "max_new_entries_per_cycle_should_remain": 1,
        },
        "recent_symbol_profiles": profiles,
        "note": "This is now a runtime patch, not just an advisory endpoint. It reduces high-vol bucket sizing and widens risk-parameter stop/trail values when those functions are used by the core engine.",
    }


def apply(module: Any | None = None) -> Dict[str, Any]:
    if module is None:
        for mod in list(sys.modules.values()):
            if getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
                module = mod
                break
    if module is None:
        return {"status": "not_applied", "reason": "trading module not found", "version": VERSION}

    _patch_bucket_allocations(module)
    _patch_global_stop_names(module)
    _patch_risk_parameter_functions(module)

    state = _load_state()
    state.setdefault("live_volatility_controls", {})
    state["live_volatility_controls"].update({
        "version": VERSION,
        "enabled": True,
        "updated_local": _now_text(),
        "applied_controls": APPLIED,
        "default_stop_pct": round(max(VOL_STOP_MIN_PCT, min(VOL_STOP_MAX_PCT, VOL_STOP_DEFAULT_PCT)) * 100, 2),
        "high_vol_alloc_reduction": HIGH_VOL_ALLOC_REDUCTION,
    })
    _save_state(state)
    return {"status": "ok", "version": VERSION, "applied_controls": APPLIED}


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/live-volatility-status" not in existing:
        flask_app.add_url_rule(
            "/paper/live-volatility-status",
            "live_volatility_status",
            lambda: jsonify(_live_status(module)),
        )

    REGISTERED_APP_IDS.add(id(flask_app))
