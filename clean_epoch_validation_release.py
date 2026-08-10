"""One-time release of the clean-accounting validation hold.

The clean epoch was intentionally deployed halted so its zero-trade baseline
could be verified from Railway before paper execution resumed.  The operator's
post-cutover audit established that baseline.  This module re-verifies the same
facts in-process on the next deployment and clears *only* the administrative
clean-epoch hold when every invariant still agrees.

It cannot clear any other risk halt and cannot run outside paper mode.  It does
not change strategy logic, thresholds, sizing, live authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List

VERSION = "clean-epoch-validation-release-2026-08-10-v1"
TARGET_EPOCH_ID = "stable-paper-v1-20260810-clean01"
EXPECTED_STARTING_CASH = float(os.environ.get("CLEAN_EPOCH_STARTING_CASH", "10000"))
_RELEASED_CORE_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _risk_metrics_zero(risk: Dict[str, Any]) -> bool:
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


def _evidence(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    realized = _d(state.get("realized_pnl"))
    perf = _d(state.get("performance"))

    try:
        import canonical_execution_ledger as ledger_module
        ledger = ledger_module.status_payload(core)
    except Exception as exc:
        ledger = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        import paper_bidirectional_accounting_guard as bidirectional
        bidir = bidirectional.status_payload(core)
    except Exception as exc:
        bidir = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        import paper_accounting_integrity_guard as accounting
        integrity = accounting.status_payload(core)
    except Exception as exc:
        integrity = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    try:
        import paper_journal_forensic_recovery as journal_module
        journal = journal_module.status_payload(core)
    except Exception as exc:
        journal = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    return {
        "state": state,
        "epoch": epoch,
        "risk": risk,
        "realized": realized,
        "performance": perf,
        "ledger": ledger,
        "bidirectional": bidir,
        "integrity": integrity,
        "journal": journal,
    }


def _preconditions(core: Any) -> Dict[str, Any]:
    e = _evidence(core)
    state = e["state"]
    epoch = e["epoch"]
    risk = e["risk"]
    realized = e["realized"]
    perf = e["performance"]
    ledger = e["ledger"]
    bidir = e["bidirectional"]
    integrity = e["integrity"]
    journal = e["journal"]
    rebuilt = _d(integrity.get("reconstructed"))

    money_tol = max(0.01, EXPECTED_STARTING_CASH * 1e-8)
    checks = {
        "paper_runtime": _paper_only(),
        "target_epoch": str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID,
        "clean_start": bool(epoch.get("clean_start")),
        "zero_trade_baseline": bool(epoch.get("zero_trade_baseline")),
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived")),
        "validation_hold_active": bool(risk.get("clean_epoch_validation_hold")),
        "validation_halt_reason_exact": str(risk.get("halt_reason") or "") == "clean accounting epoch validation hold",
        "cash_at_baseline": abs(_f(state.get("cash")) - EXPECTED_STARTING_CASH) <= money_tol,
        "equity_at_baseline": abs(_f(state.get("equity")) - EXPECTED_STARTING_CASH) <= money_tol,
        "no_positions": not _d(state.get("positions")),
        "no_state_trades": not _l(state.get("trades")),
        "realized_zero": abs(_f(realized.get("today"))) <= money_tol and abs(_f(realized.get("total"))) <= money_tol,
        "unrealized_zero": abs(_f(perf.get("unrealized_pnl"))) <= money_tol,
        "risk_metrics_zero": _risk_metrics_zero(risk),
        "canonical_ledger_chain_valid": bool(ledger.get("chain_valid")),
        "canonical_ledger_authoritative": bool(ledger.get("authoritative_for_new_executions")),
        "canonical_ledger_empty": int(ledger.get("row_count") or 0) == 0,
        "canonical_epoch_empty": int(ledger.get("current_epoch_rows") or 0) == 0,
        "canonical_epoch_matches": str(ledger.get("current_epoch_id") or "") == TARGET_EPOCH_ID,
        "bidirectional_accounting_installed": bidir.get("status") == "ok" and bool(bidir.get("supports_long_short")),
        "accounting_coverage_complete": bool(integrity.get("coverage_complete")),
        "accounting_clean_zero_trade_baseline": rebuilt.get("baseline_type") == "clean_zero_trade_epoch",
        "accounting_no_coverage_issues": int(rebuilt.get("coverage_issue_count") or 0) == 0,
        "accounting_no_economic_issues": int(rebuilt.get("economic_issue_count") or 0) == 0,
        "journal_decision_complete": bool(journal.get("decision_complete")),
        "journal_archived": str(journal.get("status") or "") == "archived",
        "journal_remains_untrusted": journal.get("trusted_recovery_candidate") is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"checks": checks, "failed": failed, "evidence": e}


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}

    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))

    if str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID and not risk.get("clean_epoch_validation_hold"):
        result = {
            "status": "released",
            "overall": "pass",
            "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID,
            "already_released": True,
            "released_local": epoch.get("validation_released_local"),
        }
        _RELEASED_CORE_IDS.add(id(core))
        _LAST = result
        return result

    pre = _preconditions(core)
    if pre["failed"]:
        result = {
            "status": "blocked",
            "overall": "warn",
            "version": VERSION,
            "epoch_id": TARGET_EPOCH_ID,
            "reason": "clean_epoch_release_preconditions_not_met",
            "failed_checks": pre["failed"],
            "checks": pre["checks"],
        }
        _LAST = result
        return result

    # Clear only the explicitly named administrative hold.  Any other halt reason
    # fails the precondition above and is preserved.
    risk["halted"] = False
    risk["halt_reason"] = ""
    risk["clean_epoch_validation_hold"] = False
    risk["clean_epoch_validation_hold_reason"] = ""
    risk["administrative_hold_active"] = False
    risk["administrative_hold_reason"] = ""
    risk["self_defense_active"] = False
    risk["self_defense_reason"] = ""
    risk["clean_epoch_validation_released_local"] = _now(core)
    risk["clean_epoch_validation_release_version"] = VERSION
    state["risk_controls"] = risk

    feedback = _d(state.get("feedback_loop"))
    feedback["self_defense_mode"] = False
    feedback["block_new_entries"] = False
    feedback["hard_halt"] = False
    feedback["reasons"] = ["clean accounting epoch validated; normal risk controls active"]
    feedback["administrative_hold_active"] = False
    state["feedback_loop"] = feedback

    epoch["validation_hold"] = False
    epoch["validation_hold_reason"] = ""
    epoch["validation_released_local"] = _now(core)
    epoch["validation_release_version"] = VERSION
    epoch["stable_paper_day_count"] = int(epoch.get("stable_paper_day_count") or 0)
    state["paper_accounting_epoch"] = epoch

    save = getattr(core, "save_state", None)
    if not callable(save):
        result = {"status": "error", "overall": "fail", "version": VERSION, "reason": "save_state_missing"}
        _LAST = result
        return result
    try:
        save(state)
    except TypeError:
        save()

    _RELEASED_CORE_IDS.add(id(core))
    result = {
        "status": "released",
        "overall": "pass",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "already_released": False,
        "released_local": epoch.get("validation_released_local"),
        "checks": pre["checks"],
    }
    _LAST = result
    return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _portfolio(core) if core is not None else {}
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    active_epoch = str(epoch.get("id") or state.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    released = bool(active_epoch and not risk.get("clean_epoch_validation_hold") and not risk.get("halted"))
    return {
        "status": "released" if released else _LAST.get("status", "pending"),
        "overall": "pass" if released else _LAST.get("overall", "warn"),
        "type": "clean_epoch_validation_release_status",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "released": released,
        "validation_hold": bool(risk.get("clean_epoch_validation_hold")),
        "risk_halted": bool(risk.get("halted")),
        "halt_reason": risk.get("halt_reason"),
        "released_local": epoch.get("validation_released_local"),
        "last_result": dict(_LAST),
        "authority": {
            "paper_only": True,
            "clears_only_clean_epoch_validation_hold": True,
            "clears_other_risk_halts": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_limits_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    path = "/paper/clean-epoch-validation-release-status"
    if path not in existing:
        flask_app.add_url_rule(path, "clean_epoch_validation_release_status", lambda: jsonify(status_payload(core)))
    return status_payload(core)
