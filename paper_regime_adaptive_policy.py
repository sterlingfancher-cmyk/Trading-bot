"""Central paper-only regime-adaptive participation policy.

This module restores coherent capital deployment without adding another entry
wrapper. It owns a small whitelist of participation, capacity, and sizing
constants across the existing paper stack and updates those values as the
market regime changes.

It deliberately does not:
- alter live-trading authority;
- bypass account halts, cooldowns, self-defense, stop losses, or the 3% daily
  loss ceiling;
- lower the primary app entry-score floors;
- place orders;
- patch or wrap entry functions.

The policy is reversible: disabling it restores the original values captured
when the module first applied.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
import threading
import time
from typing import Any, Dict, Tuple

VERSION = "paper-regime-adaptive-policy-2026-08-03-v1"
ENABLED = os.environ.get("PAPER_REGIME_ADAPTIVE_POLICY_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
PAPER_ONLY = os.environ.get("PAPER_REGIME_ADAPTIVE_POLICY_PAPER_ONLY", "true").lower() not in {
    "0", "false", "no", "off"
}
WATCHDOG_SECONDS = max(10, int(os.environ.get("PAPER_REGIME_ADAPTIVE_POLICY_WATCHDOG_SECONDS", "30")))

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED: set[int] = set()
_ORIGINALS: Dict[Tuple[str, str], Any] = {}
_LAST: Dict[str, Any] = {}

# The primary score floors remain owned by app/min_entry_score_for_market.
# These profiles only reconcile capacity and sizing paths that were
# independently shrinking or suppressing otherwise valid entries.
PROFILES: Dict[str, Dict[str, Any]] = {
    "strong_risk_on": {
        "target_exposure": 0.62,
        "max_open": 4,
        "max_daily": 3,
        "max_cycle": 2,
        "starter_target": 0.16,
        "late_target": 0.12,
        "max_entry_alloc": 0.18,
        "cash_reserve": 0.22,
        "starter_min_cash_pct": 32.0,
        "min_spacing_seconds": 420,
        "second_position_min_pnl": -0.010,
        "risk_reward_account_risk": 0.012,
        "valve_min_raw_score": 0.0080,
        "valve_min_rank_score": 0.0120,
        "valve_max_score_gap": 0.0060,
    },
    "risk_on": {
        "target_exposure": 0.58,
        "max_open": 4,
        "max_daily": 3,
        "max_cycle": 2,
        "starter_target": 0.16,
        "late_target": 0.12,
        "max_entry_alloc": 0.17,
        "cash_reserve": 0.25,
        "starter_min_cash_pct": 35.0,
        "min_spacing_seconds": 480,
        "second_position_min_pnl": -0.010,
        "risk_reward_account_risk": 0.010,
        "valve_min_raw_score": 0.0080,
        "valve_min_rank_score": 0.0120,
        "valve_max_score_gap": 0.0050,
    },
    "constructive": {
        "target_exposure": 0.52,
        "max_open": 4,
        "max_daily": 3,
        "max_cycle": 2,
        "starter_target": 0.15,
        "late_target": 0.11,
        "max_entry_alloc": 0.16,
        "cash_reserve": 0.30,
        "starter_min_cash_pct": 40.0,
        "min_spacing_seconds": 540,
        "second_position_min_pnl": -0.008,
        "risk_reward_account_risk": 0.010,
        "valve_min_raw_score": 0.0085,
        "valve_min_rank_score": 0.0130,
        "valve_max_score_gap": 0.0045,
    },
    "neutral": {
        "target_exposure": 0.42,
        "max_open": 3,
        "max_daily": 2,
        "max_cycle": 1,
        "starter_target": 0.13,
        "late_target": 0.10,
        "max_entry_alloc": 0.14,
        "cash_reserve": 0.40,
        "starter_min_cash_pct": 55.0,
        "min_spacing_seconds": 600,
        "second_position_min_pnl": -0.005,
        "risk_reward_account_risk": 0.0075,
        "valve_min_raw_score": 0.0090,
        "valve_min_rank_score": 0.0140,
        "valve_max_score_gap": 0.0035,
    },
    "defensive": {
        "target_exposure": 0.20,
        "max_open": 2,
        "max_daily": 1,
        "max_cycle": 1,
        "starter_target": 0.08,
        "late_target": 0.06,
        "max_entry_alloc": 0.10,
        "cash_reserve": 0.60,
        "starter_min_cash_pct": 70.0,
        "min_spacing_seconds": 900,
        "second_position_min_pnl": 0.0,
        "risk_reward_account_risk": 0.005,
        "valve_min_raw_score": 0.0110,
        "valve_min_rank_score": 0.0170,
        "valve_max_score_gap": 0.0020,
    },
    "risk_off": {
        "target_exposure": 0.10,
        "max_open": 1,
        "max_daily": 1,
        "max_cycle": 1,
        "starter_target": 0.06,
        "late_target": 0.05,
        "max_entry_alloc": 0.08,
        "cash_reserve": 0.75,
        "starter_min_cash_pct": 80.0,
        "min_spacing_seconds": 1200,
        "second_position_min_pnl": 0.0,
        "risk_reward_account_risk": 0.004,
        "valve_min_raw_score": 0.0130,
        "valve_min_rank_score": 0.0200,
        "valve_max_score_gap": 0.0015,
    },
}

_MODE_ALIASES = {
    "strong_risk_on": "strong_risk_on",
    "risk_on": "risk_on",
    "bull": "risk_on",
    "constructive": "constructive",
    "neutral": "neutral",
    "caution": "neutral",
    "defensive": "defensive",
    "defensive_rotation": "defensive",
    "risk_off": "risk_off",
    "bear": "risk_off",
    "bearish": "risk_off",
    "crash_warning": "risk_off",
    "crash": "risk_off",
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        out = float(value)
        return default if math.isnan(out) or math.isinf(out) else out
    except Exception:
        return default


def _core() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "portfolio"):
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "portfolio"):
            return mod
    return None


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _save(core: Any) -> None:
    try:
        fn = getattr(core, "save_state", None)
        if callable(fn):
            fn(_portfolio(core))
    except Exception:
        pass


def _market(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    out: Dict[str, Any] = {}
    for source in (
        _d(_d(state.get("auto_runner")).get("last_result")),
        _d(state.get("last_market")),
        _d(state.get("market_regime")),
    ):
        for key, value in source.items():
            out.setdefault(key, value)
    return out


def _risk_state(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    risk = _d(state.get("risk_controls"))
    feedback = _d(state.get("feedback_loop"))
    return {
        "halted": bool(risk.get("halted")),
        "self_defense_active": bool(risk.get("self_defense_active")),
        "profit_guard_active": bool(risk.get("profit_guard_active")),
        "daily_loss_pct": _f(risk.get("daily_loss_pct")),
        "intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct")),
        "feedback_blocks_entries": bool(feedback.get("block_new_entries") or feedback.get("hard_halt")),
    }


def _profile_name(market: Dict[str, Any]) -> str:
    raw = str(market.get("market_mode") or market.get("regime") or "neutral").lower().strip()
    if bool(market.get("bear_confirmed")):
        return "risk_off"
    if bool(market.get("defensive_rotation")) and raw not in {"risk_on", "strong_risk_on"}:
        return "defensive"
    risk_score = _f(market.get("risk_score"), 50.0)
    mode = _MODE_ALIASES.get(raw, "neutral")
    if mode == "risk_on" and risk_score >= 78:
        return "strong_risk_on"
    if mode in {"risk_on", "constructive"} and risk_score < 45:
        return "neutral"
    if mode == "neutral" and risk_score < 35:
        return "defensive"
    return mode


def _remember(module_name: str, attr: str, value: Any) -> None:
    key = (module_name, attr)
    if key not in _ORIGINALS:
        _ORIGINALS[key] = value


def _set_attr(module: Any, attr: str, value: Any, changes: list[Dict[str, Any]]) -> None:
    if module is None or not hasattr(module, attr):
        return
    module_name = getattr(module, "__name__", str(module))
    old = getattr(module, attr)
    _remember(module_name, attr, old)
    if old != value:
        setattr(module, attr, value)
        changes.append({"module": module_name, "name": attr, "old": old, "new": value})


def _set_core_attr(core: Any, attr: str, value: Any, changes: list[Dict[str, Any]]) -> None:
    if core is None or not hasattr(core, attr):
        return
    old = getattr(core, attr)
    _remember(getattr(core, "__name__", "app"), attr, old)
    if old != value:
        setattr(core, attr, value)
        changes.append({"module": getattr(core, "__name__", "app"), "name": attr, "old": old, "new": value})


def _import(name: str) -> Any | None:
    try:
        return __import__(name)
    except Exception:
        return None


def _apply_profile(core: Any, name: str) -> Dict[str, Any]:
    profile = dict(PROFILES.get(name) or PROFILES["neutral"])
    changes: list[Dict[str, Any]] = []

    pipeline = _import("core_entry_pipeline")
    starter = _import("risk_on_starter_participation_valve")
    neutral = _import("neutral_momentum_starter_extension")
    under = _import("paper_underdeployment_repair")
    allocator = _import("paper_participation_allocator")
    risk_reward = _import("risk_reward_structure")

    # The valve only runs in risk-on/constructive modes, so it owns one stable
    # favorable-market configuration rather than inheriting neutral settings.
    valve_profile = PROFILES["risk_on"]
    _set_attr(pipeline, "PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY", valve_profile["max_daily"], changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE", valve_profile["max_cycle"], changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_MAX_REVIEWED_RANK", 8, changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_ALLOC_FACTOR", 1.0, changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_MIN_RAW_SCORE", valve_profile["valve_min_raw_score"], changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_MIN_RANK_SCORE", valve_profile["valve_min_rank_score"], changes)
    _set_attr(pipeline, "PARTICIPATION_VALVE_MAX_SCORE_GAP", valve_profile["valve_max_score_gap"], changes)

    # The existing hard blocker list remains untouched.
    _set_attr(starter, "ALLOC_FACTOR", 1.0, changes)
    _set_attr(starter, "MAX_ENTRIES_PER_DAY", valve_profile["max_daily"], changes)
    _set_attr(starter, "MAX_ENTRIES_PER_CYCLE", valve_profile["max_cycle"], changes)
    _set_attr(starter, "MAX_OPEN_POSITIONS", valve_profile["max_open"], changes)
    _set_attr(starter, "MAX_REVIEWED_RANK", 8, changes)
    _set_attr(starter, "MIN_CASH_PCT", valve_profile["starter_min_cash_pct"], changes)
    _set_attr(starter, "MIN_RAW_SCORE", valve_profile["valve_min_raw_score"], changes)
    _set_attr(starter, "MIN_RANK_SCORE", valve_profile["valve_min_rank_score"], changes)

    # Neutral participation owns a stable neutral policy and remains staged.
    neutral_profile = PROFILES["neutral"]
    _set_attr(neutral, "MAX_COMBINED_EXPOSURE_PCT", round(neutral_profile["target_exposure"] * 100, 2), changes)
    _set_attr(neutral, "MAX_NEUTRAL_OPEN_POSITIONS", neutral_profile["max_open"], changes)
    _set_attr(neutral, "MAX_NEUTRAL_STARTERS_PER_DAY", neutral_profile["max_daily"], changes)
    _set_attr(neutral, "MAX_NEUTRAL_STARTERS_PER_CYCLE", neutral_profile["max_cycle"], changes)
    _set_attr(neutral, "MIN_SECONDS_BETWEEN_STARTERS", neutral_profile["min_spacing_seconds"], changes)
    _set_attr(neutral, "FIRST_POSITION_MIN_PNL_PCT", neutral_profile["second_position_min_pnl"] * 100.0, changes)
    _set_attr(neutral, "MIN_SCANNER_SIGNALS", 12, changes)
    _set_attr(neutral, "MIN_LONG_SIGNALS", 3, changes)

    # Final starter targets are static by destination regime; broad capacity is
    # dynamic and follows the active market profile.
    if under is not None:
        old_targets = dict(getattr(under, "TARGETS", {}) or {})
        _remember(getattr(under, "__name__", "paper_underdeployment_repair"), "TARGETS", old_targets)
        targets = dict(old_targets)
        targets.update(
            {
                "risk_on": PROFILES["risk_on"]["starter_target"],
                "constructive": PROFILES["constructive"]["starter_target"],
                "neutral": PROFILES["neutral"]["starter_target"],
                "late_neutral": PROFILES["neutral"]["late_target"],
            }
        )
        if old_targets != targets:
            under.TARGETS = targets
            changes.append(
                {
                    "module": getattr(under, "__name__", "paper_underdeployment_repair"),
                    "name": "TARGETS",
                    "old": old_targets,
                    "new": targets,
                }
            )
    _set_attr(under, "MAX_COMBINED", profile["target_exposure"], changes)
    _set_attr(under, "MAX_OPEN", profile["max_open"], changes)
    _set_attr(under, "MAX_DAILY", profile["max_daily"], changes)
    _set_attr(under, "MIN_SPACING", profile["min_spacing_seconds"], changes)
    _set_attr(under, "MIN_FIRST_PNL", profile["second_position_min_pnl"], changes)
    _set_attr(under, "CASH_RESERVE", profile["cash_reserve"], changes)
    _set_attr(under, "STARTER_MIN_CASH", profile["starter_min_cash_pct"], changes)

    # Reconcile the allocator with final targets while preserving sector and
    # bucket caps.
    _set_attr(allocator, "MAX_NEW_ENTRIES_PER_CYCLE", profile["max_cycle"], changes)
    _set_attr(allocator, "MAX_ENTRY_ALLOC_PCT", profile["max_entry_alloc"], changes)
    _set_attr(allocator, "STRONG_MAX_ENTRY_ALLOC_PCT", min(0.18, profile["max_entry_alloc"] + 0.01), changes)
    _set_attr(allocator, "CASH_RESERVE_PCT", profile["cash_reserve"], changes)
    _set_attr(allocator, "TARGET_STRONG_RISK_ON", PROFILES["strong_risk_on"]["target_exposure"], changes)
    _set_attr(allocator, "TARGET_RISK_ON", PROFILES["risk_on"]["target_exposure"], changes)
    _set_attr(allocator, "TARGET_CONSTRUCTIVE", PROFILES["constructive"]["target_exposure"], changes)
    _set_attr(allocator, "TARGET_NEUTRAL", PROFILES["neutral"]["target_exposure"], changes)
    _set_attr(allocator, "TARGET_DEFENSIVE", PROFILES["defensive"]["target_exposure"], changes)
    _set_attr(allocator, "TARGET_RISK_OFF", PROFILES["risk_off"]["target_exposure"], changes)

    # Raise the former 0.4% risk ceiling by regime while retaining structure
    # stops, minimum RR, and the absolute 2% per-trade cap.
    _set_attr(risk_reward, "MAX_RISK_PER_TRADE_PCT", profile["risk_reward_account_risk"], changes)

    # Primary score floors and hard account controls remain unchanged.
    _set_core_attr(core, "MAX_NEW_ENTRIES_PER_CYCLE", max(1, profile["max_cycle"]), changes)

    return {"profile": name, "settings": profile, "changes": changes}


def restore(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    restored: list[Dict[str, Any]] = []
    for (module_name, attr), value in list(_ORIGINALS.items()):
        module = sys.modules.get(module_name)
        if module is None and module_name == "app":
            module = core
        if module is None or not hasattr(module, attr):
            continue
        old = getattr(module, attr)
        if old != value:
            setattr(module, attr, value)
            restored.append({"module": module_name, "name": attr, "old": old, "new": value})
    return {"status": "ok", "version": VERSION, "restored": restored, "restored_count": len(restored)}


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    with _LOCK:
        if not ENABLED:
            result = restore(core)
            result.update({"status": "disabled", "enabled": False})
            _LAST = result
            return dict(result)
        if not _paper_context():
            result = restore(core)
            result.update(
                {
                    "status": "guarded",
                    "enabled": True,
                    "paper_context": False,
                    "reason": "live_or_production_context_detected",
                }
            )
            _LAST = result
            return dict(result)
        market = _market(core)
        profile_name = _profile_name(market)
        applied = _apply_profile(core, profile_name)
        risk = _risk_state(core)
        result = {
            "status": "ok",
            "overall": "pass",
            "version": VERSION,
            "generated_local": _now(core),
            "enabled": True,
            "paper_only": PAPER_ONLY,
            "paper_context": True,
            "market_mode": market.get("market_mode") or market.get("regime"),
            "risk_score": market.get("risk_score"),
            "active_profile": profile_name,
            "settings": applied["settings"],
            "changes_this_call": applied["changes"],
            "changes_this_call_count": len(applied["changes"]),
            "original_values_captured": len(_ORIGINALS),
            "hard_controls_preserved": {
                "primary_entry_score_floors_changed": False,
                "daily_loss_limit_changed": False,
                "intraday_drawdown_halt_changed": False,
                "self_defense_changed": False,
                "cooldowns_changed": False,
                "stop_loss_logic_changed": False,
                "places_orders": False,
                "wraps_entry_functions": False,
            },
            "risk_state": risk,
            "authority": {
                "paper_only": True,
                "changes_paper_capacity": True,
                "changes_paper_sizing_ceilings": True,
                "changes_primary_score_floors": False,
                "changes_live_authority": False,
                "places_orders": False,
            },
        }
        _LAST = result
        state = _portfolio(core)
        state["paper_regime_adaptive_policy"] = dict(result)
        setattr(core, "PAPER_REGIME_ADAPTIVE_POLICY_VERSION", VERSION)
        _save(core)
        return dict(result)


def status(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    current = dict(_LAST) if _LAST else apply(core)
    current["type"] = "paper_regime_adaptive_policy_status"
    current["available_profiles"] = {name: dict(values) for name, values in PROFILES.items()}
    return current


def _watchdog(core: Any) -> None:
    while True:
        try:
            apply(core)
        except Exception as exc:
            state = _portfolio(core)
            state["paper_regime_adaptive_policy_error"] = f"{type(exc).__name__}: {exc}"
        time.sleep(WATCHDOG_SECONDS)


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    apply(core)
    if id(core) not in _WATCHDOGS:
        _WATCHDOGS.add(id(core))
        threading.Thread(
            target=_watchdog,
            args=(core,),
            name="paper-regime-adaptive-policy",
            daemon=True,
        ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _core()
    start_watchdog(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}

    def status_route():
        return jsonify(status(core or _core()))

    def apply_route():
        return jsonify(apply(core or _core()))

    routes = (
        ("/paper/regime-adaptive-policy-status", "paper_regime_adaptive_policy_status", status_route),
        ("/paper/regime-adaptive-policy-apply", "paper_regime_adaptive_policy_apply", apply_route),
    )
    for path, endpoint, fn in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, fn)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [row[0] for row in routes]}


try:
    apply(_core())
except Exception:
    pass
