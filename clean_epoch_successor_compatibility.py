"""Compatibility guard for legitimately superseded clean accounting epochs.

The 2026-08-10 clean epoch migration leaves a durable completion marker. Later,
explicit verified-snapshot roll-forwards are allowed to supersede that epoch.
This shim teaches the old migration to treat only the exact v1->v2 and
v1->v2->v3 successor relationships as healthy instead of reporting a missing
active epoch.

It does not mutate account state, risk limits, strategy, sizing, live authority,
or ML authority. Any unrelated epoch mismatch continues to fail closed.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "clean-epoch-successor-compatibility-2026-08-25-v2-v3-chain"
OLD_EPOCH_ID = "stable-paper-v1-20260810-clean01"
VERIFIED_V2_EPOCH_ID = "stable-paper-v2-20260812-verified01"
NEW_EPOCH_ID = VERIFIED_V2_EPOCH_ID
ISSUE82_V3_EPOCH_ID = "stable-paper-v3-20260825-successor01"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _successor_epoch(core: Any) -> str | None:
    pf = getattr(core, "portfolio", None)
    pf = pf if isinstance(pf, dict) else {}
    epoch = _d(pf.get("paper_accounting_epoch"))
    epoch_id = str(epoch.get("id") or "")
    if bool(
        epoch_id == VERIFIED_V2_EPOCH_ID
        and str(epoch.get("prior_epoch_id") or "") == OLD_EPOCH_ID
        and str(epoch.get("historical_recovery_decision") or "") == "verified_snapshot_rollforward"
        and bool(epoch.get("historical_evidence_archived", False))
    ):
        return VERIFIED_V2_EPOCH_ID
    if bool(
        epoch_id == ISSUE82_V3_EPOCH_ID
        and str(epoch.get("prior_epoch_id") or "") == VERIFIED_V2_EPOCH_ID
        and str(epoch.get("historical_recovery_decision") or "") == "verified_v2_historical_disposition_successor_rollforward"
        and bool(epoch.get("historical_evidence_archived", False))
        and bool(epoch.get("validation_hold", False))
    ):
        return ISSUE82_V3_EPOCH_ID
    return None


def _is_verified_successor(core: Any) -> bool:
    return _successor_epoch(core) is not None


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import clean_accounting_epoch as clean
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}
    current = getattr(clean, "apply", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "clean_epoch_apply_missing"}
    if getattr(current, "_successor_compatibility_version", None) == VERSION:
        _APPLIED = True
        return status_payload(core)
    prior = getattr(current, "_successor_compatibility_prior", current)

    def wrapped(runtime_core: Any = None):
        successor = _successor_epoch(runtime_core) if runtime_core is not None else None
        if successor:
            pf = getattr(runtime_core, "portfolio", None)
            epoch = _d(_d(pf).get("paper_accounting_epoch"))
            return {
                "status": "superseded",
                "overall": "pass",
                "version": getattr(clean, "VERSION", None),
                "compatibility_version": VERSION,
                "epoch_id": OLD_EPOCH_ID,
                "superseded_by_epoch_id": successor,
                "historical_recovery_decision": epoch.get("historical_recovery_decision"),
                "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)),
            }
        return prior(runtime_core)

    wrapped._successor_compatibility_version = VERSION
    wrapped._successor_compatibility_prior = prior
    clean.apply = wrapped
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    successor = _successor_epoch(core) if core is not None else None
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "verified_successor_present": bool(successor),
        "successor_epoch_id": successor,
        "reporting_compatibility_only": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
