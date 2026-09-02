"""Governed release of the Issue #126 v4 successor validation hold.

The v4 successor was deliberately created with a validation hold after exact-
evidence accounting recovery.  This module releases only that epoch metadata
hold after the existing forward-validation and integrity surfaces independently
prove the configured criteria.  It never clears a risk halt, edits canonical
history, or changes strategy, sizing, risk limits, live authority, ML authority,
or order authority.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict

VERSION = "verified-v4-validation-release-2026-09-02-v1"
TARGET_EPOCH_ID = "stable-paper-v4-20260826-successor01"
MINIMUM_POST_EPOCH_VALID_ROWS = 1
_LAST: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _i(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(value))
    except Exception:
        return 0


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _evidence(core: Any) -> Dict[str, Any]:
    try:
        import canonical_execution_ledger as ledger_module
        ledger = ledger_module.status_payload(core)
    except Exception as exc:
        ledger = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        import paper_bidirectional_accounting_guard as accounting_module
        accounting = accounting_module.status_payload(core)
        rebuilt = accounting_module.analyze_ledger(_portfolio(core), core)
        accounting = {**accounting, "reconstructed": rebuilt}
    except Exception as exc:
        accounting = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        import daily_data_integrity_audit_overlay as audit_module
        integrity = audit_module.build_integrity_section(core)
    except Exception as exc:
        integrity = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"ledger": ledger, "accounting": accounting, "integrity": integrity}


def _preconditions(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    evidence = _evidence(core)
    ledger = _d(evidence.get("ledger"))
    accounting = _d(evidence.get("accounting"))
    rebuilt = _d(accounting.get("reconstructed"))
    integrity = _d(evidence.get("integrity"))
    forward = _d(integrity.get("forward_validation"))
    epoch_evidence = _d(integrity.get("post_recovery_evidence_epoch"))
    post_epoch_rows = _i(
        forward.get(
            "post_epoch_valid_exact_lifecycle_rows",
            epoch_evidence.get("post_epoch_valid_exact_lifecycle_rows"),
        )
    )
    stored_cash = _f(state.get("cash"))
    stored_equity = _f(state.get("equity"))
    reconstructed_cash = _f(rebuilt.get("cash"), float("inf"))
    reconstructed_equity = _f(rebuilt.get("equity"), float("inf"))
    money_tolerance = max(0.01, abs(stored_equity) * 1e-8)
    checks = {
        "paper_runtime": _paper_only(),
        "target_epoch": str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID,
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived")),
        "validation_hold_active": bool(epoch.get("validation_hold")),
        "validation_release_blocked": str(epoch.get("validation_release_status") or "") == "blocked",
        "forward_validation_required": bool(epoch.get("forward_validation_required")),
        "risk_not_halted": not bool(risk.get("halted")),
        "self_defense_inactive": not bool(risk.get("self_defense_active")),
        "canonical_chain_valid": bool(ledger.get("chain_valid")),
        "canonical_ledger_authoritative": bool(ledger.get("authoritative_for_new_executions")),
        "canonical_epoch_matches": str(ledger.get("current_epoch_id") or "") == TARGET_EPOCH_ID,
        "canonical_epoch_has_rows": _i(ledger.get("current_epoch_rows")) > 0,
        "accounting_coverage_complete": bool(accounting.get("coverage_complete")),
        "accounting_no_coverage_issues": _i(accounting.get("coverage_issue_count")) == 0,
        "accounting_no_economic_issues": _i(accounting.get("economic_issue_count")) == 0,
        "accounting_reconstructed_flat": not _d(rebuilt.get("open_positions")),
        "cash_matches_reconstruction": abs(stored_cash - reconstructed_cash) <= money_tolerance,
        "equity_matches_reconstruction": abs(stored_equity - reconstructed_equity) <= money_tolerance,
        "integrity_not_failed": str(integrity.get("status") or "").lower() != "fail",
        "forward_promotion_evidence_eligible": forward.get("promotion_evidence_eligible") is True,
        "post_epoch_rows_sufficient": post_epoch_rows >= MINIMUM_POST_EPOCH_VALID_ROWS,
    }
    return {
        "checks": checks,
        "failed": [name for name, ok in checks.items() if not ok],
        "post_epoch_valid_exact_lifecycle_rows": post_epoch_rows,
        "evidence": evidence,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}

    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    active = str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    if active and not bool(epoch.get("validation_hold")):
        result = {
            "status": "released",
            "overall": "pass",
            "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID,
            "already_released": True,
            "released_local": epoch.get("validation_released_local"),
        }
        _LAST = result
        return result

    pre = _preconditions(core)
    if pre["failed"]:
        result = {
            "status": "blocked",
            "overall": "warn",
            "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID,
            "reason": "v4_validation_release_preconditions_not_met",
            "failed_checks": pre["failed"],
            "checks": pre["checks"],
            "post_epoch_valid_exact_lifecycle_rows": pre["post_epoch_valid_exact_lifecycle_rows"],
        }
        _LAST = result
        return result

    # Change only the v4 epoch's validation metadata. Risk state and all trading
    # authority remain byte-for-byte unchanged.
    epoch_before = dict(epoch)
    epoch["validation_hold"] = False
    epoch["validation_hold_reason"] = ""
    epoch["validation_release_status"] = "released"
    epoch["validation_released"] = True
    epoch["validation_released_local"] = _now(core)
    epoch["validation_release_version"] = VERSION
    epoch["forward_validation_required"] = False
    epoch["forward_validation_completed_rows"] = pre["post_epoch_valid_exact_lifecycle_rows"]
    state["paper_accounting_epoch"] = epoch

    save = getattr(core, "save_state", None)
    if not callable(save):
        epoch.clear()
        epoch.update(epoch_before)
        return {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_missing"}
    try:
        save(state)
    except TypeError:
        try:
            save()
        except Exception as exc:
            epoch.clear()
            epoch.update(epoch_before)
            return {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_failed", "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        epoch.clear()
        epoch.update(epoch_before)
        return {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_failed", "error": f"{type(exc).__name__}: {exc}"}

    result = {
        "status": "released",
        "overall": "pass",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "already_released": False,
        "released_local": epoch.get("validation_released_local"),
        "post_epoch_valid_exact_lifecycle_rows": pre["post_epoch_valid_exact_lifecycle_rows"],
        "checks": pre["checks"],
    }
    _LAST = result
    return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _portfolio(core) if core is not None else {}
    epoch = _d(state.get("paper_accounting_epoch"))
    active = str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    released = bool(active and not epoch.get("validation_hold") and epoch.get("validation_released"))
    attempted_but_not_persisted = bool(
        active
        and not released
        and _LAST.get("status") == "released"
        and _LAST.get("already_released") is False
    )
    return {
        "status": "released" if released else "blocked" if attempted_but_not_persisted else _LAST.get("status", "pending"),
        "overall": "pass" if released else "fail" if attempted_but_not_persisted else _LAST.get("overall", "warn"),
        "type": "verified_v4_validation_release_status",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "released": released,
        "validation_hold": bool(epoch.get("validation_hold")) if active else None,
        "released_local": epoch.get("validation_released_local") if active else None,
        "reason": "release_attempt_not_reflected_in_authoritative_state" if attempted_but_not_persisted else None,
        "last_result": dict(_LAST),
        "authority": {
            "paper_only": True,
            "changes_only_v4_validation_metadata": True,
            "clears_risk_halts": False,
            "edits_or_deletes_canonical_rows": False,
            "rewrites_current_day_peak": False,
            "rewrites_history": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    from flask import jsonify
    path = "/paper/verified-v4-validation-release-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(path, "verified_v4_validation_release_status", lambda: jsonify(status_payload(core)))
    return status_payload(core)
