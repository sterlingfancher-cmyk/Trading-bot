"""Final-stage compact response for the routine daily audit.

Registered early so Flask executes this after_request handler last. The routine
/paper/daily-audit response is intentionally small and operator-oriented.
?full=1 preserves the complete forensic audit.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "final-daily-audit-compactor-2026-08-13-v5-active-epoch-runner-diagnostics"
_REGISTERED = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _i(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(value))
    except Exception:
        return 0


def _journal_status(core: Any = None) -> Dict[str, Any]:
    try:
        import paper_journal_forensic_recovery as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def _ledger_status(core: Any = None) -> Dict[str, Any]:
    try:
        import canonical_execution_ledger as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def _legacy_epoch_status(core: Any = None) -> Dict[str, Any]:
    try:
        import clean_accounting_epoch as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def _active_epoch_status(core: Any = None) -> Dict[str, Any]:
    """Report the active persisted epoch before falling back to legacy migration status."""
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    epoch = _d(portfolio.get("paper_accounting_epoch"))
    epoch_id = epoch.get("id") or portfolio.get("accounting_epoch_id")
    if epoch or epoch_id:
        return {
            "status": "ok" if epoch_id else "warn",
            "epoch_id": epoch_id,
            "starting_cash": epoch.get("starting_cash"),
            "starting_equity": epoch.get("starting_equity"),
            "clean_start": epoch.get("clean_start"),
            "zero_trade_baseline": epoch.get("zero_trade_baseline"),
            "baseline_type": epoch.get("baseline_type"),
            "historical_recovery_decision": epoch.get("historical_recovery_decision"),
            "historical_evidence_archived": epoch.get("historical_evidence_archived"),
            "validation_hold": epoch.get("validation_hold"),
            "forward_validation_required": epoch.get("forward_validation_required"),
            "prior_epoch_id": epoch.get("prior_epoch_id"),
            "source": "active_portfolio_epoch",
        }
    legacy = _legacy_epoch_status(core)
    return {**legacy, "source": "legacy_clean_epoch_status_fallback"}


def _release_status(core: Any = None) -> Dict[str, Any]:
    try:
        import clean_epoch_validation_release as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def _bidirectional_status(core: Any = None) -> Dict[str, Any]:
    try:
        import paper_bidirectional_accounting_guard as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def _runner_diagnostics(core: Any = None) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    auto = _d(portfolio.get("auto_runner"))
    return {
        "last_error": auto.get("last_error"),
        "last_attempt": auto.get("last_attempt_local") or auto.get("last_attempt_ts"),
        "last_attempt_source": auto.get("last_attempt_source"),
        "last_run": auto.get("last_run_local") or auto.get("last_run_ts"),
        "last_successful_run": auto.get("last_successful_run_local") or auto.get("last_successful_run_ts"),
        "last_successful_run_source": auto.get("last_successful_run_source"),
    }


def _market_data_status(integrity: Dict[str, Any], provider: Dict[str, Any]) -> str:
    requests = _i(provider.get("requests"))
    classified = _i(provider.get("classified_terminal_outcomes"))
    gap = _i(provider.get("in_flight_or_unclassified_requests"))
    if not gap and requests > classified:
        gap = requests - classified
    over = _i(provider.get("provider_outcomes_over_request_count"))
    protected_blocked = _l(integrity.get("protected_symbols_blocked"))
    if bool(integrity.get("provider_circuit_open")) or protected_blocked or over > 0:
        return "fail"
    # One open request is an expected concurrent snapshot state because the
    # request counter increments before its terminal outcome is recorded.
    if gap > 1:
        return "warn"
    return "pass"


def compact_payload(payload: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    sections = _d(payload.get("sections"))
    account = _d(sections.get("01_account_and_open_position_performance"))
    runner = _d(sections.get("02_auto_runner_liveness"))
    risk = _d(sections.get("04_risk_controls_and_drawdown"))
    scanner = _d(sections.get("05_scanner_signals_entries_rejections"))
    integrity = _d(sections.get("10b_market_data_and_path_integrity"))
    accounting = _d(integrity.get("paper_accounting_integrity"))
    rebuilt = _d(accounting.get("reconstructed"))
    economics = _d(integrity.get("paper_ledger_economic_integrity"))
    forward = _d(integrity.get("forward_validation"))
    provider = _d(integrity.get("provider_request_accounting"))
    conclusion = _d(sections.get("11_conclusion"))
    next_action = _d(sections.get("12_next_action"))
    journal = _journal_status(core)
    ledger = _ledger_status(core)
    epoch = _active_epoch_status(core)
    release = _release_status(core)
    bidirectional = _bidirectional_status(core)
    runner_diagnostics = _runner_diagnostics(core)

    reasons = []
    for value in _l(risk.get("reasons")) + _l(integrity.get("reasons")):
        if value and value not in reasons:
            reasons.append(value)

    next_reason = next_action.get("reason")
    next_action_text = next_action.get("action")
    next_priority = next_action.get("priority")
    if next_reason == "clean_accounting_epoch_forward_validation_required":
        next_action_text = "Continue normal paper operation and collect the first clean exact lifecycle before any ML/MAE-MFE promotion."
        next_priority = "normal"

    requests = _i(provider.get("requests"))
    classified = _i(provider.get("classified_terminal_outcomes"))
    gap = _i(provider.get("in_flight_or_unclassified_requests"))
    if not gap and requests > classified:
        gap = requests - classified

    return {
        "status": payload.get("status"),
        "overall": payload.get("overall"),
        "type": "daily_operational_audit_compact_final",
        "version": payload.get("version"),
        "generated_local": payload.get("generated_local"),
        "duration_seconds": payload.get("duration_seconds"),
        "summary": {
            "pass": conclusion.get("pass_count"),
            "warn": conclusion.get("warn_count"),
            "fail": conclusion.get("fail_count"),
            "reasons": reasons[:6],
        },
        "account": {
            "cash": account.get("cash"),
            "equity": account.get("equity"),
            "positions": account.get("positions") or [],
            "realized_today": account.get("realized_today"),
            "unrealized_pnl": account.get("unrealized_pnl"),
        },
        "accounting_epoch": {
            "status": epoch.get("status"),
            "epoch_id": epoch.get("epoch_id"),
            "starting_cash": epoch.get("starting_cash"),
            "starting_equity": epoch.get("starting_equity"),
            "clean_start": epoch.get("clean_start"),
            "zero_trade_baseline": epoch.get("zero_trade_baseline"),
            "baseline_type": epoch.get("baseline_type"),
            "historical_recovery_decision": epoch.get("historical_recovery_decision"),
            "historical_evidence_archived": epoch.get("historical_evidence_archived"),
            "validation_hold": epoch.get("validation_hold"),
            "forward_validation_required": epoch.get("forward_validation_required"),
            "prior_epoch_id": epoch.get("prior_epoch_id"),
            "source": epoch.get("source"),
            "validation_release_status": release.get("status"),
            "validation_released": release.get("released"),
            "validation_released_local": release.get("released_local"),
        },
        "runner": {
            "status": runner.get("status"),
            "enabled": runner.get("enabled"),
            "last_completed_cycle": runner.get("last_completed_cycle_contract") or runner.get("last_completed_cycle"),
            "last_completed_cycle_duration_seconds": runner.get("last_completed_cycle_duration_seconds"),
            "active_error": bool(next_reason == "active_auto_runner_error"),
            **runner_diagnostics,
        },
        "risk": {
            "status": risk.get("status"),
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
            "net_daily_loss_pct": risk.get("net_daily_loss_pct", risk.get("realized_loss_pct")),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
        },
        "scanner": {
            "signals_found": scanner.get("signals_found"),
            "entries_count": scanner.get("entries_count"),
            "rejected_signals_count": scanner.get("rejected_signals_count"),
        },
        "accounting_integrity": {
            "status": accounting.get("status"),
            "coverage_complete": accounting.get("coverage_complete"),
            "baseline_type": rebuilt.get("baseline_type"),
            "supports_long_short": bidirectional.get("supports_long_short"),
            "accounting_model": "bidirectional_margin_v1" if bidirectional.get("supports_long_short") else None,
            "ignored_trade_rows": rebuilt.get("ignored_trade_rows"),
            "coverage_issue_count": rebuilt.get("coverage_issue_count"),
            "economic_issue_count": economics.get("economic_issue_count"),
            "reconstructed_cash": rebuilt.get("cash"),
            "reconstructed_equity": rebuilt.get("equity"),
        },
        "journal_recovery_candidate": {
            "status": journal.get("status"),
            "journal_trade_rows": journal.get("journal_trade_rows"),
            "deduplicated_execution_rows": journal.get("deduplicated_execution_rows"),
            "entry_rows": journal.get("entry_rows"),
            "exit_rows": journal.get("exit_rows"),
            "coverage_complete": journal.get("coverage_complete"),
            "coverage_issue_count": journal.get("coverage_issue_count"),
            "economic_issue_count": journal.get("economic_issue_count"),
            "candidate_cash": journal.get("candidate_cash"),
            "candidate_equity": journal.get("candidate_equity"),
            "trusted_recovery_candidate": journal.get("trusted_recovery_candidate"),
            "decision_complete": journal.get("decision_complete"),
            "historical_recovery_disposition": journal.get("historical_recovery_disposition"),
        },
        "execution_ledger": {
            "status": ledger.get("status"),
            "chain_valid": ledger.get("chain_valid"),
            "row_count": ledger.get("row_count"),
            "current_epoch_id": ledger.get("current_epoch_id"),
            "current_epoch_rows": ledger.get("current_epoch_rows"),
            "authoritative_for_new_executions": ledger.get("authoritative_for_new_executions"),
        },
        "market_data": {
            "status": _market_data_status(integrity, provider),
            "requests": requests,
            "classified_terminal_outcomes": classified,
            "in_flight_or_unclassified_requests": gap,
            "accounting_complete_at_snapshot": provider.get("accounting_complete_at_snapshot"),
            "provider_circuit_open": integrity.get("provider_circuit_open"),
        },
        "ml_evidence": {
            "status": "pass" if forward.get("promotion_evidence_eligible") else "warn",
            "promotion_evidence_eligible": forward.get("promotion_evidence_eligible"),
            "promotion_block_reason": forward.get("promotion_block_reason"),
            "valid_exact_lifecycle_rows": forward.get("valid_exact_lifecycle_rows_observed"),
            "post_recovery_valid_exact_lifecycle_rows": forward.get("post_recovery_valid_exact_lifecycle_rows"),
            "post_epoch_valid_exact_lifecycle_rows": forward.get("post_epoch_valid_exact_lifecycle_rows"),
        },
        "next_action": {
            "status": next_action.get("status"),
            "priority": next_priority,
            "reason": next_reason,
            "action": next_action_text,
        },
        "full_audit": "https://web-production-e1796.up.railway.app/paper/daily-audit?full=1",
        "compactor_version": VERSION,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {"status": "ok", "overall": "pass", "version": VERSION, "reporting_only": True}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "warn", "overall": "warn", "version": VERSION}
    app_id = id(flask_app)
    if app_id not in _REGISTERED:
        from flask import request

        @flask_app.after_request
        def _compact_daily_audit_response(response):
            try:
                if request.path != "/paper/daily-audit" or request.args.get("full") == "1":
                    return response
                payload = response.get_json(silent=True)
                if not isinstance(payload, dict):
                    return response
                compact = compact_payload(payload, core)
                response.set_data(flask_app.json.dumps(compact))
                response.content_type = "application/json"
                response.content_length = len(response.get_data())
            except Exception:
                return response
            return response

        _REGISTERED.add(app_id)
    return {"status": "ok", "overall": "pass", "version": VERSION, "registered": True}
