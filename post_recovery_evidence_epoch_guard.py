"""Block MAE/MFE promotion until new clean lifecycle evidence exists.

Supports both the historical accounting-recovery epoch and the deliberate clean
accounting epoch.  Old contaminated/recovery-era rows can never satisfy a clean
epoch promotion gate.
"""
from __future__ import annotations

import functools
from typing import Any, Dict

VERSION = "post-recovery-evidence-epoch-guard-2026-08-10-v2-clean-epoch"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _state(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _epoch_gate(state: Dict[str, Any]) -> Dict[str, Any]:
    clean = _d(state.get("paper_accounting_epoch"))
    if bool(clean.get("clean_start")):
        return {
            "source": "clean_accounting_epoch",
            "epoch_id": clean.get("id"),
            "baseline": int(clean.get("valid_path_rows_baseline") or 0),
            "required": bool(clean.get("forward_validation_required", True)),
            "reason": "clean_accounting_epoch_forward_validation_required",
        }
    recovery = _d(state.get("paper_accounting_semantics_recovery"))
    return {
        "source": "historical_accounting_recovery",
        "epoch_id": None,
        "baseline": int(recovery.get("recovery_epoch_valid_path_rows_baseline") or 0),
        "required": bool(recovery.get("post_recovery_validation_required", False)),
        "reason": "post_accounting_recovery_forward_validation_required",
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_data_integrity_audit_overlay as audit
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(audit, "build_integrity_section", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "integrity_builder_missing"}
    if getattr(current, "_post_recovery_evidence_epoch_guard", None) == VERSION:
        _APPLIED = True
        return status_payload(core)

    prior = getattr(current, "_post_recovery_evidence_epoch_guard_prior", current)

    @functools.wraps(prior)
    def wrapped(runtime: Any = None):
        active = runtime or core
        section = prior(active)
        if not isinstance(section, dict):
            return section

        state = _state(active)
        gate = _epoch_gate(state)
        baseline = int(gate.get("baseline") or 0)
        forward = _d(section.get("forward_validation"))
        current_valid = int(forward.get("valid_exact_lifecycle_rows_observed") or 0)
        post_epoch_valid = max(0, current_valid - baseline)
        required = bool(gate.get("required", False))
        eligible = (not required) or post_epoch_valid >= 1

        epoch = {
            "version": VERSION,
            "source": gate.get("source"),
            "epoch_id": gate.get("epoch_id"),
            "baseline_valid_exact_lifecycle_rows": baseline,
            "current_valid_exact_lifecycle_rows": current_valid,
            "post_recovery_valid_exact_lifecycle_rows": post_epoch_valid,
            "post_epoch_valid_exact_lifecycle_rows": post_epoch_valid,
            "minimum_post_recovery_rows_required": 1,
            "promotion_evidence_eligible": eligible,
        }
        section["post_recovery_evidence_epoch"] = epoch

        if required and not eligible:
            reason = str(gate.get("reason") or "post_accounting_recovery_forward_validation_required")
            reasons = list(section.get("reasons") or [])
            if reason not in reasons:
                reasons.insert(0, reason)
            section["reasons"] = reasons
            section["status"] = "fail"

            forward["promotion_evidence_eligible"] = False
            forward["promotion_block_reason"] = reason
            forward["post_recovery_valid_exact_lifecycle_rows"] = post_epoch_valid
            forward["post_epoch_valid_exact_lifecycle_rows"] = post_epoch_valid
            section["forward_validation"] = forward

            mae = _d(section.get("mae_mfe_integrity"))
            mae["promotion_evidence_eligible"] = False
            mae["promotion_block_reason"] = reason
            mae["post_recovery_training_eligible_rows"] = post_epoch_valid
            mae["post_epoch_training_eligible_rows"] = post_epoch_valid
            section["mae_mfe_integrity"] = mae
        elif required and eligible:
            forward["promotion_evidence_eligible"] = True
            forward["post_recovery_valid_exact_lifecycle_rows"] = post_epoch_valid
            forward["post_epoch_valid_exact_lifecycle_rows"] = post_epoch_valid
            section["forward_validation"] = forward

        return section

    wrapped._post_recovery_evidence_epoch_guard = VERSION  # type: ignore[attr-defined]
    wrapped._post_recovery_evidence_epoch_guard_prior = prior  # type: ignore[attr-defined]
    audit.build_integrity_section = wrapped
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _state(core) if core is not None else {}
    gate = _epoch_gate(state)
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "post_recovery_evidence_epoch_guard_status",
        "version": VERSION,
        "applied": _APPLIED,
        "epoch_source": gate.get("source"),
        "epoch_id": gate.get("epoch_id"),
        "recovery_epoch_valid_path_rows_baseline": int(gate.get("baseline") or 0),
        "post_recovery_validation_required": bool(gate.get("required", False)),
        "promotion_block_reason": gate.get("reason") if gate.get("required") else None,
        "authority": {
            "reporting_and_promotion_gate_only": True,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
