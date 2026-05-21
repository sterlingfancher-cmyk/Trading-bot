"""Paper exposure expansion and breakout rotation authority.

This module is loaded by sitecustomize. It is state-safe: it patches runtime
parameters and decision functions, and adds diagnostic routes. It does not
bypass halts, cooldowns, stop losses, or account state reconciliation.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "paper-exposure-breakout-rotation-2026-05-21-v1"

PATCHED_MODULE_IDS: set[int] = set()
REGISTERED_APP_IDS: set[int] = set()

PAPER_EXPOSURE_EXPANSION_ENABLED = os.environ.get(
    "PAPER_EXPOSURE_EXPANSION_ENABLED", "true"
).lower() not in {"0", "false", "no", "off"}
PAPER_ONLY_UNLESS_EXPLICIT_LIVE = os.environ.get(
    "PAPER_EXPOSURE_PAPER_ONLY", "true"
).lower() not in {"0", "false", "no", "off"}

PAPER_MAX_POSITIONS_STRONG_RISK_ON = int(os.environ.get("PAPER_MAX_POSITIONS_STRONG_RISK_ON", "10"))
PAPER_MAX_POSITIONS_RISK_ON = int(os.environ.get("PAPER_MAX_POSITIONS_RISK_ON", "9"))
PAPER_MAX_POSITIONS_CONSTRUCTIVE = int(os.environ.get("PAPER_MAX_POSITIONS_CONSTRUCTIVE", "8"))
PAPER_MAX_POSITIONS_NEUTRAL = int(os.environ.get("PAPER_MAX_POSITIONS_NEUTRAL", "6"))
PAPER_MAX_POSITIONS_DEFENSIVE = int(os.environ.get("PAPER_MAX_POSITIONS_DEFENSIVE", "4"))
PAPER_MAX_POSITIONS_RISK_OFF = int(os.environ.get("PAPER_MAX_POSITIONS_RISK_OFF", "3"))

PAPER_MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("PAPER_MAX_NEW_ENTRIES_PER_CYCLE", "3"))
PAPER_TECH_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_TECH_MAX_POSITIONS_PER_SECTOR", "6"))
PAPER_BASE_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_BASE_MAX_POSITIONS_PER_SECTOR", "4"))

BREAKOUT_ROTATION_ENABLED = os.environ.get(
    "BREAKOUT_ROTATION_AUTHORITY_ENABLED", "true"
).lower() not in {"0", "false", "no", "off"}
BREAKOUT_ROTATION_MIN_HOLD_SECONDS = int(os.environ.get("BREAKOUT_ROTATION_MIN_HOLD_SECONDS", "900"))
BREAKOUT_ROTATION_MIN_SCORE_EDGE = float(os.environ.get("BREAKOUT_ROTATION_MIN_SCORE_EDGE", "0.004"))
BREAKOUT_ROTATION_EXCEPTIONAL_SCORE = float(os.environ.get("BREAKOUT_ROTATION_EXCEPTIONAL_SCORE", "0.045"))
BREAKOUT_ROTATION_KEEP_WINNER_PCT = float(os.environ.get("BREAKOUT_ROTATION_KEEP_WINNER_PCT", "0.008"))
BREAKOUT_ROTATION_LOSER_OVERRIDE_PCT = float(os.environ.get("BREAKOUT_ROTATION_LOSER_OVERRIDE_PCT", "-0.004"))
BREAKOUT_ROTATION_MAX_PARABOLIC_WEAK_PNL_PCT = float(os.environ.get("BREAKOUT_ROTATION_MAX_PARABOLIC_WEAK_PNL_PCT", "-0.002"))

BUCKET_LIMIT_OVERRIDES = {
    "semi_leaders": {"max_positions": 5, "max_exposure_pct": 0.68},
    "cloud_cyber_software": {"max_positions": 4, "max_exposure_pct": 0.50},
    "data_center_infra": {"max_positions": 5, "max_exposure_pct": 0.52},
    "bitcoin_ai_compute": {"max_positions": 4, "max_exposure_pct": 0.34},
    "small_cap_momentum": {"max_positions": 3, "max_exposure_pct": 0.22},
    "ai_cloud_breakout": {"max_positions": 4, "max_exposure_pct": 0.38},
    "power_grid_data_center": {"max_positions": 3, "max_exposure_pct": 0.42},
    "data_center_breakout": {"max_positions": 4, "max_exposure_pct": 0.45},
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


def _is_paper_context(m: Any | None) -> bool:
    if not PAPER_ONLY_UNLESS_EXPLICIT_LIVE:
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
        return len((m.portfolio.get("positions", {}) or {}))
    except Exception:
        return 0


def _growth_breadth_confirmed(market: Dict[str, Any]) -> bool:
    try:
        risk_on_sector_count = int(market.get("risk_on_sector_count", 0) or 0)
    except Exception:
        risk_on_sector_count = 0
    return bool(
        market.get("growth_leadership")
        or market.get("defensive_leadership") is False and risk_on_sector_count >= 2
        or str(market.get("market_mode", "")).lower() == "risk_on"
    )


def effective_position_target(market: Dict[str, Any] | None, m: Any | None = None) -> Dict[str, Any]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    risk_score = _i(market.get("risk_score"), 0)
    current = _positions_count(m)
    bear_confirmed = bool(market.get("bear_confirmed", False))
    broad_soft = bool(market.get("broad_market_soft", False))
    growth_confirmed = _growth_breadth_confirmed(market)

    if bear_confirmed or mode in {"risk_off", "crash_warning"}:
        target = PAPER_MAX_POSITIONS_RISK_OFF
        tier = "risk_off_defensive"
        reason = "bear_or_risk_off"
    elif mode == "risk_on" and growth_confirmed and risk_score >= 70:
        target = PAPER_MAX_POSITIONS_STRONG_RISK_ON
        tier = "strong_risk_on_expanded_paper"
        reason = "risk_on_growth_leadership"
    elif mode == "risk_on":
        target = PAPER_MAX_POSITIONS_RISK_ON
        tier = "risk_on_expanded_paper"
        reason = "risk_on"
    elif mode == "constructive" and not broad_soft:
        target = PAPER_MAX_POSITIONS_CONSTRUCTIVE
        tier = "constructive_expanded_paper"
        reason = "constructive_not_broadly_soft"
    elif mode == "neutral":
        target = PAPER_MAX_POSITIONS_NEUTRAL
        tier = "neutral_standard"
        reason = "neutral_market"
    else:
        target = PAPER_MAX_POSITIONS_DEFENSIVE
        tier = "defensive_reduced"
        reason = "defensive_or_soft_market"

    return {
        "target_max_positions": int(max(0, target)),
        "current_positions": int(current),
        "tier": tier,
        "reason": reason,
        "market_mode": mode,
        "risk_score": risk_score,
        "growth_confirmed": bool(growth_confirmed),
        "broad_market_soft": bool(broad_soft),
        "bear_confirmed": bool(bear_confirmed),
    }


def _patch_bucket_and_sector_limits(m: Any) -> Dict[str, Any]:
    changed = {}
    try:
        if hasattr(m, "MAX_NEW_ENTRIES_PER_CYCLE"):
            old = int(getattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", 0))
            if old < PAPER_MAX_NEW_ENTRIES_PER_CYCLE:
                setattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", PAPER_MAX_NEW_ENTRIES_PER_CYCLE)
            changed["max_new_entries_per_cycle"] = int(getattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", old))
    except Exception:
        pass

    try:
        if hasattr(m, "MAX_POSITIONS_PER_SECTOR"):
            old = int(getattr(m, "MAX_POSITIONS_PER_SECTOR", 0))
            if old < PAPER_BASE_MAX_POSITIONS_PER_SECTOR:
                setattr(m, "MAX_POSITIONS_PER_SECTOR", PAPER_BASE_MAX_POSITIONS_PER_SECTOR)
            changed["base_max_positions_per_sector"] = int(getattr(m, "MAX_POSITIONS_PER_SECTOR", old))
    except Exception:
        pass

    try:
        if hasattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR"):
            old = int(getattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", 0))
            if old < PAPER_TECH_MAX_POSITIONS_PER_SECTOR:
                setattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", PAPER_TECH_MAX_POSITIONS_PER_SECTOR)
            changed["tech_max_positions_per_sector"] = int(getattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", old))
    except Exception:
        pass

    try:
        cfg = getattr(m, "BUCKET_CONFIG", {}) or {}
        for bucket, overrides in BUCKET_LIMIT_OVERRIDES.items():
            current = cfg.setdefault(bucket, {"alloc_factor": 0.55, "max_exposure_pct": 0.30, "max_positions": 2})
            current["max_positions"] = max(int(current.get("max_positions", 0)), int(overrides["max_positions"]))
            current["max_exposure_pct"] = max(float(current.get("max_exposure_pct", 0.0)), float(overrides["max_exposure_pct"]))
        m.BUCKET_CONFIG = cfg
        changed["bucket_overrides"] = {
            k: {
                "max_positions": int((cfg.get(k) or {}).get("max_positions", 0)),
                "max_exposure_pct": round(float((cfg.get(k) or {}).get("max_exposure_pct", 0.0)), 4),
            }
            for k in sorted(BUCKET_LIMIT_OVERRIDES)
            if k in cfg
        }
    except Exception:
        pass

    return changed


def _patch_aggression(m: Any) -> bool:
    if getattr(m.apply_aggression_adjustments, "_paper_exposure_patched", False):
        return False

    original = m.apply_aggression_adjustments

    def patched_apply_aggression_adjustments(params, market):
        out = original(params, market)
        if not PAPER_EXPOSURE_EXPANSION_ENABLED or not _is_paper_context(m):
            return out

        try:
            expansion = effective_position_target(market or {}, m)
            old_max = int(out.get("max_positions", 0) or 0)
            target = int(expansion["target_max_positions"])
            # Never shrink below the number already open; normal exits still reduce risk.
            target = max(target, _positions_count(m))
            out["max_positions"] = max(old_max, target)
            out["paper_position_expansion"] = {
                **expansion,
                "previous_max_positions": old_max,
                "effective_max_positions": int(out.get("max_positions", old_max)),
                "enabled": True,
                "paper_only": PAPER_ONLY_UNLESS_EXPLICIT_LIVE,
                "version": VERSION,
            }
        except Exception as exc:
            try:
                out["paper_position_expansion"] = {"enabled": False, "error": str(exc), "version": VERSION}
            except Exception:
                pass
        return out

    patched_apply_aggression_adjustments._paper_exposure_patched = True
    patched_apply_aggression_adjustments._paper_exposure_original = original
    m.apply_aggression_adjustments = patched_apply_aggression_adjustments
    return True


def _is_breakout_signal(signal: Dict[str, Any] | None) -> bool:
    if not isinstance(signal, dict):
        return False
    ctx = signal.get("breakout_participation") or {}
    catalyst = signal.get("catalyst") or {}
    return bool(
        ctx.get("active")
        or signal.get("entry_context") == "breakout_participation_starter"
        or signal.get("trade_class") == "breakout_starter"
        or catalyst.get("reason") == "breakout_participation_layer"
    )


def breakout_rotation_allowed(new_signal: Dict[str, Any], weakest: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not BREAKOUT_ROTATION_ENABLED:
        return False, {"reason": "breakout_rotation_disabled", "version": VERSION}
    if not _is_breakout_signal(new_signal):
        return False, {"reason": "not_breakout_signal", "version": VERSION}

    new_score = _f(new_signal.get("score"), 0.0)
    weak_score = _f(weakest.get("score"), 0.0)
    weak_pnl = _f(weakest.get("pnl_pct"), 0.0)
    held = _i(weakest.get("held_seconds"), 0)
    ctx = new_signal.get("breakout_participation") or {}
    risk_tier = str(ctx.get("risk_tier") or "breakout_starter")
    score_edge = new_score - weak_score
    sector_aligned = new_signal.get("sector") in (market.get("sector_leaders", []) or [])

    if weak_pnl >= BREAKOUT_ROTATION_KEEP_WINNER_PCT:
        return False, {
            "reason": "breakout_rotation_keep_winner_guard",
            "weakest_symbol": weakest.get("symbol"),
            "weakest_pnl_pct": round(weak_pnl * 100, 2),
            "keep_winner_pct": round(BREAKOUT_ROTATION_KEEP_WINNER_PCT * 100, 2),
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "version": VERSION,
        }

    if held < BREAKOUT_ROTATION_MIN_HOLD_SECONDS and weak_pnl > BREAKOUT_ROTATION_LOSER_OVERRIDE_PCT:
        return False, {
            "reason": "breakout_rotation_min_hold_not_met",
            "weakest_symbol": weakest.get("symbol"),
            "held_seconds": held,
            "required_hold_seconds": BREAKOUT_ROTATION_MIN_HOLD_SECONDS,
            "weakest_pnl_pct": round(weak_pnl * 100, 2),
            "loser_override_pct": round(BREAKOUT_ROTATION_LOSER_OVERRIDE_PCT * 100, 2),
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "version": VERSION,
        }

    if "parabolic" in risk_tier and weak_pnl > BREAKOUT_ROTATION_MAX_PARABOLIC_WEAK_PNL_PCT:
        return False, {
            "reason": "breakout_rotation_parabolic_requires_lagging_replacement",
            "risk_tier": risk_tier,
            "weakest_symbol": weakest.get("symbol"),
            "weakest_pnl_pct": round(weak_pnl * 100, 2),
            "max_weakest_pnl_pct": round(BREAKOUT_ROTATION_MAX_PARABOLIC_WEAK_PNL_PCT * 100, 2),
            "new_score": round(new_score, 6),
            "version": VERSION,
        }

    if score_edge < BREAKOUT_ROTATION_MIN_SCORE_EDGE and new_score < BREAKOUT_ROTATION_EXCEPTIONAL_SCORE:
        return False, {
            "reason": "breakout_rotation_score_edge_not_met",
            "weakest_symbol": weakest.get("symbol"),
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "score_edge": round(score_edge, 6),
            "required_score_edge": BREAKOUT_ROTATION_MIN_SCORE_EDGE,
            "exceptional_score": BREAKOUT_ROTATION_EXCEPTIONAL_SCORE,
            "version": VERSION,
        }

    return True, {
        "reason": "breakout_rotation_to_stronger_participation",
        "version": VERSION,
        "weakest_symbol": weakest.get("symbol"),
        "new_score": round(new_score, 6),
        "weakest_score": round(weak_score, 6),
        "score_edge": round(score_edge, 6),
        "held_seconds": held,
        "weakest_pnl_pct": round(weak_pnl * 100, 2),
        "risk_tier": risk_tier,
        "sector_aligned": bool(sector_aligned),
        "intraday_move_pct": ctx.get("intraday_move_pct"),
        "volume_surge_ratio": ctx.get("volume_surge_ratio"),
    }


def _patch_rotation_allowed(m: Any) -> bool:
    if getattr(m.rotation_allowed, "_paper_breakout_rotation_patched", False):
        return False

    original = m.rotation_allowed

    def patched_rotation_allowed(new_signal, weakest, market):
        allowed, info = original(new_signal, weakest, market)
        if allowed:
            return allowed, info
        if not PAPER_EXPOSURE_EXPANSION_ENABLED or not _is_paper_context(m):
            return allowed, info
        breakout_ok, breakout_info = breakout_rotation_allowed(new_signal, weakest, market or {})
        if breakout_ok:
            breakout_info["standard_rotation_block"] = info
            return True, breakout_info
        try:
            info = dict(info or {})
            info["breakout_rotation_info"] = breakout_info
        except Exception:
            pass
        return False, info

    patched_rotation_allowed._paper_breakout_rotation_patched = True
    patched_rotation_allowed._paper_breakout_rotation_original = original
    m.rotation_allowed = patched_rotation_allowed
    return True


def _patch_try_entries(m: Any) -> bool:
    if getattr(m.try_entries_and_rotations, "_paper_exposure_debug_patched", False):
        return False

    original = m.try_entries_and_rotations

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        breakout_candidates = {}
        for sig in list(long_signals or []) + list(short_signals or []):
            if isinstance(sig, dict) and _is_breakout_signal(sig):
                breakout_candidates[str(sig.get("symbol", "")).upper()] = {
                    "symbol": sig.get("symbol"),
                    "side": sig.get("side"),
                    "score": sig.get("score"),
                    "entry_context": sig.get("entry_context"),
                    "trade_class": sig.get("trade_class"),
                    "breakout_participation": sig.get("breakout_participation"),
                }

        entries, rotations, blocked_entries = original(
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed,
            entry_block_reason=entry_block_reason,
        )

        blocked_breakouts = []
        for item in blocked_entries or []:
            try:
                sym = str(item.get("symbol", "")).upper()
                if sym in breakout_candidates:
                    merged = dict(item)
                    merged["breakout_candidate"] = breakout_candidates[sym]
                    blocked_breakouts.append(merged)
            except Exception:
                continue

        try:
            m.portfolio["breakout_rotation_authority"] = {
                "status": "ok",
                "type": "breakout_rotation_authority",
                "version": VERSION,
                "generated_local": _now_text(m),
                "enabled": bool(BREAKOUT_ROTATION_ENABLED and PAPER_EXPOSURE_EXPANSION_ENABLED and _is_paper_context(m)),
                "breakout_candidates_count": len(breakout_candidates),
                "blocked_breakout_candidates_count": len(blocked_breakouts),
                "blocked_breakout_candidates": blocked_breakouts[:20],
                "entries_from_breakouts": [
                    e for e in (entries or [])
                    if str(e.get("symbol", "")).upper() in breakout_candidates
                ][:20],
                "rotations_from_breakouts": [
                    r for r in (rotations or [])
                    if str(r.get("in", "")).upper() in breakout_candidates
                ][:20],
                "positions_count": _positions_count(m),
                "max_positions": int((params or {}).get("max_positions", 0) or 0),
                "max_new_entries_per_cycle": int(getattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", 0)),
            }
        except Exception:
            pass

        return entries, rotations, blocked_entries

    patched_try_entries_and_rotations._paper_exposure_debug_patched = True
    patched_try_entries_and_rotations._paper_exposure_debug_original = original
    m.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def exposure_status(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "paper_exposure_status", "version": VERSION, "reason": "app_module_not_ready"}
    try:
        market = m.portfolio.get("last_market") or {}
    except Exception:
        market = {}
    try:
        params = m.apply_aggression_adjustments(m.risk_parameters(market), market)
    except Exception:
        params = {}
    return {
        "status": "ok",
        "type": "paper_exposure_status",
        "version": VERSION,
        "generated_local": _now_text(m),
        "enabled": bool(PAPER_EXPOSURE_EXPANSION_ENABLED and _is_paper_context(m)),
        "paper_context": bool(_is_paper_context(m)),
        "position_target": effective_position_target(market, m),
        "effective_max_positions": int((params or {}).get("max_positions", 0) or 0),
        "positions_count": _positions_count(m),
        "positions": list((getattr(m, "portfolio", {}).get("positions", {}) or {}).keys()),
        "max_new_entries_per_cycle": int(getattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", 0)),
        "sector_limits": {
            "base_max_positions_per_sector": int(getattr(m, "MAX_POSITIONS_PER_SECTOR", 0)),
            "tech_leadership_max_positions_per_sector": int(getattr(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", 0)),
            "max_sector_exposure_pct": round(_f(getattr(m, "MAX_SECTOR_EXPOSURE_PCT", 0.0)) * 100, 2),
            "tech_leadership_max_exposure_pct": round(_f(getattr(m, "TECH_LEADERSHIP_MAX_EXPOSURE_PCT", 0.0)) * 100, 2),
        },
        "bucket_overrides": {
            bucket: {
                "max_positions": int((getattr(m, "BUCKET_CONFIG", {}) or {}).get(bucket, {}).get("max_positions", 0)),
                "max_exposure_pct": round(_f((getattr(m, "BUCKET_CONFIG", {}) or {}).get(bucket, {}).get("max_exposure_pct", 0.0)) * 100, 2),
            }
            for bucket in sorted(BUCKET_LIMIT_OVERRIDES)
            if bucket in (getattr(m, "BUCKET_CONFIG", {}) or {})
        },
        "breakout_rotation": {
            "enabled": bool(BREAKOUT_ROTATION_ENABLED),
            "min_hold_seconds": BREAKOUT_ROTATION_MIN_HOLD_SECONDS,
            "min_score_edge": BREAKOUT_ROTATION_MIN_SCORE_EDGE,
            "exceptional_score": BREAKOUT_ROTATION_EXCEPTIONAL_SCORE,
            "keep_winner_pct": round(BREAKOUT_ROTATION_KEEP_WINNER_PCT * 100, 2),
            "loser_override_pct": round(BREAKOUT_ROTATION_LOSER_OVERRIDE_PCT * 100, 2),
            "latest": (getattr(m, "portfolio", {}).get("breakout_rotation_authority") or {}),
        },
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}

    bucket_changes = {}
    if PAPER_EXPOSURE_EXPANSION_ENABLED and _is_paper_context(m):
        bucket_changes = _patch_bucket_and_sector_limits(m)

    patched_aggression = _patch_aggression(m)
    patched_rotation = _patch_rotation_allowed(m)
    patched_try_entries = _patch_try_entries(m)
    PATCHED_MODULE_IDS.add(id(m))
    payload = exposure_status(m)
    payload.update({
        "patched_aggression": bool(patched_aggression or getattr(m.apply_aggression_adjustments, "_paper_exposure_patched", False)),
        "patched_rotation_allowed": bool(patched_rotation or getattr(m.rotation_allowed, "_paper_breakout_rotation_patched", False)),
        "patched_try_entries": bool(patched_try_entries or getattr(m.try_entries_and_rotations, "_paper_exposure_debug_patched", False)),
        "bucket_changes": bucket_changes,
    })
    return payload


def register_routes(flask_app: Any) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def paper_exposure_status():
        return jsonify(apply_runtime_overrides(_mod()))

    def breakout_rotation_status():
        payload = apply_runtime_overrides(_mod())
        return jsonify({
            "status": payload.get("status", "ok"),
            "type": "breakout_rotation_status",
            "version": VERSION,
            "generated_local": payload.get("generated_local"),
            "breakout_rotation": payload.get("breakout_rotation", {}),
            "positions_count": payload.get("positions_count"),
            "effective_max_positions": payload.get("effective_max_positions"),
            "max_new_entries_per_cycle": payload.get("max_new_entries_per_cycle"),
        })

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/paper-exposure-status" not in existing:
        flask_app.add_url_rule("/paper/paper-exposure-status", "paper_exposure_status", paper_exposure_status)
    if "/paper/breakout-rotation-status" not in existing:
        flask_app.add_url_rule("/paper/breakout-rotation-status", "breakout_rotation_status", breakout_rotation_status)

    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(_mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
