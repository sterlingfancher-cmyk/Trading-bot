"""Governed paper-only release for the Issue #222 verified-flat v5 successor.

This is the narrow administrative transition required to start the controlled
paper trial authorized in Issue #84. It releases only the v5 successor's own
validation hold plus the exact retained canonical-projection halt inherited
from the archived, unresolved v4 discrepancy. The prior discrepancy remains
immutable and non-promotable. No canonical rows, history, day peak, strategy,
sizing, hard-risk limits, live authority, ML authority, or order authority are
changed here.

The transition is fail-closed and only applies while the active account is
still the exact verified-flat zero-trade v5 baseline. Once any v5 execution is
present, this module cannot perform a first release.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
from typing import Any, Dict

VERSION = "issue84-governed-v5-paper-restart-2026-09-25-v1"
TARGET_EPOCH_ID = "stable-paper-v5-20260914-issue222-flat-successor01"
PRIOR_EPOCH_ID = "stable-paper-v4-20260826-successor01"
SUCCESSOR_DECISION = "issue222_unresolved_v4_projection_verified_flat_successor"
RETAINED_HALT_REASON = "canonical execution/state projection divergence"
EXPECTED_LEDGER_ROWS = 88
EXPECTED_CASH = 13429.13048559457
MONEY_TOLERANCE = 0.01
_LAST: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    except Exception as exc:
        accounting = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        rebuilt = {}
    return {"ledger": ledger, "accounting": accounting, "rebuilt": rebuilt}


def _preconditions(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    successor = _d(state.get("issue222_verified_flat_successor"))
    evidence = _evidence(core)
    ledger = _d(evidence["ledger"])
    accounting = _d(evidence["accounting"])
    rebuilt = _d(evidence["rebuilt"])

    cash = _f(state.get("cash"), -1.0)
    equity = _f(state.get("equity"), -1.0)
    reconstructed_cash = _f(rebuilt.get("cash"), float("inf"))
    reconstructed_equity = _f(rebuilt.get("equity"), float("inf"))

    checks = {
        "paper_runtime": _paper_only(),
        "target_epoch": str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID,
        "prior_epoch_exact": str(epoch.get("prior_epoch_id") or "") == PRIOR_EPOCH_ID,
        "successor_decision_exact": str(epoch.get("historical_recovery_decision") or "") == SUCCESSOR_DECISION,
        "historical_evidence_archived": epoch.get("historical_evidence_archived") is True,
        "validation_hold_active": epoch.get("validation_hold") is True,
        "validation_release_blocked": str(epoch.get("validation_release_status") or "") == "blocked",
        "forward_validation_required": epoch.get("forward_validation_required") is True,
        "prior_discrepancy_unresolved_non_promotable": str(epoch.get("prior_epoch_discrepancy_status") or "") == "unresolved_non_promotable",
        "prior_economics_non_promotable": epoch.get("prior_epoch_economics_promotable") is False,
        "fabricated_exit_rows_zero": int(epoch.get("fabricated_exit_rows") or 0) == 0,
        "successor_marker_validation_hold": str(successor.get("status") or "") == "validation_hold",
        "exact_retained_projection_halt": risk.get("halted") is True and str(risk.get("halt_reason") or "") == RETAINED_HALT_REASON,
        "no_positions": not _d(state.get("positions")),
        "no_v5_state_trades": not _l(state.get("trades")),
        "cash_at_verified_baseline": abs(cash - EXPECTED_CASH) <= MONEY_TOLERANCE,
        "equity_at_verified_baseline": abs(equity - EXPECTED_CASH) <= MONEY_TOLERANCE,
        "canonical_chain_valid": ledger.get("chain_valid") is True,
        "canonical_authoritative": ledger.get("authoritative_for_new_executions") is True,
        "canonical_epoch_exact": str(ledger.get("current_epoch_id") or "") == TARGET_EPOCH_ID,
        "canonical_total_rows_immutable": int(ledger.get("row_count") or 0) == EXPECTED_LEDGER_ROWS,
        "canonical_v5_rows_zero": int(ledger.get("current_epoch_rows") or 0) == 0,
        "canonical_state_projection_parity": ledger.get("state_projection_parity") is True,
        "canonical_missing_from_state_zero": int(ledger.get("missing_from_state_count") or 0) == 0,
        "canonical_missing_from_ledger_zero": int(ledger.get("missing_from_ledger_count") or 0) == 0,
        "accounting_coverage_complete": accounting.get("coverage_complete") is True,
        "accounting_no_coverage_issues": int(accounting.get("coverage_issue_count") or 0) == 0,
        "accounting_no_economic_issues": int(accounting.get("economic_issue_count") or 0) == 0,
        "accounting_reconstructed_flat": not _d(rebuilt.get("open_positions")),
        "cash_matches_reconstruction": abs(cash - reconstructed_cash) <= MONEY_TOLERANCE,
        "equity_matches_reconstruction": abs(equity - reconstructed_equity) <= MONEY_TOLERANCE,
    }
    return {"checks": checks, "failed": [k for k, ok in checks.items() if not ok]}


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}

    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    active = str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    already_released = bool(
        active
        and epoch.get("validation_hold") is False
        and epoch.get("validation_released") is True
        and str(epoch.get("validation_release_status") or "") == "released"
        and risk.get("halted") is False
        and str(epoch.get("validation_release_version") or "") == VERSION
    )
    if already_released:
        result = {
            "status": "released", "overall": "pass", "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID, "already_released": True,
            "released_local": epoch.get("validation_released_local"),
        }
        _LAST = result
        return result

    pre = _preconditions(core)
    if pre["failed"]:
        result = {
            "status": "blocked", "overall": "warn", "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID,
            "reason": "governed_v5_restart_preconditions_not_met",
            "failed_checks": pre["failed"], "checks": pre["checks"],
        }
        _LAST = result
        return result

    epoch_before = copy.deepcopy(epoch)
    risk_before = copy.deepcopy(risk)
    feedback_before = copy.deepcopy(_d(state.get("feedback_loop")))
    successor_before = copy.deepcopy(_d(state.get("issue222_verified_flat_successor")))
    released_local = _now(core)

    epoch["validation_hold"] = False
    epoch["validation_hold_reason"] = ""
    epoch["validation_release_status"] = "released"
    epoch["validation_released"] = True
    epoch["validation_released_local"] = released_local
    epoch["validation_release_version"] = VERSION
    epoch["forward_validation_required"] = True
    state["paper_accounting_epoch"] = epoch

    # Clear only the exact inherited administrative projection halt. The archived
    # v4 discrepancy remains unresolved/non-promotable in epoch metadata.
    risk["halted"] = False
    risk["halt_reason"] = ""
    state["risk_controls"] = risk

    feedback = _d(state.get("feedback_loop"))
    feedback["hard_halt"] = False
    feedback["block_new_entries"] = False
    feedback["administrative_hold_active"] = False
    feedback["administrative_hold_reason"] = ""
    feedback["reasons"] = ["governed v5 paper trial released; normal hard-risk controls remain authoritative"]
    state["feedback_loop"] = feedback

    successor = _d(state.get("issue222_verified_flat_successor"))
    successor["status"] = "paper_trial_released"
    successor["validation_hold"] = False
    successor["risk_halt_cleared"] = True
    successor["governed_release_version"] = VERSION
    successor["governed_release_local"] = released_local
    successor["unresolved_prior_discrepancy"] = True
    successor["prior_epoch_economics_promotable"] = False
    successor["fabricated_exit_rows"] = 0
    successor["canonical_history_rewritten"] = False
    state["issue222_verified_flat_successor"] = successor

    save = getattr(core, "save_state", None)
    if not callable(save):
        epoch.clear(); epoch.update(epoch_before)
        risk.clear(); risk.update(risk_before)
        state["feedback_loop"] = feedback_before
        state["issue222_verified_flat_successor"] = successor_before
        result = {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_missing"}
        _LAST = result
        return result
    try:
        try:
            save(state)
        except TypeError:
            save()
    except Exception as exc:
        epoch.clear(); epoch.update(epoch_before)
        risk.clear(); risk.update(risk_before)
        state["feedback_loop"] = feedback_before
        state["issue222_verified_flat_successor"] = successor_before
        result = {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_failed", "error": f"{type(exc).__name__}: {exc}"}
        _LAST = result
        return result

    result = {
        "status": "released", "overall": "pass", "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID, "already_released": False,
        "released_local": released_local, "checks": pre["checks"],
        "forward_validation_required": True,
    }
    _LAST = result
    return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _portfolio(core) if core is not None else {}
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    active = str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    released = bool(
        active and epoch.get("validation_hold") is False
        and epoch.get("validation_released") is True
        and str(epoch.get("validation_release_status") or "") == "released"
        and not risk.get("halted")
        and str(epoch.get("validation_release_version") or "") == VERSION
    )
    return {
        "status": "released" if released else _LAST.get("status", "pending"),
        "overall": "pass" if released else _LAST.get("overall", "warn"),
        "type": "issue84_governed_v5_paper_restart_status",
        "version": VERSION, "epoch_id": TARGET_EPOCH_ID,
        "released": released,
        "validation_hold": epoch.get("validation_hold") if active else None,
        "risk_halted": bool(risk.get("halted")) if active else None,
        "halt_reason": risk.get("halt_reason") if active else None,
        "forward_validation_required": epoch.get("forward_validation_required") if active else None,
        "prior_epoch_discrepancy_status": epoch.get("prior_epoch_discrepancy_status") if active else None,
        "prior_epoch_economics_promotable": epoch.get("prior_epoch_economics_promotable") if active else None,
        "last_result": dict(_LAST),
        "authority": {
            "paper_only": True,
            "clears_only_exact_issue222_v5_administrative_hold_and_inherited_projection_halt": True,
            "preserves_prior_unresolved_discrepancy": True,
            "edits_or_deletes_canonical_rows": False,
            "rewrites_history": False,
            "rewrites_day_peak": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_hard_risk_limits_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    from flask import jsonify
    path = "/paper/issue84-governed-v5-restart-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(path, "issue84_governed_v5_restart_status", lambda: jsonify(status_payload(core)))
    return status_payload(core)
