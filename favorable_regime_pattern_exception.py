"""Controlled paper-only exception for a contradictory chase-pattern veto.

The entry pipeline can identify a high-ranking constructive-market leader with a
clean retest/continuation structure, then the older loss-streak governor can veto
it solely because one diagnostic also labels the move as overextended. This patch
allows that narrow case only when the account has no realized loss streak, risk
controls are clean, cash remains high, and the signal score is exceptional.

It does not bypass cooldowns, starter spacing, daily entry caps, position caps,
sector/bucket limits, stop-loss sizing, account halts, self-defense, or live-trade
authority. It never places an order directly.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Tuple

VERSION = "favorable-regime-pattern-exception-2026-08-04-v1-controlled-retest"
ENABLED = os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_SCORE = float(os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MIN_SCORE", "0.0550"))
MIN_CASH_PCT = float(os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MIN_CASH_PCT", "80.0"))
MAX_OPEN_POSITIONS = int(os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MAX_OPEN_POSITIONS", "1"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MAX_DAILY_LOSS_PCT", "0.10"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MAX_INTRADAY_DRAWDOWN_PCT", "0.10"))
ALLOWED_MODES = {x.strip().lower() for x in os.environ.get("FAVORABLE_REGIME_PATTERN_EXCEPTION_MODES", "constructive,risk_on").split(",") if x.strip()}
QUALIFYING_PATTERNS = {
    "breakout_retest_hold",
    "relative_strength_pullback",
    "failed_breakdown_reclaim",
    "higher_low_continuation",
}
ALLOWED_RISK_PATTERNS = {"overextension_chase_risk"}

_PATCHED = False
_ORIGINAL = None
_LAST: Dict[str, Any] = {}
_REGISTERED_APP_IDS: set[int] = set()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set)):
        return {str(x).strip() for x in value if str(x).strip()}
    return set()


def _portfolio(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _paper_only(core: Any) -> bool:
    if bool(getattr(core, "LIVE_TRADING_ENABLED", False)):
        return False
    mode = str(os.environ.get("TRADING_MODE") or os.environ.get("EXECUTION_MODE") or "paper").lower()
    return mode not in {"live", "production", "real"}


def _market_mode(core: Any) -> str:
    market = _portfolio(core).get("last_market") or {}
    if not isinstance(market, dict):
        market = {}
    return str(market.get("market_mode") or market.get("regime") or "").lower()


def _cash_pct(core: Any) -> float:
    portfolio = _portfolio(core)
    cash = _safe_float(portfolio.get("cash"), 0.0)
    equity = _safe_float(portfolio.get("equity"), 0.0) or cash
    return (cash / equity * 100.0) if equity > 0 else 0.0


def _risk_state(core: Any) -> Dict[str, Any]:
    try:
        value = core.get_risk_controls() if callable(getattr(core, "get_risk_controls", None)) else _portfolio(core).get("risk_controls")
    except Exception:
        value = _portfolio(core).get("risk_controls")
    return value if isinstance(value, dict) else {}


def _qualifies(core: Any, signal: Dict[str, Any], decision: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    loss = decision.get("loss_state") if isinstance(decision.get("loss_state"), dict) else {}
    pattern = decision.get("pattern_veto") if isinstance(decision.get("pattern_veto"), dict) else {}
    reasons = set(str(x) for x in decision.get("reasons") or [])
    detected = _as_set(pattern.get("patterns_detected"))
    risk_patterns = _as_set(pattern.get("risk_patterns"))
    score = _safe_float(signal.get("score"), _safe_float(decision.get("score"), 0.0))
    side = str(signal.get("side") or "long").lower()
    mode = _market_mode(core)
    cash_pct = _cash_pct(core)
    positions = _portfolio(core).get("positions") or {}
    open_positions = len(positions) if isinstance(positions, dict) else 0
    risk = _risk_state(core)
    daily_loss = _safe_float(risk.get("daily_loss_pct"), 0.0)
    drawdown = _safe_float(risk.get("intraday_drawdown_pct"), 0.0)
    matched_patterns = sorted(detected.intersection(QUALIFYING_PATTERNS))

    checks = {
        "enabled": bool(ENABLED),
        "paper_only": _paper_only(core),
        "long_only": side == "long",
        "sole_base_rejection_is_pattern_chase": reasons == {"pattern_chase_risk_veto"},
        "loss_state_clear": str(loss.get("level") or "") == "clear" and int(_safe_float(loss.get("losses_today"), 0)) == 0 and int(_safe_float(loss.get("stop_losses_today"), 0)) == 0,
        "allowed_market_mode": mode in ALLOWED_MODES,
        "score_exceptional": score >= MIN_SCORE,
        "clean_retest_structure": len(matched_patterns) >= 2,
        "only_allowed_risk_pattern": bool(risk_patterns) and risk_patterns.issubset(ALLOWED_RISK_PATTERNS),
        "cash_high": cash_pct >= MIN_CASH_PCT,
        "open_positions_controlled": open_positions <= MAX_OPEN_POSITIONS,
        "risk_not_halted": not bool(risk.get("halted", False)),
        "self_defense_inactive": not bool(risk.get("self_defense_active", False)),
        "daily_loss_within_starter_tolerance": daily_loss <= MAX_DAILY_LOSS_PCT,
        "drawdown_within_starter_tolerance": drawdown <= MAX_INTRADAY_DRAWDOWN_PCT,
    }
    detail = {
        "version": VERSION,
        "symbol": str(signal.get("symbol") or signal.get("ticker") or "").upper(),
        "score": round(score, 6),
        "minimum_score": MIN_SCORE,
        "market_mode": mode,
        "cash_pct": round(cash_pct, 4),
        "open_positions": open_positions,
        "matched_patterns": matched_patterns,
        "risk_patterns": sorted(risk_patterns),
        "daily_loss_pct": daily_loss,
        "intraday_drawdown_pct": drawdown,
        "checks": checks,
    }
    return all(checks.values()), detail


def _patched_govern_signal(core: Any, signal: Dict[str, Any]):
    global _LAST
    original = _ORIGINAL
    if not callable(original):
        return False, {"version": VERSION, "ok": False, "reasons": ["base_governor_missing"]}
    ok, decision = original(core, signal)
    if ok or not isinstance(decision, dict):
        _LAST = {"status": "passthrough", "allowed": bool(ok), "base_decision": decision}
        return ok, decision

    allow, detail = _qualifies(core, signal if isinstance(signal, dict) else {}, decision)
    if not allow:
        _LAST = {"status": "blocked", "allowed": False, "detail": detail, "base_decision": decision}
        return ok, decision

    amended = dict(decision)
    amended.update({
        "ok": True,
        "reasons": ["favorable_regime_clean_retest_exception"],
        "favorable_regime_pattern_exception": detail,
        "base_governor_decision": decision,
    })
    _LAST = {"status": "allowed", "allowed": True, "detail": detail, "base_decision": decision}
    return True, amended


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED, _ORIGINAL
    try:
        import loss_streak_defensive_governor as governor
        current = getattr(governor, "_govern_signal", None)
        if getattr(current, "_favorable_regime_pattern_exception_version", None) != VERSION:
            _ORIGINAL = current
            _patched_govern_signal._favorable_regime_pattern_exception_version = VERSION  # type: ignore[attr-defined]
            _patched_govern_signal._favorable_regime_pattern_exception_original = current  # type: ignore[attr-defined]
            governor._govern_signal = _patched_govern_signal
        _PATCHED = True
    except Exception as exc:
        return {"status": "error", "overall": "warn", "version": VERSION, "patched": False, "error": f"{type(exc).__name__}: {exc}"}
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _PATCHED else "pending",
        "overall": "pass" if _PATCHED else "warn",
        "type": "favorable_regime_pattern_exception_status",
        "version": VERSION,
        "generated_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": bool(ENABLED),
        "patched": bool(_PATCHED),
        "latest": dict(_LAST),
        "policy": {
            "paper_only": True,
            "minimum_score": MIN_SCORE,
            "minimum_cash_pct": MIN_CASH_PCT,
            "maximum_open_positions": MAX_OPEN_POSITIONS,
            "allowed_market_modes": sorted(ALLOWED_MODES),
            "requires_zero_realized_losses_today": True,
            "requires_zero_stop_losses_today": True,
            "requires_two_clean_retest_patterns": True,
            "allowed_risk_patterns": sorted(ALLOWED_RISK_PATTERNS),
            "does_not_bypass_spacing": True,
            "does_not_bypass_daily_entry_caps": True,
            "does_not_bypass_position_caps": True,
            "does_not_bypass_sector_or_bucket_caps": True,
            "does_not_bypass_account_halts": True,
            "does_not_bypass_self_defense": True,
            "does_not_change_sizing": True,
            "does_not_change_live_authority": True,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/favorable-regime-pattern-exception-status" not in existing:
        flask_app.add_url_rule(
            "/paper/favorable-regime-pattern-exception-status",
            "favorable_regime_pattern_exception_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
