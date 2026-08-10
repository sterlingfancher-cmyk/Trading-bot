"""Keep administrative paper holds distinct from performance self-defense.

A clean-accounting validation hold blocks execution through ``risk.halted`` but
is not a loss event.  The performance-risk calibration layer historically treated
any halt as a hard performance halt, which caused a zero-loss clean epoch to be
reported as self-defense.

This guard preserves the administrative halt itself while preventing it from
being mislabeled as loss-driven self-defense.  It changes no thresholds, sizing,
entry rules, order behavior, live authority, or ML authority.
"""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "administrative-halt-classification-2026-08-10-v1"
_APPLIED_CORE_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _portfolio(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", None) if core is not None else None
    return value if isinstance(value, dict) else {}


def _is_clean_epoch_admin_hold(risk: Dict[str, Any]) -> bool:
    reason = str(risk.get("halt_reason") or "").strip().lower()
    return bool(
        risk.get("halted")
        and risk.get("clean_epoch_validation_hold")
        and reason == "clean accounting epoch validation hold"
    )


def _loss_metrics_clear(risk: Dict[str, Any]) -> bool:
    return all(
        abs(_f(risk.get(key), 0.0)) < 1e-9
        for key in (
            "daily_loss_pct",
            "daily_drawdown_pct",
            "intraday_drawdown_pct",
            "realized_loss_pct",
            "daily_loss_fraction",
            "intraday_drawdown_fraction",
            "realized_loss_fraction",
        )
    )


def _normalize(core: Any, feedback: Dict[str, Any], persist: bool) -> Dict[str, Any]:
    state = _portfolio(core)
    risk = _d(state.get("risk_controls"))
    if not (_is_clean_epoch_admin_hold(risk) and _loss_metrics_clear(risk)):
        return feedback

    controlled = _d(feedback.get("controlled_restart"))
    if controlled:
        controlled["hard_halt_active"] = False
        controlled["soft_pause_active"] = False
        controlled["realized_soft_triggered"] = False
        controlled["loss_streak_soft_triggered"] = False
        controlled["active"] = False
        controlled["administrative_hold_active"] = True
        feedback["controlled_restart"] = controlled

    feedback["self_defense_mode"] = False
    feedback["hard_halt"] = False
    # The administrative hold is already enforced by risk.halted in the canonical
    # entry gate. Do not duplicate it as a self-defense loss block.
    feedback["block_new_entries"] = False
    feedback["reasons"] = ["clean accounting epoch validation hold (administrative, zero-loss)"]
    feedback["administrative_hold_active"] = True
    feedback["administrative_hold_reason"] = "clean accounting epoch validation hold"

    if persist:
        risk["self_defense_active"] = False
        risk["self_defense_reason"] = ""
        risk["administrative_hold_active"] = True
        risk["administrative_hold_reason"] = "clean accounting epoch validation hold"
        state["risk_controls"] = risk
        state["feedback_loop"] = feedback
    return feedback


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if id(core) in _APPLIED_CORE_IDS:
        return status_payload(core)

    current = getattr(core, "feedback_loop_status", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "reason": "feedback_loop_status_missing"}
    if getattr(current, "_administrative_halt_classification_version", None) == VERSION:
        _APPLIED_CORE_IDS.add(id(core))
        return status_payload(core)

    prior = getattr(current, "_administrative_halt_classification_prior", current)

    @functools.wraps(prior)
    def wrapped(*args, **kwargs):
        result = prior(*args, **kwargs)
        feedback = result if isinstance(result, dict) else {}
        persist = bool(kwargs.get("persist", args[4] if len(args) >= 5 else True))
        return _normalize(core, feedback, persist)

    wrapped._administrative_halt_classification_version = VERSION  # type: ignore[attr-defined]
    wrapped._administrative_halt_classification_prior = prior  # type: ignore[attr-defined]
    core.feedback_loop_status = wrapped
    _APPLIED_CORE_IDS.add(id(core))

    # Normalize the persisted diagnostic immediately; the halt remains active.
    state = _portfolio(core)
    feedback = _d(state.get("feedback_loop"))
    if feedback:
        _normalize(core, feedback, True)
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _portfolio(core) if core is not None else {}
    risk = _d(state.get("risk_controls"))
    return {
        "status": "ok" if core is not None and id(core) in _APPLIED_CORE_IDS else "pending",
        "overall": "pass" if core is not None and id(core) in _APPLIED_CORE_IDS else "warn",
        "type": "administrative_halt_classification_status",
        "version": VERSION,
        "applied": bool(core is not None and id(core) in _APPLIED_CORE_IDS),
        "clean_epoch_administrative_hold": _is_clean_epoch_admin_hold(risk),
        "loss_metrics_clear": _loss_metrics_clear(risk),
        "authority": {
            "classification_only": True,
            "clears_halt": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
