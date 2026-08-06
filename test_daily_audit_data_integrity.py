from __future__ import annotations

from types import SimpleNamespace

import daily_operational_audit as audit


def _base_portfolio():
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "positions": {"AI": {"entry": 10.0, "last_price": 10.0, "unrealized_pnl": 0.0}},
        "trades": [],
        "performance": {"realized_pnl_today": 0.0, "realized_pnl_total": 0.0, "unrealized_pnl": 0.0},
        "auto_runner": {
            "enabled": True,
            "thread_started": True,
            "last_attempt_local": "2026-08-06 09:30:00",
            "last_attempt_source": "auto",
            "last_run_local": "2026-08-06 09:31:00",
            "last_successful_run_local": "2026-08-06 09:31:00",
        },
        "risk_controls": {"halted": False, "self_defense_active": False, "daily_loss_pct": 0.0, "intraday_drawdown_pct": 0.0},
        "scanner_audit": {"signals_found": 0, "entries_count": 0, "rejected_signals_count": 0},
        "decision_audit": {"signals_found": 0, "entries_count": 0, "rejected_signals_count": 0, "rejected_signals": []},
        "trade_journal": {"journal_summary": {"execution_rows": 0, "open_positions_count": 1}},
        "runtime_shadow_capture": {"capture_state": "captured", "latest_parity": True},
    }


def test_audit_warns_when_protected_symbols_are_quarantined(monkeypatch):
    portfolio = _base_portfolio()
    core = SimpleNamespace(
        portfolio=portfolio,
        app=None,
        STATE_FILE="state.json",
        local_ts_text=lambda: "2026-08-06 09:32:00",
    )

    original = audit._status_payload

    def fake_status(module_name, runtime, argument=None):
        if module_name == "yfinance_data_hygiene":
            return {
                "installed": True,
                "protected_symbols": ["SPY", "QQQ", "AI"],
                "active_symbol_backoffs": {"SPY": {"reason": "short_retry_backoff"}},
            }
        if module_name == "market_data_resilience":
            return {"installed": True, "provider_circuit_open": False, "distinct_provider_failure_symbols": []}
        if module_name == "mae_mfe_integration":
            return {"status": "ok", "integrity": {"quarantined_rows": 0, "training_eligible_rows": 0}}
        if module_name == "entry_pipeline_composition_guard":
            return {"stack_stable": True, "recursion_safe": True, "participation_valve_chain_cycle_free": True, "direct_core_base": True}
        if module_name == "bear_recovery_stack_contract":
            return {"owned": True, "wrapper_counts": {"bear_wrapper_count": 1, "xray_wrapper_count": 1}}
        if module_name == "runtime_shadow_capture":
            return {"capture_state": "captured", "latest_parity": True}
        return original(module_name, runtime, argument)

    monkeypatch.setattr(audit, "_status_payload", fake_status)
    monkeypatch.setattr(audit, "_state_persistence", lambda portfolio, core: {
        "state_file": "state.json", "state_file_exists": True, "state_file_size_bytes": 1,
        "state_file_modified_age_seconds": 1.0, "persistent_volume_configured": True,
        "backup_count": 1, "latest_backup": "state.json.bak", "transaction_status": "ok",
        "recovery_status": "ok", "archive_status": "ok", "provenance_status": "ok",
        "corruption_detected": False, "last_error": None, "recovery_failed": False,
    })

    payload = audit.build_payload(core)
    section = payload["sections"]["11_market_data_and_path_integrity"]
    assert section["status"] == "fail"
    assert "protected_symbol_quarantined" in section["reasons"]
    assert payload["overall"] == "fail"
