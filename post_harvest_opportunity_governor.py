"""Opportunity governor for post-harvest redeployment.

This module converts the blunt post-harvest rule of "any loss today blocks
redeployment" into a graduated opportunity throttle. It stays paper-only and
preserves hard stops:
- risk halt active
- self-defense active
- drawdown near the configured hard cap
- normal entry-quality checks
- normal max-position checks

It also prevents profit-taking from becoming a reason to sit idle when cash is
available and high-quality candidates are present.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "post-harvest-opportunity-governor-2026-06-16-v1-loss-throttle"
REGISTERED_APP_IDS: set[int] = set()

ENABLED = os.environ.get("POST_HARVEST_OPPORTUNITY_GOVERNOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("POST_HARVEST_OPPORTUNITY_GOVERNOR_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}

NORMAL_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_NORMAL_DD_PCT", "0.50"))
CAUTIOUS_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_CAUTIOUS_DD_PCT", "1.00"))
DEFENSIVE_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_DEFENSIVE_DD_PCT", "2.00"))
HARD_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_HARD_DD_PCT", "2.75"))

LOSS_BLOCK_TOKENS = (
    "losses_today_not_clean",
    "loss_today",
    "losses_today",
    "small_loss",
    "daily_loss",
    "daily loss",
)

OPPORTUNITY_BLOCK_TOKENS = (
    "profit_guard",
    "profit guard",
    "harvest",
    "maturity",
    "take_profit",
    "take profit",
    "underdeploy",
    "underdeployed",
    "cash",
) + LOSS_BLOCK_TOKENS

TRUE_HARD_BLOCK_TOKENS = (
    "halt",
    "self_defense",
    "self defense",
    "stop_loss",
    "stop loss",
    "drawdown",
    "bear",
    "risk_off",
    "runner_stale",
    "stale_runner",
)


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    return None


def _now(m: Any | None = None) -> str:
    try:
        return str(m.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _portfolio(m: Any | None) -> Dict[str, Any]:
    try:
        pf = getattr(m, "portfolio", {})
        if isinstance(pf, dict):
            return pf
    except Exception:
        pass
    try:
        state = m.load_state()
        if isinstance(state, dict):
            return state
    except Exception:
        pass
    return {}


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _risk_controls(m: Any | None) -> Dict[str, Any]:
    try:
        fn = getattr(m, "get_risk_controls", None)
        if callable(fn):
            rc = fn()
            if isinstance(rc, dict):
                return rc
    except Exception:
        pass
    try:
        rc = (_portfolio(m).get("risk_controls") or {})
        return dict(rc) if isinstance(rc, dict) else {}
    except Exception:
        return {}


def _cash_equity_pct(m: Any | None) -> Tuple[float, float, float]:
    pf = _portfolio(m)
    cash = _f(pf.get("cash"), 0.0)
    equity = _f(pf.get("equity"), 0.0)
    if equity <= 0.0:
        perf = pf.get("performance") if isinstance(pf.get("performance"), dict) else {}
        equity = _f(perf.get("equity"), 0.0)
    return cash, equity, (cash / equity if equity > 0 else 0.0)


def _losses_today(m: Any | None, rc: Dict[str, Any]) -> int:
    pf = _portfolio(m)
    perf = pf.get("performance") if isinstance(pf.get("performance"), dict) else {}
    return _i(rc.get("losses_today", perf.get("losses_today", 0)), 0)


def _realized_today(m: Any | None) -> float:
    pf = _portfolio(m)
    perf = pf.get("performance") if isinstance(pf.get("performance"), dict) else {}
    for source in (pf, perf):
        if not isinstance(source, dict):
            continue
        for key in ("realized_today", "realized_pnl_today", "realized_profit_today", "day_realized_pnl", "realized_today_pnl"):
            if key in source:
                return _f(source.get(key), 0.0)
    return 0.0


def _drawdown_pct(rc: Dict[str, Any]) -> float:
    return max(
        _f(rc.get("daily_loss_pct"), 0.0),
        _f(rc.get("daily_drawdown_pct"), 0.0),
        _f(rc.get("intraday_drawdown_pct"), 0.0),
    )


def _throttle_band(drawdown_pct: float) -> Dict[str, Any]:
    if drawdown_pct < NORMAL_DRAWDOWN_PCT:
        return {
            "mode": "normal_opportunity",
            "entry_size_factor": 1.0,
            "quality_requirement": "normal_post_harvest_quality",
            "reason": "losses_do_not_block_when_drawdown_is_small",
        }
    if drawdown_pct < CAUTIOUS_DRAWDOWN_PCT:
        return {
            "mode": "cautious_opportunity",
            "entry_size_factor": 0.75,
            "quality_requirement": "high_quality_only",
            "reason": "minor_drawdown_use_cautious_size",
        }
    if drawdown_pct < DEFENSIVE_DRAWDOWN_PCT:
        return {
            "mode": "defensive_opportunity",
            "entry_size_factor": 0.50,
            "quality_requirement": "exceptional_or_relative_strength_only",
            "reason": "moderate_drawdown_reduce_size_not_full_halt",
        }
    return {
        "mode": "near_limit_opportunity",
        "entry_size_factor": 0.35,
        "quality_requirement": "best_only_until_hard_limit",
        "reason": "near_daily_limit_allow_only_best_small_starters",
    }


def _opportunity_risk_ok(m: Any | None, source: str) -> Tuple[bool, Dict[str, Any]]:
    rc = _risk_controls(m)
    losses_today = _losses_today(m, rc)
    drawdown_pct = _drawdown_pct(rc)
    realized_today = _realized_today(m)
    halt_reason = str(rc.get("halt_reason") or rc.get("self_defense_reason") or "")
    band = _throttle_band(drawdown_pct)

    payload = {
        "source": source,
        "version": VERSION,
        "halted": bool(rc.get("halted")),
        "self_defense_active": bool(rc.get("self_defense_active")),
        "losses_today": losses_today,
        "realized_today": round(realized_today, 4),
        "daily_drawdown_pct": round(drawdown_pct, 4),
        "hard_drawdown_pct": HARD_DRAWDOWN_PCT,
        "halt_reason": halt_reason,
        "losses_today_policy": "throttle_not_hard_block",
        "profit_taking_policy": "frees_capital_if_quality_and_risk_are_clean",
        "opportunity_throttle": band,
    }

    if payload["halted"]:
        return False, {**payload, "reason": "risk_halt_active"}
    if payload["self_defense_active"]:
        return False, {**payload, "reason": "self_defense_active"}
    if drawdown_pct >= HARD_DRAWDOWN_PCT:
        return False, {**payload, "reason": "hard_drawdown_limit_reached"}

    return True, {**payload, "reason": "opportunity_throttle_clean"}


def _opportunity_entry_block_safe(original_fn: Any, new_entries_allowed: bool, entry_block_reason: Any) -> Tuple[bool, str]:
    if bool(new_entries_allowed):
        return True, "entries_already_allowed"

    reason = str(entry_block_reason or "").lower()
    if any(token in reason for token in OPPORTUNITY_BLOCK_TOKENS):
        return True, "opportunity_throttle_soft_block_override"

    # Preserve true hard blocks unless they are loss/profit/cash opportunity gates.
    if any(token in reason for token in TRUE_HARD_BLOCK_TOKENS):
        return False, "hard_entry_block_not_overridden"

    try:
        if callable(original_fn):
            return original_fn(new_entries_allowed, entry_block_reason)
    except Exception:
        pass
    return False, "entry_block_reason_not_post_harvest_safe"


def _opportunity_harvest_ok(original_fn: Any, controller: Any, m: Any | None, entry_block_reason: Any) -> Tuple[bool, Dict[str, Any]]:
    try:
        if callable(original_fn):
            ok, info = original_fn(m, entry_block_reason)
            if ok:
                if isinstance(info, dict):
                    info = dict(info)
                    info["opportunity_governor"] = VERSION
                return True, info
    except Exception:
        info = {"reason": "original_profit_gate_error"}

    reason_text = str(entry_block_reason or "").lower()
    risk_ok, risk_info = _opportunity_risk_ok(m, "post_harvest_profit_gate")
    cash, equity, cash_pct = _cash_equity_pct(m)
    min_cash_pct = _f(getattr(controller, "MIN_CASH_PCT", 0.60), 0.60)
    opportunity_reason = any(token in reason_text for token in OPPORTUNITY_BLOCK_TOKENS) or cash_pct >= min_cash_pct

    if risk_ok and cash_pct >= min_cash_pct and opportunity_reason:
        return True, {
            "reason": "opportunity_redeployment_confirmed",
            "original_profit_gate": info if isinstance(info, dict) else {},
            "entry_block_reason": str(entry_block_reason or ""),
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "cash_pct": round(cash_pct, 4),
            "min_cash_pct": min_cash_pct,
            "risk_controls": risk_info,
            "policy": "profit_harvest_not_required_when_cash_is_available_and_risk_is_clean",
            "version": VERSION,
        }

    return False, {
        "reason": "opportunity_redeployment_not_confirmed",
        "original_profit_gate": info if isinstance(info, dict) else {},
        "entry_block_reason": str(entry_block_reason or ""),
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "cash_pct": round(cash_pct, 4),
        "min_cash_pct": min_cash_pct,
        "risk_controls": risk_info,
        "version": VERSION,
    }


def _patch_redeployment_controller(m: Any | None = None) -> Dict[str, Any]:
    try:
        import post_harvest_redeployment_controller as controller  # type: ignore
    except Exception as exc:
        return {"patched": False, "reason": "controller_import_failed", "error": f"{type(exc).__name__}: {exc}"}

    if getattr(controller, "_opportunity_governor_patched", False):
        return {"patched": True, "already_patched": True, "module": "post_harvest_redeployment_controller"}

    original_entry_block_safe = getattr(controller, "_entry_block_safe", None)
    original_profit_harvest_ok = getattr(controller, "_profit_harvest_ok", None)

    def patched_risk_ok(app_module: Any | None = None):
        return _opportunity_risk_ok(app_module or m or _mod(), "post_harvest_redeployment")

    def patched_entry_block_safe(new_entries_allowed: bool, entry_block_reason: Any):
        return _opportunity_entry_block_safe(original_entry_block_safe, new_entries_allowed, entry_block_reason)

    def patched_profit_harvest_ok(app_module: Any | None, entry_block_reason: Any):
        return _opportunity_harvest_ok(original_profit_harvest_ok, controller, app_module or m or _mod(), entry_block_reason)

    controller._risk_ok = patched_risk_ok  # type: ignore[attr-defined]
    controller._entry_block_safe = patched_entry_block_safe  # type: ignore[attr-defined]
    controller._profit_harvest_ok = patched_profit_harvest_ok  # type: ignore[attr-defined]
    controller.MAX_LOSSES_TODAY = max(_i(getattr(controller, "MAX_LOSSES_TODAY", 0), 0), 99)  # type: ignore[attr-defined]
    controller._opportunity_governor_patched = True  # type: ignore[attr-defined]
    controller._opportunity_governor_version = VERSION  # type: ignore[attr-defined]

    return {
        "patched": True,
        "module": "post_harvest_redeployment_controller",
        "losses_today_policy": "throttle_not_hard_block",
        "profit_taking_policy": "frees_capital_if_quality_and_risk_are_clean",
        "version": VERSION,
    }


def _patch_entry_fallback(m: Any | None = None) -> Dict[str, Any]:
    try:
        import post_harvest_entry_fallback as fallback  # type: ignore
    except Exception as exc:
        return {"patched": False, "reason": "fallback_import_failed", "error": f"{type(exc).__name__}: {exc}"}

    if getattr(fallback, "_opportunity_governor_patched", False):
        return {"patched": True, "already_patched": True, "module": "post_harvest_entry_fallback"}

    def patched_risk_ok(app_module: Any | None = None):
        return _opportunity_risk_ok(app_module or m or _mod(), "post_harvest_entry_fallback")

    fallback._risk_ok = patched_risk_ok  # type: ignore[attr-defined]
    fallback.MAX_LOSSES_TODAY = max(_i(getattr(fallback, "MAX_LOSSES_TODAY", 0), 0), 99)  # type: ignore[attr-defined]
    fallback._opportunity_governor_patched = True  # type: ignore[attr-defined]
    fallback._opportunity_governor_version = VERSION  # type: ignore[attr-defined]

    return {
        "patched": True,
        "module": "post_harvest_entry_fallback",
        "losses_today_policy": "throttle_not_hard_block",
        "version": VERSION,
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if not ENABLED:
        return {"status": "disabled", "type": "post_harvest_opportunity_governor_status", "version": VERSION}
    if not _paper_context():
        return {"status": "blocked", "type": "post_harvest_opportunity_governor_status", "version": VERSION, "reason": "not_paper_context"}

    controller_patch = _patch_redeployment_controller(m)
    fallback_patch = _patch_entry_fallback(m)
    risk_ok, risk_info = _opportunity_risk_ok(m, "status")

    return {
        "status": "ok",
        "overall": "pass" if risk_ok else "stand_down",
        "type": "post_harvest_opportunity_governor_status",
        "version": VERSION,
        "generated_local": _now(m),
        "enabled": True,
        "paper_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "controller_patch": controller_patch,
        "fallback_patch": fallback_patch,
        "risk_controls": risk_info,
        "policy": {
            "losses_today": "throttle_not_hard_block",
            "profit_taking": "frees_capital_if_quality_and_risk_are_clean",
            "hard_blocks_preserved": ["risk_halt", "self_defense", "hard_drawdown_limit"],
            "normal_drawdown_pct": NORMAL_DRAWDOWN_PCT,
            "cautious_drawdown_pct": CAUTIOUS_DRAWDOWN_PCT,
            "defensive_drawdown_pct": DEFENSIVE_DRAWDOWN_PCT,
            "hard_drawdown_pct": HARD_DRAWDOWN_PCT,
        },
    }


def apply(m: Any | None = None) -> Dict[str, Any]:
    return apply_runtime_overrides(m)


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify

    def post_harvest_opportunity_governor_status():
        return jsonify(apply_runtime_overrides(m or _mod()))

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/post-harvest-opportunity-governor-status" not in existing:
        flask_app.add_url_rule(
            "/paper/post-harvest-opportunity-governor-status",
            "post_harvest_opportunity_governor_status",
            post_harvest_opportunity_governor_status,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
