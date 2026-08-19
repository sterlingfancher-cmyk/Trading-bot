"""Fail closed until a fresh risk day has a sane current equity baseline.

Issue #82 requires the normal next-day reset to initialize ``day_start_equity``
and ``day_peak_equity`` from a sane protected valuation.  The legacy
``get_risk_controls`` reset used the first persisted ``portfolio['equity']`` it
saw on a new date without validating it.  A contaminated/non-positive persisted
value could therefore become the new day's baseline before valuation recovery,
and the later ``0.01`` arithmetic floor could manufacture an enormous loss
percentage and latch a false hard halt.

This guard is intentionally prospective and fail-closed:

* a new-day reset is deferred while the candidate equity is non-finite or <= $1;
* risk metrics are not recomputed from that invalid candidate while deferred;
* once a sane current equity reaches the normal update boundary, the ordinary
  daily reset is allowed to initialize from that value;
* an already-initialized current day is never rewritten, so this module does not
  clear today's halt or rewrite today's peak after the fact.

No strategy, sizing, risk thresholds, accounting history, live authority, ML
authority, or order-placement behavior is changed.
"""
from __future__ import annotations

import functools
import math
from typing import Any, Dict

VERSION = "fresh-risk-day-baseline-guard-2026-08-19-v1"
MIN_SANE_EQUITY = 1.0
_APPLIED_CORE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _today(core: Any) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return ""


def _sane_equity(value: Any) -> bool:
    return _f(value, 0.0) > MIN_SANE_EQUITY


def _mark_pending(rc: Dict[str, Any], candidate: Any, source: str) -> None:
    rc["fresh_day_reset_pending"] = True
    rc["fresh_day_reset_pending_reason"] = "sane_current_equity_required"
    rc["fresh_day_reset_candidate_equity"] = _f(candidate, 0.0)
    rc["fresh_day_reset_candidate_source"] = source
    rc["fresh_day_reset_guard_version"] = VERSION


def _clear_pending(rc: Dict[str, Any], source: str) -> None:
    rc.pop("fresh_day_reset_pending", None)
    rc.pop("fresh_day_reset_pending_reason", None)
    rc.pop("fresh_day_reset_candidate_equity", None)
    rc.pop("fresh_day_reset_candidate_source", None)
    rc["fresh_day_reset_guard_version"] = VERSION
    rc["fresh_day_reset_source"] = source


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    get_current = getattr(core, "get_risk_controls", None)
    update_current = getattr(core, "update_daily_risk_controls", None)
    default_factory = getattr(core, "default_risk_controls", None)
    if not callable(get_current) or not callable(update_current) or not callable(default_factory):
        return {
            "status": "error",
            "overall": "fail",
            "version": VERSION,
            "error": "required_risk_control_boundaries_missing",
        }

    if getattr(get_current, "_fresh_risk_day_baseline_version", None) == VERSION:
        _APPLIED_CORE_IDS.add(id(core))
        return status_payload(core)

    prior_get = getattr(get_current, "_fresh_risk_day_baseline_prior", get_current)
    prior_update = getattr(update_current, "_fresh_risk_day_baseline_prior", update_current)

    @functools.wraps(prior_get)
    def guarded_get_risk_controls():
        portfolio = _d(getattr(core, "portfolio", {}))
        rc = portfolio.setdefault("risk_controls", default_factory())
        if not isinstance(rc, dict):
            rc = default_factory()
            portfolio["risk_controls"] = rc

        today = _today(core)
        if today and str(rc.get("date") or "") != today:
            candidate = portfolio.get("equity")
            if not _sane_equity(candidate):
                _mark_pending(rc, candidate, "portfolio.equity")
                return rc

        out = prior_get()
        if isinstance(out, dict) and today and str(out.get("date") or "") == today:
            if _sane_equity(out.get("day_start_equity")) and _sane_equity(out.get("day_peak_equity")):
                _clear_pending(out, "normal_get_risk_controls_reset")
        return out

    @functools.wraps(prior_update)
    def guarded_update_daily_risk_controls(equity):
        portfolio = _d(getattr(core, "portfolio", {}))
        rc = portfolio.setdefault("risk_controls", default_factory())
        if not isinstance(rc, dict):
            rc = default_factory()
            portfolio["risk_controls"] = rc

        today = _today(core)
        if today and str(rc.get("date") or "") != today:
            if not _sane_equity(equity):
                _mark_pending(rc, equity, "update_daily_risk_controls.argument")
                return rc

            # This is the normal new-day reset, performed only when the valuation
            # boundary itself supplies a sane current equity.  It is not a repair
            # of an already-initialized current day.
            fresh = default_factory()
            fresh["date"] = today
            fresh["day_start_equity"] = float(equity)
            fresh["day_peak_equity"] = float(equity)
            _clear_pending(fresh, "update_daily_risk_controls.argument")
            portfolio["risk_controls"] = fresh

        return prior_update(equity)

    guarded_get_risk_controls._fresh_risk_day_baseline_version = VERSION  # type: ignore[attr-defined]
    guarded_get_risk_controls._fresh_risk_day_baseline_prior = prior_get  # type: ignore[attr-defined]
    guarded_update_daily_risk_controls._fresh_risk_day_baseline_version = VERSION  # type: ignore[attr-defined]
    guarded_update_daily_risk_controls._fresh_risk_day_baseline_prior = prior_update  # type: ignore[attr-defined]

    core.get_risk_controls = guarded_get_risk_controls
    core.update_daily_risk_controls = guarded_update_daily_risk_controls
    _APPLIED_CORE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    installed = bool(
        core is not None
        and getattr(getattr(core, "get_risk_controls", None), "_fresh_risk_day_baseline_version", None) == VERSION
        and getattr(getattr(core, "update_daily_risk_controls", None), "_fresh_risk_day_baseline_version", None) == VERSION
    )
    portfolio = _d(getattr(core, "portfolio", {})) if core is not None else {}
    rc = _d(portfolio.get("risk_controls"))
    return {
        "status": "ok" if installed else "pending",
        "overall": "pass" if installed else "warn",
        "type": "fresh_risk_day_baseline_guard_status",
        "version": VERSION,
        "installed": installed,
        "prospective_only": True,
        "current_day_rewrite": False,
        "minimum_sane_equity": MIN_SANE_EQUITY,
        "current_equity_sane": _sane_equity(portfolio.get("equity")),
        "day_start_equity_sane": _sane_equity(rc.get("day_start_equity")),
        "day_peak_equity_sane": _sane_equity(rc.get("day_peak_equity")),
        "fresh_day_reset_pending": bool(rc.get("fresh_day_reset_pending", False)),
        "authority": {
            "risk_correctness_only": True,
            "changes_risk_thresholds": False,
            "changes_strategy": False,
            "changes_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
            "edits_historical_accounting": False,
            "clears_current_day_halt": False,
            "rewrites_current_day_peak": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify

        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/fresh-risk-day-baseline-guard-status"
        if path not in existing:
            flask_app.add_url_rule(
                path,
                "fresh_risk_day_baseline_guard_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
