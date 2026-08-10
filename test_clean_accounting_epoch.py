import json
import sys
import types

import clean_accounting_epoch as clean
import final_daily_audit_compactor as compact
import paper_journal_forensic_recovery as journal_recovery
import paper_ledger_matched_exit_guard as matched
import paper_trade_action_semantics_recovery as semantics


def _core_with_defaults():
    def risk():
        return {"date": "2026-08-10", "halted": False, "halt_reason": "", "cooldowns": {}}

    return types.SimpleNamespace(
        portfolio={},
        default_state=lambda: {
            "cash": 10000.0,
            "equity": 10000.0,
            "peak": 10000.0,
            "positions": {},
            "history": [],
            "trades": [],
            "risk_controls": risk(),
            "auto_runner": {},
            "realized_pnl": {},
            "performance": {},
            "feedback_loop": {},
            "reports": {},
            "scanner_audit": {},
            "pullback_watchlist": {},
        },
        default_risk_controls=risk,
        default_auto_runner=lambda: {"enabled": True},
        default_realized_pnl=lambda: {"date": "2026-08-10", "today": 0.0, "total": 0.0},
        default_performance=lambda: {"realized_pnl_today": 0.0, "realized_pnl_total": 0.0, "unrealized_pnl": 0.0},
        default_feedback_loop=lambda: {},
        default_reports=lambda: {},
        default_scanner_audit=lambda: {},
        local_ts_text=lambda *args, **kwargs: "2026-08-10 13:20:00 CDT",
    )


def test_build_clean_state_is_zeroed_and_validation_halted():
    core = _core_with_defaults()
    state = clean.build_clean_state(
        core,
        {"archive_dir": "/data/forensic_archives/example"},
        {"coverage_issue_count": 23, "economic_issue_count": 0},
    )

    assert state["accounting_epoch_id"] == clean.TARGET_EPOCH_ID
    assert state["cash"] == 10000.0
    assert state["equity"] == 10000.0
    assert state["positions"] == {}
    assert state["trades"] == []
    assert state["realized_pnl"]["today"] == 0.0
    assert state["realized_pnl"]["total"] == 0.0
    assert state["risk_controls"]["halted"] is True
    assert state["risk_controls"]["clean_epoch_validation_hold"] is True
    assert state["paper_accounting_epoch"]["historical_recovery_decision"] == "clean_epoch"
    assert state["paper_accounting_epoch"]["journal_coverage_issue_count"] == 23


def test_zero_trade_clean_epoch_is_valid_accounting_baseline(monkeypatch):
    core = _core_with_defaults()
    state = clean.build_clean_state(core, {"archive_dir": "/archive"}, {"coverage_issue_count": 23, "economic_issue_count": 0})
    core.portfolio = state

    fake_ledger = types.SimpleNamespace(
        status_payload=lambda runtime: {
            "chain_valid": True,
            "authoritative_for_new_executions": True,
            "row_count": 0,
            "current_epoch_rows": 0,
            "current_epoch_id": clean.TARGET_EPOCH_ID,
        }
    )
    monkeypatch.setitem(sys.modules, "canonical_execution_ledger", fake_ledger)

    rebuilt = matched.analyze_ledger(state, core)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["baseline_type"] == "clean_zero_trade_epoch"
    assert rebuilt["parsed_trade_rows"] == 0
    assert rebuilt["cash"] == 10000.0
    assert rebuilt["equity"] == 10000.0
    assert rebuilt["coverage_issue_count"] == 0


def test_clean_epoch_rejects_nonempty_canonical_ledger(monkeypatch):
    core = _core_with_defaults()
    state = clean.build_clean_state(core, {"archive_dir": "/archive"}, {"coverage_issue_count": 23, "economic_issue_count": 0})
    core.portfolio = state
    fake_ledger = types.SimpleNamespace(
        status_payload=lambda runtime: {
            "chain_valid": True,
            "authoritative_for_new_executions": True,
            "row_count": 1,
            "current_epoch_rows": 1,
            "current_epoch_id": clean.TARGET_EPOCH_ID,
        }
    )
    monkeypatch.setitem(sys.modules, "canonical_execution_ledger", fake_ledger)
    rebuilt = matched.analyze_ledger(state, core)
    assert rebuilt["coverage_complete"] is False
    assert rebuilt["coverage_issue_count"] >= 1


def test_historical_journal_is_archived_after_clean_epoch(monkeypatch, tmp_path):
    journal_path = tmp_path / "trade_journal.json"
    journal_path.write_text(json.dumps({"trades": []}), encoding="utf-8")
    monkeypatch.setitem(sys.modules, "trade_journal", types.SimpleNamespace(TRADE_JOURNAL_FILE=str(journal_path)))

    core = _core_with_defaults()
    state = clean.build_clean_state(core, {"archive_dir": "/archive"}, {"coverage_issue_count": 23, "economic_issue_count": 0})
    core.portfolio = state
    out = journal_recovery.status_payload(core)
    assert out["status"] == "archived"
    assert out["overall"] == "pass"
    assert out["trusted_recovery_candidate"] is False
    assert out["decision_complete"] is True
    assert out["historical_recovery_disposition"] == "archived_after_incomplete_coverage"


def test_action_semantics_does_not_recreate_historical_recovery_on_clean_epoch():
    core = _core_with_defaults()
    state = clean.build_clean_state(core, {"archive_dir": "/archive"}, {"coverage_issue_count": 23, "economic_issue_count": 0})
    core.portfolio = state
    out = semantics.apply(core)
    assert out["mode"] == "clean_epoch_semantics_only"
    assert "paper_accounting_semantics_recovery" not in core.portfolio


def test_compact_audit_exposes_accounting_epoch(monkeypatch):
    monkeypatch.setattr(compact, "_epoch_status", lambda core=None: {
        "status": "validation_hold",
        "epoch_id": clean.TARGET_EPOCH_ID,
        "starting_cash": 10000.0,
        "clean_start": True,
        "zero_trade_baseline": True,
        "historical_recovery_decision": "clean_epoch",
        "historical_evidence_archived": True,
        "validation_hold": True,
    })
    monkeypatch.setattr(compact, "_journal_status", lambda core=None: {"status": "archived", "decision_complete": True})
    monkeypatch.setattr(compact, "_ledger_status", lambda core=None: {"status": "ok", "chain_valid": True, "row_count": 0})
    payload = {
        "status": "ok",
        "overall": "fail",
        "sections": {
            "01_account_and_open_position_performance": {"cash": 10000.0, "equity": 10000.0, "positions": []},
            "02_auto_runner_liveness": {"status": "pass", "enabled": True},
            "04_risk_controls_and_drawdown": {"status": "fail", "halted": True, "halt_reason": "clean accounting epoch validation hold"},
            "05_scanner_signals_entries_rejections": {},
            "10b_market_data_and_path_integrity": {
                "paper_accounting_integrity": {"status": "ok", "coverage_complete": True, "reconstructed": {"baseline_type": "clean_zero_trade_epoch", "cash": 10000.0, "equity": 10000.0}},
                "paper_ledger_economic_integrity": {"economic_issue_count": 0},
                "forward_validation": {},
                "provider_request_accounting": {},
            },
            "11_conclusion": {"pass_count": 10, "warn_count": 0, "fail_count": 1},
            "12_next_action": {},
        },
    }
    out = compact.compact_payload(payload, None)
    assert out["accounting_epoch"]["epoch_id"] == clean.TARGET_EPOCH_ID
    assert out["accounting_epoch"]["validation_hold"] is True
    assert out["accounting_integrity"]["baseline_type"] == "clean_zero_trade_epoch"
