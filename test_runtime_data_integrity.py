from __future__ import annotations

from types import SimpleNamespace

import yfinance_data_hygiene as hygiene
import market_data_resilience as resilience
import intratrade_path_capture as path_capture
import mae_mfe_integration as integration


def reset_hygiene():
    with hygiene._LOCK:
        hygiene._SYMBOL_STATE.clear()
        hygiene._CACHE.clear()
        hygiene._PROTECTED_SYMBOLS.clear()
        hygiene._PROTECTED_SYMBOLS.update(hygiene._DEFAULT_PROTECTED_SYMBOLS)
        for key in hygiene._TOTALS:
            hygiene._TOTALS[key] = 0


def test_single_missing_data_does_not_quarantine_protected_symbol():
    reset_hygiene()
    hygiene._apply_failure("SPY", "no_data", "possibly delisted", "1d|5m", True)
    assert hygiene.is_blocked_symbol("SPY") is False
    assert "SPY" not in hygiene.status_payload(None)["active_symbol_backoffs"]


def test_missing_data_only_receives_short_retry_backoff_after_repeats():
    reset_hygiene()
    hygiene._apply_failure("TESTX", "missing_or_empty", "possibly delisted")
    hygiene._apply_failure("TESTX", "missing_or_empty", "possibly delisted")
    assert hygiene.is_blocked_symbol("TESTX") is False
    hygiene._apply_failure("TESTX", "missing_or_empty", "possibly delisted")
    assert hygiene.is_blocked_symbol("TESTX") is True
    payload = hygiene.status_payload(None)
    assert payload["active_symbol_backoffs"]["TESTX"]["seconds_remaining"] <= hygiene.FAILURE_BACKOFF_SECONDS


def test_success_clears_dynamic_backoff():
    reset_hygiene()
    for _ in range(3):
        hygiene._apply_failure("TESTX", "missing_or_empty", "possibly delisted")
    assert hygiene.is_blocked_symbol("TESTX") is True
    hygiene._clear_success(["TESTX"])
    assert hygiene.is_blocked_symbol("TESTX") is False


def test_stale_yfinance_error_is_removed_before_call():
    reset_hygiene()
    errors = {"SPY": "old possibly delisted"}
    fake_yf = SimpleNamespace(shared=SimpleNamespace(_ERRORS=errors))
    hygiene._clear_provider_errors(fake_yf, ["SPY"])
    assert errors == {}


def test_empty_responses_do_not_open_provider_wide_circuit():
    with resilience._LOCK:
        resilience._PROVIDER_FAILURES.clear()
        resilience._SYMBOL_STATE.clear()
        resilience._PROVIDER_CIRCUIT_OPEN_UNTIL = 0.0
        for key in resilience._TOTALS:
            resilience._TOTALS[key] = 0
    for symbol in ("A", "B", "C", "D", "E", "F"):
        resilience._register_failure([symbol], "empty", "empty")
    assert resilience._PROVIDER_CIRCUIT_OPEN_UNTIL == 0.0


def test_distinct_timeout_failures_can_open_provider_circuit():
    with resilience._LOCK:
        resilience._PROVIDER_FAILURES.clear()
        resilience._SYMBOL_STATE.clear()
        resilience._PROVIDER_CIRCUIT_OPEN_UNTIL = 0.0
    for symbol in ("A", "B", "C", "D", "A", "B"):
        resilience._register_failure([symbol], "timeout", "timed out")
    assert resilience._PROVIDER_CIRCUIT_OPEN_UNTIL > 0.0


def test_position_owned_price_prevents_cross_symbol_core_price():
    state = {
        "positions": {
            "CRWD": {
                "entry": 210.0,
                "entry_time": 1000,
                "last_price": 209.0,
                "side": "long",
                "shares": 1,
            }
        }
    }
    mod = SimpleNamespace(local_ts_text=lambda: "2026-08-06 09:00:00", latest_price=lambda symbol: 9.95)
    for _ in range(3):
        path_capture.update_paths(state, mod)
    path = state["intratrade_path_capture"]["paths"]["CRWD"]
    assert path["current_price"] == 209.0
    assert path["low_since_entry"] == 209.0
    assert path["mae_pct"] > -1.0
    assert path["training_eligible"] is True


def test_implausible_legacy_path_is_quarantined_and_reset():
    state = {
        "positions": {"CRWD": {"entry": 210.0, "entry_time": 1000, "last_price": 209.0, "side": "long", "shares": 1}},
        "intratrade_path_capture": {
            "paths": {"CRWD": {"symbol": "CRWD", "side": "long", "entry_price": 210.0, "entry_time": 1000, "high_since_entry": 233.0, "low_since_entry": 9.95}}
        },
    }
    mod = SimpleNamespace(local_ts_text=lambda: "2026-08-06 09:00:00")
    path_capture.update_paths(state, mod)
    path = state["intratrade_path_capture"]["paths"]["CRWD"]
    assert path["low_since_entry"] == 209.0
    archive = state["intratrade_path_capture"]["closed_path_archive"]
    assert any(row.get("integrity_status") == "quarantined" for row in archive)


def test_symbol_only_ml_features_are_quarantined_without_exact_path():
    state = {
        "trades": [],
        "ml_phase2": {
            "dataset": [
                {"symbol": "CRWD", "side": "long", "mae_mfe_features": {"mae_pct": -95.0, "ml_feature_ready": True}}
            ]
        },
        "intratrade_path_capture": {"paths": {}, "closed_path_archive": []},
    }
    integration.integrate(state, None)
    row = state["ml_phase2"]["dataset"][0]
    assert row["mae_mfe_features"]["ml_feature_ready"] is False
    assert row["mae_mfe_quarantined"] is True


def test_exact_execution_path_can_enrich_trade():
    entry_time = 1000
    entry_price = 10.0
    path_id = f"AI|long|{entry_time}|{entry_price:.6f}"
    state = {
        "trades": [
            {"action": "entry", "symbol": "AI", "side": "long", "time": entry_time, "price": entry_price},
            {"action": "exit", "symbol": "AI", "side": "long", "time": 2000, "price": 10.2, "pnl_pct": 2.0},
        ],
        "ml_phase2": {"dataset": []},
        "intratrade_path_capture": {
            "paths": {},
            "closed_path_archive": [{
                "path_id": path_id,
                "symbol": "AI",
                "side": "long",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "current_price": 10.2,
                "high_since_entry": 10.3,
                "low_since_entry": 9.9,
                "mae_pct": -1.0,
                "mfe_pct": 3.0,
                "integrity_status": "valid",
                "training_eligible": True,
                "ml_feature_ready": True,
                "calculation_version": "test",
            }],
        },
    }
    original_refresh = integration._refresh_intratrade_paths
    integration._refresh_intratrade_paths = lambda state, mod=None: {"status": "ok"}
    try:
        integration.integrate(state, None)
    finally:
        integration._refresh_intratrade_paths = original_refresh
    exit_row = state["trades"][1]
    assert exit_row["mae_mfe_feature_enriched"] is True
    assert exit_row["mae_mfe_features"]["path_id"] == path_id
    assert exit_row["mae_mfe_features"]["ml_feature_ready"] is True
