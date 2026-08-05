from __future__ import annotations

import daily_audit_repair_overlay as overlay


def _sections():
    return {
        "05_scanner_signals_entries_rejections": {
            "status": "warn",
            "reasons": ["rejection_count_missing"],
            "signals_found": 3,
            "entries_count": 0,
            "rejected_signals_count": None,
        },
        "06_top_five_blockers": {
            "status": "warn",
            "reasons": ["blocker_reason_missing"],
            "blockers": [
                {"symbol": "BSP", "reason": "entry_quality_block", "score": 0.07},
                {"symbol": "BSP", "reason": None, "score": None},
                {"symbol": "PPTA", "reason": None, "score": None},
            ],
        },
        "08_trade_journal_reconciliation": {
            "status": "warn",
            "reasons": ["trade_journal_summary_missing"],
            "execution_rows": 7,
            "journal_execution_rows": None,
            "open_positions": 2,
            "journal_open_positions": None,
            "last_error": None,
        },
    }


def test_reconciles_rejections_and_deduplicates_blank_blockers():
    sections = _sections()
    portfolio = {
        "scanner_audit": {
            "blocked_entries": [
                {"symbol": "BSP", "reason": "entry_quality_block", "score": 0.07},
                {"symbol": "PPTA", "reason": "entry_quality_block", "score": 0.04},
            ]
        },
        "decision_audit": {},
        "blocked_entry_reason_audit": {},
    }
    overlay._reconcile_scanner(sections, portfolio)
    scanner = sections["05_scanner_signals_entries_rejections"]
    blockers = sections["06_top_five_blockers"]
    assert scanner["rejected_signals_count"] == 2
    assert scanner["rejection_count_source"] == "unique_rejection_telemetry"
    assert scanner["status"] == "pass"
    assert blockers["status"] == "pass"
    assert blockers["reason_coverage_pct"] == 100.0
    assert [row["symbol"] for row in blockers["blockers"]] == ["BSP", "PPTA"]


def test_trade_journal_uses_transparent_authoritative_fallback():
    sections = _sections()
    portfolio = {
        "trades": [{} for _ in range(7)],
        "positions": {"AI": {}, "CRWD": {}},
    }
    overlay._reconcile_journal(sections, portfolio)
    journal = sections["08_trade_journal_reconciliation"]
    assert journal["journal_execution_rows"] == 7
    assert journal["journal_open_positions"] == 2
    assert journal["execution_rows_match"] is True
    assert journal["open_positions_match"] is True
    assert journal["summary_synthesized_for_reporting"] is True
    assert journal["reconciliation_source"] == "authoritative_runtime_state_fallback"
    assert journal["status"] == "pass"


def test_authority_remains_reporting_only():
    authority = overlay.status_payload()["authority"]
    assert authority["classification_and_reporting_only"] is True
    assert authority["changes_strategy"] is False
    assert authority["changes_thresholds"] is False
    assert authority["changes_risk_or_sizing"] is False
    assert authority["changes_live_or_ml_authority"] is False
    assert authority["places_orders"] is False
