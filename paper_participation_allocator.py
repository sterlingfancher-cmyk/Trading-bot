"""Paper-mode capital participation allocator.

This module is loaded by sitecustomize. It is paper-only by default and does
not bypass halts, cooldowns, score floors, sector/bucket exposure checks, stop
losses, or profit guards. It only raises paper-mode capacity and uses the
existing entry path to size new long entries toward a target deployed-capital
range when market conditions are favorable.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "paper-participation-allocator-2026-05-21-v1"
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

ENABLED = os.environ.get("PAPER_PARTICIPATION_ALLOCATOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PAPER_PARTICIPATION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}

MAX_POS_STRONG_RISK_ON = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_STRONG_RISK_ON", "12"))
MAX_POS_RISK_ON = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_RISK_ON", "11"))
MAX_POS_CONSTRUCTIVE = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_CONSTRUCTIVE", "9"))
MAX_POS_NEUTRAL = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_NEUTRAL", "6"))
MAX_POS_DEFENSIVE = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_DEFENSIVE", "4"))
MAX_POS_RISK_OFF = int(os.environ.get("PAPER_PARTICIPATION_MAX_POS_RISK_OFF", "3"))

MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("PAPER_PARTICIPATION_MAX_NEW_ENTRIES_PER_CYCLE", "4"))
BASE_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_PARTICIPATION_BASE_MAX_POSITIONS_PER_SECTOR", "5"))
TECH_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_PARTICIPATION_TECH_MAX_POSITIONS_PER_SECTOR", "7"))
BASE_MAX_SECTOR_EXPOSURE = float(os.environ.get("PAPER_PARTICIPATION_BASE_MAX_SECTOR_EXPOSURE", "0.55"))
TECH_MAX_SECTOR_EXPOSURE = float(os.environ.get("PAPER_PARTICIPATION_TECH_MAX_SECTOR_EXPOSURE", "0.75"))
TECH_CAUTION_SECTOR_EXPOSURE = float(os.environ.get("PAPER_PARTICIPATION_TECH_CAUTION_SECTOR_EXPOSURE", "0.68"))

TARGET_STRONG_RISK_ON = float(os.environ.get("PAPER_TARGET_EXPOSURE_STRONG_RISK_ON", "0.62"))
TARGET_RISK_ON = float(os.environ.get("PAPER_TARGET_EXPOSURE_RISK_ON", "0.55"))
TARGET_CONSTRUCTIVE = float(os.environ.get("PAPER_TARGET_EXPOSURE_CONSTRUCTIVE", "0.45"))
TARGET_NEUTRAL = float(os.environ.get("PAPER_TARGET_EXPOSURE_NEUTRAL", "0.32"))
TARGET_DEFENSIVE = float(os.environ.get("PAPER_TARGET_EXPOSURE_DEFENSIVE", "0.18"))
TARGET_RISK_OFF = float(os.environ.get("PAPER_TARGET_EXPOSURE_RISK_OFF", "0.08"))

MIN_ENTRY_ALLOC_PCT = float(os.environ.get("PAPER_PARTICIPATION_MIN_ENTRY_ALLOC_PCT", "0.025"))
MAX_ENTRY_ALLOC_PCT = float(os.environ.get("PAPER_PARTICIPATION_MAX_ENTRY_ALLOC_PCT", "0.095"))
STRONG_MAX_ENTRY_ALLOC_PCT = float(os.environ.get("PAPER_PARTICIPATION_STRONG_MAX_ENTRY_ALLOC_PCT", "0.105"))
CASH_RESERVE_PCT = float(os.environ.get("PAPER_PARTICIPATION_CASH_RESERVE_PCT", "0.20"))
MIN_GAP_DOLLARS = float(os.environ.get("PAPER_PARTICIPATION_MIN_GAP_DOLLARS", "125"))

BUCKET_OVERRIDES = {
    "mega_cap_ai": {"max_positions": 5, "max_exposure_pct": 0.70},
    "semi_leaders": {"max_positions": 6, "max_exposure_pct": 0.75},
    "cloud_cyber_software": {"max_positions": 5, "max_exposure_pct": 0.55},
    "data_center_infra": {"max_positions": 6, "max_exposure_pct": 0.62},
    "bitcoin_ai_compute": {"max_positions": 5, "max_exposure_pct": 0.40},
    "small_cap_momentum": {"max_positions": 4, "max_exposure_pct": 0.28},
    "benchmark_etf": {"max_positions": 3, "max_exposure_pct": 0.40},
    "ai_cloud_breakout": {"max_positions": 4, "max_exposure_pct": 0.42},
    "power_grid_data_center": {"max_positions": 4, "max_exposure_pct": 0.46},
    "data_center_breakout": {"max_positions": 5, "max_exposure_pct": 0.52},
}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "try_entries_and_rotations"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "try_entries_and_rotations"):
            return m
    return None


def _now_text(m: Any | None = None) -> str:
    try:
        return m.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _portfolio(m: Any | None) -> Dict[str, Any]:
    return getattr(m, "portfolio", {}) if m is not None else {}


def _is_paper_context(m: Any | None) -> bool:
    if not PAPER_ONLY:
        return True
    live_requested = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    route_hint = True
    try:
        route_hint = any(str(rule.rule).startswith("/paper") for rule in m.app.url_map.iter_rules())
    except Exception:
        route_hint = True
    return route_hint and not live_requested and not broker_live


def _positions_count(m: Any | None) -> int:
    try:
        return len((_portfolio(m).get("positions", {}) or {}))
    except Exception:
        return 0


def _growth_confirmed(market: Dict[str, Any]) -> bool:
    try:
        risk_on_sector_count = int(market.get("risk_on_sector_count", 0) or 0)
    except Exception:
        risk_on_sector_count = 0
    return bool(
        market.get("growth_leadership")
        or (market.get("defensive_leadership") is False and risk_on_sector_count >= 2)
        or str(market.get("market_mode", "")).lower() == "risk_on"
    )


def position_target(market: Dict[str, Any] | None, m: Any | None = None) -> Dict[str, Any]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    risk_score = _i(market.get("risk_score"), 0)
    current = _positions_count(m)
    bear = bool(market.get("bear_confirmed", False))
    soft = bool(market.get("broad_market_soft", False))
    growth = _growth_confirmed(market)

    if bear or mode in {"risk_off", "crash_warning"}:
        target, tier, reason = MAX_POS_RISK_OFF, "risk_off_defensive", "bear_or_risk_off"
    elif mode == "risk_on" and growth and risk_score >= 70:
        target, tier, reason = MAX_POS_STRONG_RISK_ON, "strong_risk_on_expanded_paper", "risk_on_growth_leadership"
    elif mode == "risk_on":
        target, tier, reason = MAX_POS_RISK_ON, "risk_on_expanded_paper", "risk_on"
    elif mode == "constructive" and not soft:
        target, tier, reason = MAX_POS_CONSTRUCTIVE, "constructive_expanded_paper", "constructive_not_broadly_soft"
    elif mode == "neutral":
        target, tier, reason = MAX_POS_NEUTRAL, "neutral_standard", "neutral_market"
    else:
        target, tier, reason = MAX_POS_DEFENSIVE, "defensive_reduced", "defensive_or_soft_market"

    return {
        "target_max_positions": int(max(0, target)),
        "current_positions": int(current),
        "remaining_slots": int(max(0, int(target) - int(current))),
        "tier": tier,
        "reason": reason,
        "market_mode": mode,
        "risk_score": risk_score,
        "growth_confirmed": bool(growth),
        "broad_market_soft": bool(soft),
        "bear_confirmed": bool(bear),
    }


def _position_market_value(m: Any, symbol: str, pos: Dict[str, Any]) -> float:
    try:
        px = float(pos.get("last_price", pos.get("entry", 0.0)) or 0.0)
        value = abs(float(m.position_value(pos, px)))
        if value > 0:
            return value
    except Exception:
        pass
    try:
        shares = abs(float(pos.get("shares", 0.0) or 0.0))
        px = float(pos.get("last_price", pos.get("entry", 0.0)) or 0.0)
        if pos.get("side", "long") == "short":
            return abs(float(pos.get("margin", shares * px) or shares * px))
        return shares * px
    except Exception:
        return 0.0


def deployed_status(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    p = _portfolio(m)
    equity = max(_f(p.get("equity", p.get("cash", 0.0)), 0.0), 0.01)
    cash = max(_f(p.get("cash", 0.0), 0.0), 0.0)
    position_value = 0.0
    try:
        for symbol, pos in (p.get("positions", {}) or {}).items():
            if isinstance(pos, dict):
                position_value += _position_market_value(m, symbol, pos)
    except Exception:
        position_value = 0.0
    implied_deployed = max(0.0, equity - cash)
    deployed = max(implied_deployed, position_value)
    return {
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "cash_pct": round((cash / equity) * 100.0, 2),
        "deployed_capital": round(deployed, 2),
        "deployed_pct": round((deployed / equity) * 100.0, 2),
        "position_value": round(position_value, 2),
        "implied_deployed": round(implied_deployed, 2),
        "positions_count": _positions_count(m),
    }


def _target_exposure(market: Dict[str, Any], m: Any | None) -> Tuple[float, str]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    risk_score = _i(market.get("risk_score"), 0)
    growth = _growth_confirmed(market)
    soft = bool(market.get("broad_market_soft", False))
    bear = bool(market.get("bear_confirmed", False))

    if bear or mode in {"risk_off", "crash_warning"}:
        target, tier = TARGET_RISK_OFF, "risk_off_capital_defense"
    elif mode == "risk_on" and growth and risk_score >= 70:
        target, tier = TARGET_STRONG_RISK_ON, "strong_risk_on_target"
    elif mode == "risk_on":
        target, tier = TARGET_RISK_ON, "risk_on_target"
    elif mode == "constructive" and not soft:
        target, tier = TARGET_CONSTRUCTIVE, "constructive_target"
    elif mode == "neutral":
        target, tier = TARGET_NEUTRAL, "neutral_target"
    else:
        target, tier = TARGET_DEFENSIVE, "defensive_target"

    futures = market.get("futures_bias", {}) or {}
    breadth = market.get("breadth", {}) or {}
    if futures.get("action") == "block_opening_longs":
        target *= 0.55
        tier += "_futures_block_reduced"
    elif futures.get("action") in {"gap_chase_protection", "reduce_aggression", "tech_caution"}:
        target *= 0.90
        tier += "_futures_caution"
    if breadth.get("action") in {"reduce_aggression", "tech_caution"}:
        target *= 0.92
        tier += "_breadth_caution"

    try:
        p = _portfolio(m)
        rc = p.get("risk_controls", {}) or {}
        feedback = p.get("feedback_loop", {}) or {}
        if bool(rc.get("halted")) or bool(rc.get("profit_guard_active")) or bool(feedback.get("block_new_entries")) or bool(feedback.get("hard_halt")):
            current = deployed_status(m).get("deployed_pct", 0.0) / 100.0
            target = min(target, current)
            tier += "_entry_guard_no_expand"
    except Exception:
        pass

    return _clamp(target, 0.0, 0.90), tier


def participation_plan(market: Dict[str, Any] | None, params: Dict[str, Any] | None = None, m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    market = market or {}
    params = params or {}
    exposure = deployed_status(m)
    equity = max(_f(exposure.get("equity"), 0.0), 0.01)
    cash = max(_f(exposure.get("cash"), 0.0), 0.0)
    deployed = max(_f(exposure.get("deployed_capital"), 0.0), 0.0)
    target_pct, target_tier = _target_exposure(market, m)
    pos_target = position_target(market, m)
    max_positions = max(_i(params.get("max_positions"), 0), _i(pos_target.get("target_max_positions"), 0))
    current_positions = _positions_count(m)
    remaining_slots = max(0, max_positions - current_positions)
    reserve_cash = equity * CASH_RESERVE_PCT
    max_deployable_cash = max(0.0, cash - reserve_cash)
    target_dollars = equity * target_pct
    exposure_gap = max(0.0, target_dollars - deployed)
    raw_entry = exposure_gap / max(remaining_slots, 1) if remaining_slots > 0 else 0.0
    max_entry_pct = STRONG_MAX_ENTRY_ALLOC_PCT if pos_target.get("tier") == "strong_risk_on_expanded_paper" else MAX_ENTRY_ALLOC_PCT
    max_entry = equity * max_entry_pct
    min_entry = equity * MIN_ENTRY_ALLOC_PCT
    desired = min(raw_entry, max_entry, max_deployable_cash)
    if exposure_gap >= max(MIN_GAP_DOLLARS, min_entry) and remaining_slots > 0:
        desired = max(desired, min_entry)
        desired = min(desired, exposure_gap, max_entry, max_deployable_cash)
    active = bool(
        ENABLED and _is_paper_context(m) and remaining_slots > 0
        and exposure_gap >= MIN_GAP_DOLLARS and max_deployable_cash > 0
        and desired >= max(1.0, min_entry * 0.40)
    )
    return {
        "enabled": bool(ENABLED and _is_paper_context(m)),
        "active": bool(active),
        "version": VERSION,
        "target_tier": target_tier,
        "target_exposure_pct": round(target_pct * 100.0, 2),
        "target_deployed_dollars": round(target_dollars, 2),
        "current_deployed_dollars": round(deployed, 2),
        "current_deployed_pct": exposure.get("deployed_pct"),
        "cash": round(cash, 2),
        "cash_pct": exposure.get("cash_pct"),
        "cash_reserve_pct": round(CASH_RESERVE_PCT * 100.0, 2),
        "max_deployable_cash": round(max_deployable_cash, 2),
        "exposure_gap_dollars": round(exposure_gap, 2),
        "max_positions": int(max_positions),
        "current_positions": int(current_positions),
        "remaining_slots": int(remaining_slots),
        "raw_entry_alloc": round(raw_entry, 2),
        "desired_entry_alloc": round(desired, 2),
        "desired_entry_alloc_pct": round((desired / equity) * 100.0, 2),
        "min_entry_alloc_pct": round(MIN_ENTRY_ALLOC_PCT * 100.0, 2),
        "max_entry_alloc_pct": round(max_entry_pct * 100.0, 2),
        "position_target": pos_target,
    }


def _base_estimated(m: Any, signal: Dict[str, Any], params: Dict[str, Any]) -> float:
    fn = getattr(getattr(m, "estimated_trade_allocation", None), "_paper_participation_original", None)
    if fn is None:
        fn = getattr(m, "estimated_trade_allocation", None)
    if fn is None or getattr(fn, "_paper_participation_patched", False):
        return 0.0
    try:
        return max(0.0, float(fn(signal, params)))
    except Exception:
        return 0.0


def _target_alloc_for_signal(signal: Dict[str, Any], params: Dict[str, Any], m: Any) -> Tuple[float | None, Dict[str, Any]]:
    if not ENABLED or not _is_paper_context(m):
        return None, {"active": False, "reason": "allocator_disabled_or_not_paper", "version": VERSION}
    if not isinstance(signal, dict) or signal.get("side", "long") != "long":
        return None, {"active": False, "reason": "long_only", "version": VERSION}
    market = _portfolio(m).get("last_market") or {}
    plan = participation_plan(market, params, m)
    if not plan.get("active"):
        return None, {**plan, "reason": "plan_inactive"}
    cash = max(_f(_portfolio(m).get("cash"), 0.0), 0.0)
    desired = min(_f(plan.get("desired_entry_alloc"), 0.0), cash)
    base = _base_estimated(m, signal, params)
    target = min(max(base, desired), cash)
    if target <= 0:
        return None, {**plan, "reason": "no_target_alloc"}
    return target, {
        **plan,
        "active": True,
        "symbol": signal.get("symbol"),
        "base_estimated_alloc": round(base, 2),
        "adjusted_alloc": round(target, 2),
        "adjustment_dollars": round(target - base, 2),
        "reason": "paper_target_exposure_gap_allocator",
    }


def _params_for_target(signal: Dict[str, Any], params: Dict[str, Any], target_alloc: float, m: Any) -> Dict[str, Any]:
    patched = dict(params or {})
    try:
        symbol = signal.get("symbol", "")
        equity = max(_f(_portfolio(m).get("equity", _portfolio(m).get("cash", 0.0)), 0.0), 0.01)
        alloc_factor = _clamp(_f(signal.get("alloc_factor", 1.0), 1.0), 0.05, 1.0)
        bucket_factor = max(0.05, _f(m.bucket_alloc_factor(symbol), 1.0))
        needed = float(target_alloc) / max(0.000001, equity * alloc_factor * bucket_factor)
        patched["long_alloc_pct"] = max(_f(patched.get("long_alloc_pct"), 0.0), needed)
        patched["paper_participation_long_alloc_pct"] = round(float(patched["long_alloc_pct"]), 6)
    except Exception:
        pass
    return patched


def _patch_limits(m: Any) -> Dict[str, Any]:
    changed: Dict[str, Any] = {}
    pairs = [
        ("MAX_NEW_ENTRIES_PER_CYCLE", MAX_NEW_ENTRIES_PER_CYCLE, "max_new_entries_per_cycle", int),
        ("MAX_POSITIONS_PER_SECTOR", BASE_MAX_POSITIONS_PER_SECTOR, "base_max_positions_per_sector", int),
        ("TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", TECH_MAX_POSITIONS_PER_SECTOR, "tech_max_positions_per_sector", int),
    ]
    for attr, minimum, key, caster in pairs:
        try:
            if hasattr(m, attr):
                old = caster(getattr(m, attr, 0))
                if old < minimum:
                    setattr(m, attr, minimum)
                changed[key] = caster(getattr(m, attr, old))
        except Exception:
            pass
    float_pairs = [
        ("MAX_SECTOR_EXPOSURE_PCT", BASE_MAX_SECTOR_EXPOSURE, "base_max_sector_exposure_pct"),
        ("TECH_LEADERSHIP_MAX_EXPOSURE_PCT", TECH_MAX_SECTOR_EXPOSURE, "tech_max_sector_exposure_pct"),
        ("TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT", TECH_CAUTION_SECTOR_EXPOSURE, "tech_caution_sector_exposure_pct"),
    ]
    for attr, minimum, key in float_pairs:
        try:
            if hasattr(m, attr):
                old = float(getattr(m, attr, 0.0))
                if old < minimum:
                    setattr(m, attr, minimum)
                changed[key] = round(float(getattr(m, attr, old)) * 100.0, 2)
        except Exception:
            pass
    try:
        cfg = getattr(m, "BUCKET_CONFIG", {}) or {}
        for bucket, overrides in BUCKET_OVERRIDES.items():
            current = cfg.setdefault(bucket, {"alloc_factor": 0.55, "max_exposure_pct": 0.30, "max_positions": 2})
            current["max_positions"] = max(int(current.get("max_positions", 0)), int(overrides["max_positions"]))
            current["max_exposure_pct"] = max(float(current.get("max_exposure_pct", 0.0)), float(overrides["max_exposure_pct"]))
        m.BUCKET_CONFIG = cfg
        changed["bucket_overrides"] = {
            b: {
                "max_positions": int((cfg.get(b) or {}).get("max_positions", 0)),
                "max_exposure_pct": round(float((cfg.get(b) or {}).get("max_exposure_pct", 0.0)) * 100.0, 2),
            }
            for b in sorted(BUCKET_OVERRIDES) if b in cfg
        }
    except Exception:
        pass
    return changed


def _patch_aggression(m: Any) -> bool:
    if getattr(m.apply_aggression_adjustments, "_paper_participation_patched", False):
        return False
    original = m.apply_aggression_adjustments

    def patched_apply_aggression_adjustments(params, market):
        out = original(params, market)
        if not ENABLED or not _is_paper_context(m):
            return out
        try:
            target = position_target(market or {}, m)
            old_max = int(out.get("max_positions", 0) or 0)
            effective_max = max(old_max, int(target["target_max_positions"]), _positions_count(m))
            out["max_positions"] = effective_max
            out["paper_participation_allocator"] = participation_plan(market or {}, out, m)
            out["paper_position_expansion_v2"] = {
                **target,
                "previous_max_positions": old_max,
                "effective_max_positions": effective_max,
                "version": VERSION,
            }
        except Exception as exc:
            out["paper_participation_allocator"] = {"active": False, "error": str(exc), "version": VERSION}
        return out

    patched_apply_aggression_adjustments._paper_participation_patched = True
    patched_apply_aggression_adjustments._paper_participation_original = original
    m.apply_aggression_adjustments = patched_apply_aggression_adjustments
    return True


def _patch_estimated(m: Any) -> bool:
    if not hasattr(m, "estimated_trade_allocation"):
        return False
    if getattr(m.estimated_trade_allocation, "_paper_participation_patched", False):
        return False
    original = m.estimated_trade_allocation

    def patched_estimated_trade_allocation(signal, params):
        base = original(signal, params)
        try:
            target, _info = _target_alloc_for_signal(signal, params, m)
            if target is None:
                return base
            return min(max(float(base or 0.0), float(target)), max(_f(_portfolio(m).get("cash"), 0.0), 0.0))
        except Exception:
            return base

    patched_estimated_trade_allocation._paper_participation_patched = True
    patched_estimated_trade_allocation._paper_participation_original = original
    m.estimated_trade_allocation = patched_estimated_trade_allocation
    return True


def _patch_enter(m: Any) -> bool:
    if not hasattr(m, "enter_position"):
        return False
    if getattr(m.enter_position, "_paper_participation_patched", False):
        return False
    original = m.enter_position

    def patched_enter_position(signal, params, market_mode=None):
        patched_params = params
        info = None
        try:
            target, allocation_info = _target_alloc_for_signal(signal, params, m)
            if target is not None:
                patched_params = _params_for_target(signal, params, target, m)
                info = allocation_info
        except Exception as exc:
            info = {"active": False, "error": str(exc), "version": VERSION}

        result = original(signal, patched_params, market_mode=market_mode)
        if info and isinstance(result, dict) and not result.get("blocked"):
            try:
                result["paper_participation_allocator"] = info
                symbol = result.get("symbol") or (signal or {}).get("symbol")
                pos = (_portfolio(m).get("positions", {}) or {}).get(symbol)
                if isinstance(pos, dict):
                    pos["allocation_model"] = "paper_participation_allocator"
                    pos["paper_participation_allocator"] = info
                trades = _portfolio(m).get("trades", []) or []
                if trades:
                    last = trades[-1]
                    if isinstance(last, dict) and last.get("action") == "entry" and last.get("symbol") == symbol:
                        last["allocation_model"] = "paper_participation_allocator"
                        last["paper_participation_allocator"] = info
            except Exception:
                pass
        return result

    patched_enter_position._paper_participation_patched = True
    patched_enter_position._paper_participation_original = original
    m.enter_position = patched_enter_position
    return True


def status(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "paper_participation_status", "version": VERSION, "reason": "app_module_not_ready"}
    market = _portfolio(m).get("last_market") or {}
    try:
        params = m.apply_aggression_adjustments(m.risk_parameters(market), market)
    except Exception:
        params = {}
    return {
        "status": "ok",
        "type": "paper_participation_status",
        "version": VERSION,
        "generated_local": _now_text(m),
        "enabled": bool(ENABLED and _is_paper_context(m)),
        "paper_context": bool(_is_paper_context(m)),
        "deployed_capital": deployed_status(m),
        "participation_plan": participation_plan(market, params, m),
        "positions": list((_portfolio(m).get("positions", {}) or {}).keys()),
        "effective_max_positions": int((params or {}).get("max_positions", 0) or 0),
        "max_new_entries_per_cycle": int(getattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", 0)),
        "sector_limits": {
            "base_max_positions_per_sector": int(getattr(m, "MAX_POSITIONS_PER_SECTOR", 0)),
            "tech_max_positions_per_sector": int(getattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", 0)),
            "base_max_sector_exposure_pct": round(_f(getattr(m, "MAX_SECTOR_EXPOSURE_PCT", 0.0)) * 100.0, 2),
            "tech_max_sector_exposure_pct": round(_f(getattr(m, "TECH_LEADERSHIP_MAX_EXPOSURE_PCT", 0.0)) * 100.0, 2),
            "tech_caution_sector_exposure_pct": round(_f(getattr(m, "TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT", 0.0)) * 100.0, 2),
        },
        "latest_cycle": (_portfolio(m).get("paper_participation_allocator") or {}),
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "paper_participation_status", "version": VERSION, "reason": "app_module_not_ready"}
    changes = _patch_limits(m) if ENABLED and _is_paper_context(m) else {}
    patched_aggression = _patch_aggression(m)
    patched_estimated = _patch_estimated(m)
    patched_enter = _patch_enter(m)
    PATCHED_MODULE_IDS.add(id(m))
    payload = status(m)
    payload.update({
        "patched_aggression": bool(patched_aggression or getattr(m.apply_aggression_adjustments, "_paper_participation_patched", False)),
        "patched_estimated_allocation": bool(patched_estimated or getattr(getattr(m, "estimated_trade_allocation", object()), "_paper_participation_patched", False)),
        "patched_enter_position": bool(patched_enter or getattr(getattr(m, "enter_position", object()), "_paper_participation_patched", False)),
        "runtime_limit_changes": changes,
    })
    try:
        _portfolio(m)["paper_participation_allocator_status"] = payload
    except Exception:
        pass
    return payload


def register_routes(flask_app: Any) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def paper_participation_status():
        return jsonify(apply_runtime_overrides(_mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/paper-participation-status" not in existing:
        flask_app.add_url_rule("/paper/paper-participation-status", "paper_participation_status", paper_participation_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(_mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
