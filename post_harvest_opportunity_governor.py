"""Opportunity governor for post-harvest redeployment.

This module converts the blunt post-harvest rule of "any loss today blocks
redeployment" into a graduated opportunity throttle. It stays paper-only and
preserves hard stops:
- risk halt active
- self-defense active
- hard drawdown limit reached
- bear/risk-off market block
- normal entry-quality checks
- normal max-position checks
- missing price/data checks
- cooldown checks

It also prevents profit-taking or a slightly-below-target cash percentage from
becoming a reason to sit idle when risk is clean and high-quality candidates are
present.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "post-harvest-opportunity-governor-2026-06-16-v3-cash-gate-throttle"
REGISTERED_APP_IDS: set[int] = set()

ENABLED = os.environ.get("POST_HARVEST_OPPORTUNITY_GOVERNOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("POST_HARVEST_OPPORTUNITY_GOVERNOR_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}

NORMAL_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_NORMAL_DD_PCT", "0.50"))
CAUTIOUS_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_CAUTIOUS_DD_PCT", "1.00"))
DEFENSIVE_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_DEFENSIVE_DD_PCT", "2.00"))
HARD_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_HARD_DD_PCT", "2.75"))

NORMAL_MIN_CASH_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_NORMAL_MIN_CASH_PCT", "0.50"))
CAUTIOUS_MIN_CASH_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_CAUTIOUS_MIN_CASH_PCT", "0.55"))
DEFENSIVE_MIN_CASH_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_DEFENSIVE_MIN_CASH_PCT", "0.60"))
NEAR_LIMIT_MIN_CASH_PCT = float(os.environ.get("POST_HARVEST_OPPORTUNITY_NEAR_LIMIT_MIN_CASH_PCT", "0.65"))

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
            "min_cash_pct": NORMAL_MIN_CASH_PCT,
            "quality_requirement": "normal_post_harvest_quality",
            "reason": "losses_do_not_block_when_drawdown_is_small",
        }
    if drawdown_pct < CAUTIOUS_DRAWDOWN_PCT:
        return {
            "mode": "cautious_opportunity",
            "entry_size_factor": 0.75,
            "min_cash_pct": CAUTIOUS_MIN_CASH_PCT,
            "quality_requirement": "high_quality_only",
            "reason": "minor_drawdown_use_cautious_size",
        }
    if drawdown_pct < DEFENSIVE_DRAWDOWN_PCT:
        return {
            "mode": "defensive_opportunity",
            "entry_size_factor": 0.50,
            "min_cash_pct": DEFENSIVE_MIN_CASH_PCT,
            "quality_requirement": "exceptional_or_relative_strength_only",
            "reason": "moderate_drawdown_reduce_size_not_full_halt",
        }
    return {
        "mode": "near_limit_opportunity",
        "entry_size_factor": 0.35,
        "min_cash_pct": NEAR_LIMIT_MIN_CASH_PCT,
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
        "cash_pct_policy": "graduated_soft_gate_not_fixed_hard_block",
        "opportunity_throttle": band,
    }

    if payload["halted"]:
        return False, {**payload, "reason": "risk_halt_active"}
    if payload["self_defense_active"]:
        return False, {**payload, "reason": "self_defense_active"}
    if drawdown_pct >= HARD_DRAWDOWN_PCT:
        return False, {**payload, "reason": "hard_drawdown_limit_reached"}

    return True, {**payload, "reason": "opportunity_throttle_clean"}


def _active_min_cash_pct(controller: Any, risk_info: Dict[str, Any]) -> float:
    controller_min = _f(getattr(controller, "MIN_CASH_PCT", 0.60), 0.60)
    band = risk_info.get("opportunity_throttle") if isinstance(risk_info.get("opportunity_throttle"), dict) else {}
    band_min = _f(band.get("min_cash_pct"), controller_min)
    return max(0.0, min(controller_min, band_min))


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
    info: Dict[str, Any] = {}
    try:
        if callable(original_fn):
            ok, original_info = original_fn(m, entry_block_reason)
            info = original_info if isinstance(original_info, dict) else {}
            if ok:
                info = dict(info)
                info["opportunity_governor"] = VERSION
                return True, info
    except Exception as exc:
        info = {"reason": "original_profit_gate_error", "error": f"{type(exc).__name__}: {exc}"}

    reason_text = str(entry_block_reason or "").lower()
    risk_ok, risk_info = _opportunity_risk_ok(m, "post_harvest_profit_gate")
    cash, equity, cash_pct = _cash_equity_pct(m)
    min_cash_pct = _active_min_cash_pct(controller, risk_info)
    opportunity_reason = any(token in reason_text for token in OPPORTUNITY_BLOCK_TOKENS) or cash_pct >= min_cash_pct

    if risk_ok and cash_pct >= min_cash_pct and opportunity_reason:
        return True, {
            "reason": "opportunity_redeployment_confirmed",
            "original_profit_gate": info,
            "entry_block_reason": str(entry_block_reason or ""),
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "cash_pct": round(cash_pct, 4),
            "min_cash_pct": min_cash_pct,
            "risk_controls": risk_info,
            "policy": "profit_harvest_not_required_when_cash_is_available_and_risk_is_clean",
            "cash_pct_policy": "graduated_soft_gate_not_fixed_hard_block",
            "version": VERSION,
        }

    return False, {
        "reason": "opportunity_redeployment_not_confirmed",
        "original_profit_gate": info,
        "entry_block_reason": str(entry_block_reason or ""),
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "cash_pct": round(cash_pct, 4),
        "min_cash_pct": min_cash_pct,
        "risk_controls": risk_info,
        "cash_pct_policy": "graduated_soft_gate_not_fixed_hard_block",
        "version": VERSION,
    }


def _safe_signal_bool(controller: Any, fn_name: str, signal: Dict[str, Any]) -> bool:
    try:
        fn = getattr(controller, fn_name, None)
        return bool(fn(signal)) if callable(fn) else False
    except Exception:
        return False


def _opportunity_quality_ok(original_fn: Any, controller: Any, m: Any | None, signal: Dict[str, Any]) -> Tuple[bool, str]:
    if not callable(original_fn):
        return False, "original_post_harvest_quality_check_unavailable"
    try:
        ok, reason = original_fn(signal)
    except Exception as exc:
        return False, f"original_post_harvest_quality_check_error:{type(exc).__name__}"
    if not ok or not isinstance(signal, dict):
        return ok, reason

    risk_ok, risk_info = _opportunity_risk_ok(m or _mod(), "post_harvest_quality_throttle")
    if not risk_ok:
        return False, str(risk_info.get("reason", "risk_controls_not_clean"))

    band = risk_info.get("opportunity_throttle") if isinstance(risk_info.get("opportunity_throttle"), dict) else {}
    mode = str(band.get("mode") or "normal_opportunity")
    score = _f(signal.get("score"), 0.0)
    min_score = _f(getattr(controller, "MIN_SCORE", 0.034), 0.034)
    exceptional_score = _f(getattr(controller, "EXCEPTIONAL_SCORE", 0.045), 0.045)
    breakout = _safe_signal_bool(controller, "_is_breakout_signal", signal)
    relative_strength = _safe_signal_bool(controller, "_is_relative_strength_signal", signal)

    if mode == "normal_opportunity":
        return True, reason

    if mode == "cautious_opportunity":
        cautious_floor = max(min_score + 0.004, min(exceptional_score, 0.038))
        if score >= cautious_floor or relative_strength or (breakout and score >= min_score + 0.002):
            return True, f"{reason}|cautious_quality_throttle_pass"
        return False, "cautious_opportunity_requires_higher_quality"

    if mode == "defensive_opportunity":
        if score >= exceptional_score or relative_strength:
            return True, f"{reason}|defensive_quality_throttle_pass"
        return False, "defensive_opportunity_requires_exceptional_or_relative_strength"

    if mode == "near_limit_opportunity":
        if score >= exceptional_score and (relative_strength or breakout):
            return True, f"{reason}|near_limit_best_only_quality_throttle_pass"
        return False, "near_limit_opportunity_requires_best_only_exceptional_quality"

    return True, reason


def _opportunity_starter_signal(original_fn: Any, m: Any | None, signal: Dict[str, Any]) -> Dict[str, Any]:
    if callable(original_fn):
        starter = original_fn(signal)
    else:
        starter = dict(signal or {})
    if not isinstance(starter, dict):
        starter = dict(signal or {})

    risk_ok, risk_info = _opportunity_risk_ok(m or _mod(), "post_harvest_size_throttle")
    band = risk_info.get("opportunity_throttle") if isinstance(risk_info.get("opportunity_throttle"), dict) else {}
    size_factor = _f(band.get("entry_size_factor"), 1.0)
    existing_alloc = _f(starter.get("alloc_factor"), 1.0)
    if risk_ok and size_factor < 1.0:
        starter["alloc_factor"] = round(max(0.0, existing_alloc * size_factor), 6)
    starter["post_harvest_opportunity_governor"] = {
        "version": VERSION,
        "losses_today_policy": "throttle_not_hard_block",
        "profit_taking_policy": "frees_capital_if_quality_and_risk_are_clean",
        "cash_pct_policy": "graduated_soft_gate_not_fixed_hard_block",
        "throttle_mode": band.get("mode", "normal_opportunity"),
        "entry_size_factor": size_factor,
        "min_cash_pct": band.get("min_cash_pct"),
        "quality_requirement": band.get("quality_requirement", "normal_post_harvest_quality"),
    }
    return starter


def _opportunity_select_redeployment_candidates(original_fn: Any, controller: Any, app_module: Any | None, *args: Any, **kwargs: Any):
    if not callable(original_fn):
        return [], {"allowed": False, "reason": "original_select_redeployment_candidates_unavailable", "version": VERSION}

    runtime_module = app_module or (args[0] if args else None) or _mod()
    risk_ok, risk_info = _opportunity_risk_ok(runtime_module, "post_harvest_cash_gate")
    active_min_cash_pct = _active_min_cash_pct(controller, risk_info)
    original_min_cash_pct = _f(getattr(controller, "MIN_CASH_PCT", 0.60), 0.60)

    try:
        controller.MIN_CASH_PCT = active_min_cash_pct  # type: ignore[attr-defined]
        selected, info = original_fn(*args, **kwargs)
    finally:
        controller.MIN_CASH_PCT = original_min_cash_pct  # type: ignore[attr-defined]

    if isinstance(info, dict):
        info = dict(info)
        info["cash_pct_policy"] = "graduated_soft_gate_not_fixed_hard_block"
        info["original_min_cash_pct"] = original_min_cash_pct
        info["active_min_cash_pct"] = active_min_cash_pct
        info["cash_gate_source"] = "post_harvest_opportunity_governor"
        info["opportunity_throttle"] = risk_info.get("opportunity_throttle")
    return selected, info


def _patch_redeployment_controller(m: Any | None = None) -> Dict[str, Any]:
    try:
        import post_harvest_redeployment_controller as controller  # type: ignore
    except Exception as exc:
        return {"patched": False, "reason": "controller_import_failed", "error": f"{type(exc).__name__}: {exc}"}

    if getattr(controller, "_opportunity_governor_patched", False):
        return {
            "patched": True,
            "already_patched": True,
            "module": "post_harvest_redeployment_controller",
            "version": getattr(controller, "_opportunity_governor_version", VERSION),
        }

    original_entry_block_safe = getattr(controller, "_entry_block_safe", None)
    original_profit_harvest_ok = getattr(controller, "_profit_harvest_ok", None)
    original_quality_ok = getattr(controller, "_quality_ok", None)
    original_starter_signal = getattr(controller, "_starter_signal", None)
    original_select_redeployment_candidates = getattr(controller, "select_redeployment_candidates", None)

    def patched_risk_ok(app_module: Any | None = None):
        return _opportunity_risk_ok(app_module or m or _mod(), "post_harvest_redeployment")

    def patched_entry_block_safe(new_entries_allowed: bool, entry_block_reason: Any):
        return _opportunity_entry_block_safe(original_entry_block_safe, new_entries_allowed, entry_block_reason)

    def patched_profit_harvest_ok(app_module: Any | None, entry_block_reason: Any):
        return _opportunity_harvest_ok(original_profit_harvest_ok, controller, app_module or m or _mod(), entry_block_reason)

    def patched_quality_ok(signal: Dict[str, Any]):
        return _opportunity_quality_ok(original_quality_ok, controller, m or _mod(), signal)

    def patched_starter_signal(signal: Dict[str, Any]):
        return _opportunity_starter_signal(original_starter_signal, m or _mod(), signal)

    def patched_select_redeployment_candidates(*args: Any, **kwargs: Any):
        runtime_module = args[0] if args else m or _mod()
        return _opportunity_select_redeployment_candidates(original_select_redeployment_candidates, controller, runtime_module, *args, **kwargs)

    controller._risk_ok = patched_risk_ok  # type: ignore[attr-defined]
    controller._entry_block_safe = patched_entry_block_safe  # type: ignore[attr-defined]
    controller._profit_harvest_ok = patched_profit_harvest_ok  # type: ignore[attr-defined]
    controller._quality_ok = patched_quality_ok  # type: ignore[attr-defined]
    controller._starter_signal = patched_starter_signal  # type: ignore[attr-defined]
    controller.select_redeployment_candidates = patched_select_redeployment_candidates  # type: ignore[attr-defined]
    controller.MAX_LOSSES_TODAY = max(_i(getattr(controller, "MAX_LOSSES_TODAY", 0), 0), 99)  # type: ignore[attr-defined]
    controller._opportunity_governor_patched = True  # type: ignore[attr-defined]
    controller._opportunity_governor_version = VERSION  # type: ignore[attr-defined]

    return {
        "patched": True,
        "module": "post_harvest_redeployment_controller",
        "patched_functions": ["_risk_ok", "_entry_block_safe", "_profit_harvest_ok", "_quality_ok", "_starter_signal", "select_redeployment_candidates"],
        "losses_today_policy": "throttle_not_hard_block",
        "profit_taking_policy": "frees_capital_if_quality_and_risk_are_clean",
        "cash_pct_policy": "graduated_soft_gate_not_fixed_hard_block",
        "quality_throttle_active": True,
        "size_throttle_active": True,
        "cash_gate_throttle_active": True,
        "version": VERSION,
    }


def _patch_entry_fallback(m: Any | None = None) -> Dict[str, Any]:
    try:
        import post_harvest_entry_fallback as fallback  # type: ignore
    except Exception as exc:
        return {"patched": False, "reason": "fallback_import_failed", "error": f"{type(exc).__name__}: {exc}"}

    if getattr(fallback, "_opportunity_governor_patched", False):
        return {
            "patched": True,
            "already_patched": True,
            "module": "post_harvest_entry_fallback",
            "version": getattr(fallback, "_opportunity_governor_version", VERSION),
        }

    def patched_risk_ok(app_module: Any | None = None):
        return _opportunity_risk_ok(app_module or m or _mod(), "post_harvest_entry_fallback")

    fallback._risk_ok = patched_risk_ok  # type: ignore[attr-defined]
    fallback.MAX_LOSSES_TODAY = max(_i(getattr(fallback, "MAX_LOSSES_TODAY", 0), 0), 99)  # type: ignore[attr-defined]
    fallback._opportunity_governor_patched = True  # type: ignore[attr-defined]
    fallback._opportunity_governor_version = VERSION  # type: ignore[attr-defined]

    return {
        "patched": True,
        "module": "post_harvest_entry_fallback",
        "patched_functions": ["_risk_ok"],
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
            "cash_pct": "graduated_soft_gate_not_fixed_hard_block",
            "hard_blocks_preserved": [
                "risk_halt_active",
                "self_defense_active",
                "hard_drawdown_limit_reached",
                "bear_or_risk_off_market_block",
                "normal_entry_quality_failure",
                "max_positions_full",
                "missing_price_or_data",
                "cooldown",
            ],
            "throttle_bands": [
                {"drawdown_pct": "<0.50", "mode": "normal_opportunity", "entry_size_factor": 1.0, "min_cash_pct": NORMAL_MIN_CASH_PCT, "quality_requirement": "normal_post_harvest_quality"},
                {"drawdown_pct": "0.50-1.00", "mode": "cautious_opportunity", "entry_size_factor": 0.75, "min_cash_pct": CAUTIOUS_MIN_CASH_PCT, "quality_requirement": "high_quality_only"},
                {"drawdown_pct": "1.00-2.00", "mode": "defensive_opportunity", "entry_size_factor": 0.50, "min_cash_pct": DEFENSIVE_MIN_CASH_PCT, "quality_requirement": "exceptional_or_relative_strength_only"},
                {"drawdown_pct": "2.00-2.75", "mode": "near_limit_opportunity", "entry_size_factor": 0.35, "min_cash_pct": NEAR_LIMIT_MIN_CASH_PCT, "quality_requirement": "best_only_small_starters"},
                {"drawdown_pct": ">=2.75", "mode": "hard_block", "entry_size_factor": 0.0, "min_cash_pct": None, "quality_requirement": "blocked"},
            ],
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
