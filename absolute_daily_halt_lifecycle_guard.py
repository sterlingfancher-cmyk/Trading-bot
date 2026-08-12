"""Allow a recovered absolute-daily-loss halt to follow the normal risk lifecycle.

The 3% absolute daily equity-loss ceiling remains unchanged and authoritative.
`performance_risk_calibration` already reasserts that halt whenever the current
metric is at or above the ceiling, and clears managed performance halts only after
the triggering metric has recovered below its threshold.

The absolute-daily-loss reason was accidentally omitted from the helper that
classifies managed performance halts. That made this one reason permanently
sticky even after the current daily-loss metric recovered. This compatibility
guard adds only that exact reason to the existing managed-halt classifier.

It does not clear state directly, change thresholds, bypass self-defense, alter
accounting, place orders, or change live/ML authority.
"""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "absolute-daily-halt-lifecycle-2026-08-12-v1"
_APPLIED = False


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import performance_risk_calibration as calibration
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(calibration, "_managed_halt", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "managed_halt_classifier_missing"}
    if getattr(current, "_absolute_daily_halt_lifecycle_version", None) == VERSION:
        _APPLIED = True
        return status_payload()

    prior = getattr(current, "_absolute_daily_halt_lifecycle_prior", current)

    @functools.wraps(prior)
    def managed_halt(reason: Any) -> bool:
        text = str(reason or "").strip().lower()
        return bool(prior(reason) or text.startswith("absolute daily equity loss halt"))

    managed_halt._absolute_daily_halt_lifecycle_version = VERSION  # type: ignore[attr-defined]
    managed_halt._absolute_daily_halt_lifecycle_prior = prior  # type: ignore[attr-defined]
    calibration._managed_halt = managed_halt
    _APPLIED = True
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "absolute_daily_halt_lifecycle_guard_status",
        "version": VERSION,
        "absolute_daily_loss_threshold_changed": False,
        "direct_state_clear": False,
        "authority": {
            "risk_correctness_only": True,
            "changes_risk_thresholds": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
