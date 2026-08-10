"""Final-stage compact response for the routine daily audit.

Registered early so Flask executes this after_request handler last. The routine
/paper/daily-audit response is intentionally small and operator-oriented.
?full=1 preserves the complete forensic audit.
"""
from __future__ import annotations

from typing import Any, Dict

VERSION = "final-daily-audit-compactor-2026-08-10-v1"
_REGISTERED = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _journal_status(core: Any = None) -> Dict[str, Any]:
    try:
        import paper_journal_forensic_recovery as module
        return module.status_payload(core)
    except Exception as exc:
        return {"status": "warn", "error": f"{type(exc).__name__}: {exc}"}


def compact_payload(payload: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    sections = _d(payload.get("sections"))
    account = _d(sections.get("01_account_and_open_position_performance"))
    runner = _d(sections.get("02_auto_runner_liveness"))
    errors = _d(sections.get("03_active_errors_and_recursion"))
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

    reasons = []
    for value in _l(risk.get("reasons")) + _l(integrity.get("reasons")):
        if value and value not in reasons:
            reasons.append(value)

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
        "runner": {
            "status": runner.get("status"),
            "enabled": runner.get("enabled"),
            "last_completed_cycle": runner.get("last_completed_cycle_contract") or runner.get("last_completed_cycle"),
            "last_completed_cycle_duration_seconds": runner.get("last_completed_cycle_duration_seconds"),
        },
        "risk": {
            "status": risk.get("status"),
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "self_defense_active": risk.get("self_defense_active"),
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
        },
        "market_data": {
            "status": integrity.get("status"),
            "requests": provider.get("requests"),
            "classified_terminal_outcomes": provider.get("classified_terminal_outcomes"),
            "provider_circuit_open": integrity.get("provider_circuit_open"),
        },
        "ml_evidence": {
            "promotion_evidence_eligible": forward.get("promotion_evidence_eligible"),
            "promotion_block_reason": forward.get("promotion_block_reason"),
            "valid_exact_lifecycle_rows": forward.get("valid_exact_lifecycle_rows_observed"),
            "post_recovery_valid_exact_lifecycle_rows": forward.get("post_recovery_valid_exact_lifecycle_rows"),
        },
        "next_action": {
            "status": next_action.get("status"),
            "priority": next_action.get("priority"),
            "reason": next_action.get("reason"),
            "action": next_action.get("action"),
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
