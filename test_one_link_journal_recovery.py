import json
import types

import final_daily_audit_compactor as compact
import paper_journal_forensic_recovery as recovery


def test_compactor_omits_large_forensic_arrays():
    payload = {
        "status": "ok",
        "overall": "fail",
        "generated_local": "2026-08-10 12:00:00 CDT",
        "duration_seconds": 0.2,
        "version": "x",
        "sections": {
            "01_account_and_open_position_performance": {"cash": 1, "equity": 2, "positions": ["QQQ"]},
            "02_auto_runner_liveness": {"status": "pass", "enabled": True},
            "04_risk_controls_and_drawdown": {"status": "fail", "halted": True, "reasons": ["risk_halted"]},
            "05_scanner_signals_entries_rejections": {"signals_found": 3, "entries_count": 0},
            "10b_market_data_and_path_integrity": {
                "status": "fail",
                "reasons": ["paper_accounting_integrity_not_reconciled"],
                "paper_accounting_integrity": {
                    "status": "warn", "coverage_complete": False,
                    "reconstructed": {"ignored_trade_rows": 19, "coverage_issue_count": 19, "coverage_issues": [{"x": 1}] * 50},
                },
                "paper_ledger_economic_integrity": {"economic_issue_count": 19, "economic_issues": [{"x": 1}] * 20},
                "forward_validation": {"promotion_evidence_eligible": False},
                "provider_request_accounting": {"requests": 10, "classified_terminal_outcomes": 10},
            },
            "11_conclusion": {"pass_count": 9, "warn_count": 0, "fail_count": 2},
            "12_next_action": {"status": "required", "priority": "high", "reason": "risk_halted"},
        },
    }
    out = compact.compact_payload(payload, None)
    text = json.dumps(out)
    assert "coverage_issues" not in text
    assert "economic_issues" not in text
    assert out["summary"]["fail"] == 2
    assert out["accounting_integrity"]["coverage_issue_count"] == 19


def test_journal_semantic_dedupe():
    row = {"time": "1", "action": "entry", "symbol": "QQQ", "side": "long", "shares": 2, "price": 100}
    dup = dict(row, journal_key="different", journal_source="backup")
    rows = recovery._candidate_rows({"trades": [row, dup]})
    assert len(rows) == 1


def test_journal_status_is_read_only(monkeypatch, tmp_path):
    journal_path = tmp_path / "trade_journal.json"
    journal_path.write_text(json.dumps({"trades": []}), encoding="utf-8")
    fake_tj = types.SimpleNamespace(TRADE_JOURNAL_FILE=str(journal_path))
    monkeypatch.setitem(__import__("sys").modules, "trade_journal", fake_tj)
    core = types.SimpleNamespace(portfolio={"history": [10000], "trades": []})
    out = recovery.status_payload(core)
    assert out["journal_available"] is True
    assert out["authority"]["repairs_state"] is False
