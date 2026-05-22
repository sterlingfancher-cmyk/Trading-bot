"""Paper-only full risk-on tech concentration policy.

The user has explicitly accepted higher technology concentration while the market is
confirmed full risk-on. This module preserves defensive behavior when the regime
weakens: it does not bypass halts, stops, cooldowns, profit guards, score floors,
journal reconciliation, or live-trading protections.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict

VERSION = "risk-on-concentration-policy-2026-05-22-v1"

ENABLED = os.environ.get("PAPER_RISK_ON_CONCENTRATION_POLICY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PAPER_RISK_ON_CONCENTRATION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}

FULL_RISK_ON_MAX_POSITIONS = int(os.environ.get("PAPER_FULL_RISK_ON_MAX_POSITIONS", "14"))
FULL_RISK_ON_MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("PAPER_FULL_RISK_ON_MAX_NEW_ENTRIES_PER_CYCLE", "5"))
FULL_RISK_ON_TECH_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_FULL_RISK_ON_TECH_MAX_POSITIONS_PER_SECTOR", "12"))
FULL_RISK_ON_BASE_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_FULL_RISK_ON_BASE_MAX_POSITIONS_PER_SECTOR", "7"))
FULL_RISK_ON_TECH_MAX_EXPOSURE = float(os.environ.get("PAPER_FULL_RISK_ON_TECH_MAX_EXPOSURE", "0.90"))
FULL_RISK_ON_TECH_CAUTION_EXPOSURE = float(os.environ.get("PAPER_FULL_RISK_ON_TECH_CAUTION_EXPOSURE", "0.82"))
FULL_RISK_ON_BASE_MAX_SECTOR_EXPOSURE = float(os.environ.get("PAPER_FULL_RISK_ON_BASE_MAX_SECTOR_EXPOSURE", "0.70"))
FULL_RISK_ON_TARGET_EXPOSURE = float(os.environ.get("PAPER_FULL_RISK_ON_TARGET_EXPOSURE", "0.76"))
FULL_RISK_ON_CASH_RESERVE = float(os.environ.get("PAPER_FULL_RISK_ON_CASH_RESERVE", "0.10"))

RISK_ON_MAX_POSITIONS = int(os.environ.get("PAPER_RISK_ON_ACCEPTED_MAX_POSITIONS", "12"))
RISK_ON_MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("PAPER_RISK_ON_ACCEPTED_MAX_NEW_ENTRIES_PER_CYCLE", "4"))
RISK_ON_TECH_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("PAPER_RISK_ON_ACCEPTED_TECH_MAX_POSITIONS_PER_SECTOR", "10"))
RISK_ON_TECH_MAX_EXPOSURE = float(os.environ.get("PAPER_RISK_ON_ACCEPTED_TECH_MAX_EXPOSURE", "0.84"))
RISK_ON_TARGET_EXPOSURE = float(os.environ.get("PAPER_RISK_ON_ACCEPTED_TARGET_EXPOSURE", "0.66"))
RISK_ON_CASH_RESERVE = float(os.environ.get("PAPER_RISK_ON_ACCEPTED_CASH_RESERVE", "0.14"))

BASELINES_CAPTURED = False
BASELINES: Dict[str, Dict[str, Any]] = {}
PATCHED_MODULE_IDS: set[int] = set()
REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "apply_aggression_adjustments"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "apply_aggression_adjustments"):
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
        return len((m.portfolio.get("positions", {}) or {}))
    except Exception:
        return 0


def _capture_baselines(m: Any | None = None) -> None:
    global BASELINES_CAPTURED
    if BASELINES_CAPTURED:
        return

    try:
        import paper_participation_allocator as participation
    except Exception:
        participation = None
    try:
        import paper_exposure_rotation as exposure
    except Exception:
        exposure = None

    if participation is not None:
        keys = [
            "MAX_POS_STRONG_RISK_ON", "MAX_POS_RISK_ON", "MAX_NEW_ENTRIES_PER_CYCLE",
            "BASE_MAX_POSITIONS_PER_SECTOR", "TECH_MAX_POSITIONS_PER_SECTOR",
            "BASE_MAX_SECTOR_EXPOSURE", "TECH_MAX_SECTOR_EXPOSURE",
            "TECH_CAUTION_SECTOR_EXPOSURE", "TARGET_STRONG_RISK_ON",
            "TARGET_RISK_ON", "CASH_RESERVE_PCT",
        ]
        BASELINES["participation"] = {k: getattr(participation, k, None) for k in keys}

    if exposure is not None:
        keys = [
            "PAPER_MAX_POSITIONS_STRONG_RISK_ON", "PAPER_MAX_POSITIONS_RISK_ON",
            "PAPER_MAX_NEW_ENTRIES_PER_CYCLE", "PAPER_TECH_MAX_POSITIONS_PER_SECTOR",
            "PAPER_BASE_MAX_POSITIONS_PER_SECTOR",
        ]
        BASELINES["exposure"] = {k: getattr(exposure, k, None) for k in keys}

    if m is not None:
        keys = [
            "MAX_NEW_ENTRIES_PER_CYCLE", "MAX_POSITIONS_PER_SECTOR",
            "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", "MAX_SECTOR_EXPOSURE_PCT",
            "TECH_LEADERSHIP_MAX_EXPOSURE_PCT", "TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT",
        ]
        BASELINES["app"] = {k: getattr(m, k, None) for k in keys if hasattr(m, k)}

    BASELINES_CAPTURED = True


def _growth_confirmed(market: Dict[str, Any]) -> bool:
    try:
        risk_on_sector_count = int(market.get("risk_on_sector_count", 0) or 0)
    except Exception:
        risk_on_sector_count = 0
    tech_state = str(((market.get("tech_leadership") or {}).get("state") or "")).lower()
    return bool(
        market.get("growth_leadership")
        or risk_on_sector_count >= 2
        or tech_state in {"leading", "strong", "risk_on", "confirmed"}
        or str(market.get("market_mode", "")).lower() == "risk_on"
    )


def _market_blocked(market: Dict[str, Any]) -> bool:
    futures = market.get("futures_bias", {}) or {}
    breadth = market.get("breadth", {}) or {}
    return bool(
        market.get("bear_confirmed")
        or market.get("broad_market_soft")
        or str(market.get("market_mode", "")).lower() in {"risk_off", "crash_warning", "defensive"}
        or futures.get("action") == "block_opening_longs"
        or breadth.get("action") == "block_opening_longs"
    )


def policy_profile(market: Dict[str, Any] | None, m: Any | None = None) -> Dict[str, Any]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    risk_score = _i(market.get("risk_score"), 0)
    growth = _growth_confirmed(market)
    blocked = _market_blocked(market)

    if not ENABLED:
        tier, active, reason = "disabled", False, "policy_disabled"
    elif not _is_paper_context(m):
        tier, active, reason = "not_paper", False, "not_paper_context"
    elif blocked:
        tier, active, reason = "normal_defensive_controls", False, "market_not_full_risk_on_or_soft"
    elif mode == "risk_on" and growth and risk_score >= 65:
        tier, active, reason = "full_risk_on_tech_concentration_accepted", True, "risk_on_growth_tech_leadership_confirmed"
    elif mode == "risk_on" and growth:
        tier, active, reason = "risk_on_tech_concentration_accepted", True, "risk_on_growth_confirmed"
    else:
        tier, active, reason = "normal_controls", False, "risk_on_not_confirmed"

    if tier == "full_risk_on_tech_concentration_accepted":
        max_positions = FULL_RISK_ON_MAX_POSITIONS
        max_new = FULL_RISK_ON_MAX_NEW_ENTRIES_PER_CYCLE
        tech_sector_positions = FULL_RISK_ON_TECH_MAX_POSITIONS_PER_SECTOR
        base_sector_positions = FULL_RISK_ON_BASE_MAX_POSITIONS_PER_SECTOR
        tech_exposure = FULL_RISK_ON_TECH_MAX_EXPOSURE
        tech_caution = FULL_RISK_ON_TECH_CAUTION_EXPOSURE
        base_exposure = FULL_RISK_ON_BASE_MAX_SECTOR_EXPOSURE
        target_exposure = FULL_RISK_ON_TARGET_EXPOSURE
        cash_reserve = FULL_RISK_ON_CASH_RESERVE
    elif tier == "risk_on_tech_concentration_accepted":
        max_positions = RISK_ON_MAX_POSITIONS
        max_new = RISK_ON_MAX_NEW_ENTRIES_PER_CYCLE
        tech_sector_positions = RISK_ON_TECH_MAX_POSITIONS_PER_SECTOR
        base_sector_positions = max(5, FULL_RISK_ON_BASE_MAX_POSITIONS_PER_SECTOR - 1)
        tech_exposure = RISK_ON_TECH_MAX_EXPOSURE
        tech_caution = min(RISK_ON_TECH_MAX_EXPOSURE, 0.76)
        base_exposure = max(0.60, FULL_RISK_ON_BASE_MAX_SECTOR_EXPOSURE - 0.08)
        target_exposure = RISK_ON_TARGET_EXPOSURE
        cash_reserve = RISK_ON_CASH_RESERVE
    else:
        max_positions = max_new = tech_sector_positions = base_sector_positions = None
        tech_exposure = tech_caution = base_exposure = target_exposure = cash_reserve = None

    return {
        "active": bool(active),
        "tier": tier,
        "reason": reason,
        "market_mode": mode,
        "risk_score": risk_score,
        "growth_confirmed": bool(growth),
        "market_blocked": bool(blocked),
        "current_positions": _positions_count(m),
        "max_positions": max_positions,
        "max_new_entries_per_cycle": max_new,
        "tech_max_positions_per_sector": tech_sector_positions,
        "base_max_positions_per_sector": base_sector_positions,
        "tech_max_exposure_pct": round(tech_exposure * 100.0, 2) if tech_exposure is not None else None,
        "tech_caution_exposure_pct": round(tech_caution * 100.0, 2) if tech_caution is not None else None,
        "base_max_sector_exposure_pct": round(base_exposure * 100.0, 2) if base_exposure is not None else None,
        "target_exposure_pct": round(target_exposure * 100.0, 2) if target_exposure is not None else None,
        "cash_reserve_pct": round(cash_reserve * 100.0, 2) if cash_reserve is not None else None,
        "paper_only": bool(PAPER_ONLY),
        "version": VERSION,
    }


def _set_attr_if_present(obj: Any, name: str, value: Any) -> None:
    try:
        if obj is not None and hasattr(obj, name) and value is not None:
            setattr(obj, name, value)
    except Exception:
        pass


def _restore_baseline(m: Any | None) -> None:
    _capture_baselines(m)
    try:
        import paper_participation_allocator as participation
    except Exception:
        participation = None
    try:
        import paper_exposure_rotation as exposure
    except Exception:
        exposure = None

    for key, value in (BASELINES.get("participation") or {}).items():
        _set_attr_if_present(participation, key, value)
    for key, value in (BASELINES.get("exposure") or {}).items():
        _set_attr_if_present(exposure, key, value)
    for key, value in (BASELINES.get("app") or {}).items():
        _set_attr_if_present(m, key, value)


def _apply_policy_values(profile: Dict[str, Any], m: Any | None) -> Dict[str, Any]:
    _capture_baselines(m)
    if not profile.get("active"):
        _restore_baseline(m)
        return {"applied": False, "reason": profile.get("reason"), "restored_baseline": True}

    try:
        import paper_participation_allocator as participation
    except Exception:
        participation = None
    try:
        import paper_exposure_rotation as exposure
    except Exception:
        exposure = None

    max_positions = int(profile.get("max_positions") or 0)
    max_new = int(profile.get("max_new_entries_per_cycle") or 0)
    tech_positions = int(profile.get("tech_max_positions_per_sector") or 0)
    base_positions = int(profile.get("base_max_positions_per_sector") or 0)
    tech_exp = _f(profile.get("tech_max_exposure_pct"), 0.0) / 100.0
    tech_caution = _f(profile.get("tech_caution_exposure_pct"), 0.0) / 100.0
    base_exp = _f(profile.get("base_max_sector_exposure_pct"), 0.0) / 100.0
    target_exp = _f(profile.get("target_exposure_pct"), 0.0) / 100.0
    cash_reserve = _f(profile.get("cash_reserve_pct"), 0.0) / 100.0

    if participation is not None:
        _set_attr_if_present(participation, "MAX_POS_STRONG_RISK_ON", max_positions)
        _set_attr_if_present(participation, "MAX_POS_RISK_ON", max(max_positions - 2, RISK_ON_MAX_POSITIONS))
        _set_attr_if_present(participation, "MAX_NEW_ENTRIES_PER_CYCLE", max_new)
        _set_attr_if_present(participation, "BASE_MAX_POSITIONS_PER_SECTOR", base_positions)
        _set_attr_if_present(participation, "TECH_MAX_POSITIONS_PER_SECTOR", tech_positions)
        _set_attr_if_present(participation, "BASE_MAX_SECTOR_EXPOSURE", base_exp)
        _set_attr_if_present(participation, "TECH_MAX_SECTOR_EXPOSURE", tech_exp)
        _set_attr_if_present(participation, "TECH_CAUTION_SECTOR_EXPOSURE", tech_caution)
        _set_attr_if_present(participation, "TARGET_STRONG_RISK_ON", target_exp)
        _set_attr_if_present(participation, "TARGET_RISK_ON", min(target_exp, RISK_ON_TARGET_EXPOSURE))
        _set_attr_if_present(participation, "CASH_RESERVE_PCT", cash_reserve)

    if exposure is not None:
        _set_attr_if_present(exposure, "PAPER_MAX_POSITIONS_STRONG_RISK_ON", max_positions)
        _set_attr_if_present(exposure, "PAPER_MAX_POSITIONS_RISK_ON", max(max_positions - 2, RISK_ON_MAX_POSITIONS))
        _set_attr_if_present(exposure, "PAPER_MAX_NEW_ENTRIES_PER_CYCLE", max_new)
        _set_attr_if_present(exposure, "PAPER_TECH_MAX_POSITIONS_PER_SECTOR", tech_positions)
        _set_attr_if_present(exposure, "PAPER_BASE_MAX_POSITIONS_PER_SECTOR", base_positions)

    _set_attr_if_present(m, "MAX_NEW_ENTRIES_PER_CYCLE", max_new)
    _set_attr_if_present(m, "MAX_POSITIONS_PER_SECTOR", base_positions)
    _set_attr_if_present(m, "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", tech_positions)
    _set_attr_if_present(m, "MAX_SECTOR_EXPOSURE_PCT", base_exp)
    _set_attr_if_present(m, "TECH_LEADERSHIP_MAX_EXPOSURE_PCT", tech_exp)
    _set_attr_if_present(m, "TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT", tech_caution)

    return {
        "applied": True,
        "max_positions": max_positions,
        "max_new_entries_per_cycle": max_new,
        "tech_max_positions_per_sector": tech_positions,
        "tech_max_exposure_pct": round(tech_exp * 100.0, 2),
        "target_exposure_pct": round(target_exp * 100.0, 2),
        "cash_reserve_pct": round(cash_reserve * 100.0, 2),
    }


def _patch_aggression(m: Any) -> bool:
    if not hasattr(m, "apply_aggression_adjustments"):
        return False
    if getattr(m.apply_aggression_adjustments, "_risk_on_concentration_policy_patched", False):
        return False

    original = m.apply_aggression_adjustments

    def patched_apply_aggression_adjustments(params, market):
        profile = policy_profile(market or {}, m)
        applied = _apply_policy_values(profile, m)
        out = original(params, market)
        try:
            if profile.get("active"):
                current = _positions_count(m)
                target = max(int(profile.get("max_positions") or 0), current, int(out.get("max_positions", 0) or 0))
                out["max_positions"] = target
            out["risk_on_concentration_policy"] = {
                **profile,
                "applied": applied,
                "effective_max_positions": int(out.get("max_positions", 0) or 0),
                "guardrails": [
                    "paper_mode_only_by_default",
                    "does_not_bypass_halts",
                    "does_not_bypass_stop_losses",
                    "does_not_bypass_score_floors",
                    "does_not_bypass_state_journal_guards",
                    "automatically_restores_baseline_when_market_is_not_risk_on",
                ],
            }
            try:
                m.portfolio["risk_on_concentration_policy"] = out["risk_on_concentration_policy"]
            except Exception:
                pass
        except Exception:
            pass
        return out

    patched_apply_aggression_adjustments._risk_on_concentration_policy_patched = True
    patched_apply_aggression_adjustments._risk_on_concentration_policy_original = original
    m.apply_aggression_adjustments = patched_apply_aggression_adjustments
    return True


def status(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    market: Dict[str, Any] = {}
    if m is not None:
        try:
            market = m.portfolio.get("last_market") or {}
        except Exception:
            market = {}
    profile = policy_profile(market, m)
    return {
        "status": "ok" if m is not None else "pending",
        "type": "risk_on_concentration_policy_status",
        "version": VERSION,
        "generated_local": _now_text(m),
        "enabled": bool(ENABLED),
        "paper_context": bool(_is_paper_context(m)),
        "module_found": bool(m is not None),
        "profile": profile,
        "baseline_captured": bool(BASELINES_CAPTURED),
        "latest_policy": ((getattr(m, "portfolio", {}) or {}).get("risk_on_concentration_policy") if m is not None else {}) or {},
        "policy_summary": (
            "Tech concentration is intentionally allowed only while paper mode is risk-on/growth-led. "
            "If market mode softens, baseline participation/exposure limits are restored."
        ),
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return status(m)
    _capture_baselines(m)
    market = {}
    try:
        market = m.portfolio.get("last_market") or {}
    except Exception:
        pass
    profile = policy_profile(market, m)
    applied = _apply_policy_values(profile, m)
    patched = _patch_aggression(m)
    PATCHED_MODULE_IDS.add(id(m))
    payload = status(m)
    payload.update({
        "patched_aggression": bool(patched or getattr(m.apply_aggression_adjustments, "_risk_on_concentration_policy_patched", False)),
        "applied": applied,
    })
    return payload


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def risk_on_concentration_policy_status():
        return jsonify(apply_runtime_overrides(_mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/risk-on-concentration-policy" not in existing:
        flask_app.add_url_rule(
            "/paper/risk-on-concentration-policy",
            "risk_on_concentration_policy_status",
            risk_on_concentration_policy_status,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
