from __future__ import annotations

import sys
from types import SimpleNamespace

import market_data_request_gate as request_gate
import yfinance_data_hygiene as hygiene


def _reset_hygiene(monkeypatch):
    monkeypatch.delenv("YFINANCE_KNOWN_NO_DATA_SYMBOLS", raising=False)
    with hygiene._LOCK:
        hygiene._SYMBOL_STATE.clear()
        hygiene._CACHE.clear()
        for key in hygiene._TOTALS:
            hygiene._TOTALS[key] = 0


def test_rgit_is_blocked_but_cifr_is_allowed(monkeypatch):
    _reset_hygiene(monkeypatch)
    cleaned, allowed, blocked = hygiene.sanitize_tickers(["RGIT", "CIFR"])
    assert cleaned == ["CIFR"]
    assert allowed == ["CIFR"]
    assert blocked == [{"symbol": "RGIT", "reason": "known_no_data_symbol"}]


def test_no_silent_rgit_to_rgti_translation(monkeypatch):
    _reset_hygiene(monkeypatch)
    cleaned, allowed, blocked = hygiene.sanitize_tickers("RGIT")
    assert cleaned == ""
    assert allowed == []
    assert blocked[0]["symbol"] == "RGIT"
    assert "RGTI" not in allowed


def test_broad_discovery_symbol_normalizer_rejects_rgit(monkeypatch):
    _reset_hygiene(monkeypatch)
    fake_broad = SimpleNamespace(
        _symbol=lambda value: str(value).upper().strip(),
        _CACHE={"ts": 123.0, "payload": {"selected_symbols": ["RGIT", "CIFR"]}},
    )
    monkeypatch.setitem(sys.modules, "broad_momentum_discovery", fake_broad)
    core = SimpleNamespace(UNIVERSE=["SPY", "RGIT", "CIFR"])

    hygiene._patch_runtime_sources(core)

    assert core.UNIVERSE == ["SPY", "CIFR"]
    assert fake_broad._symbol("RGIT") == ""
    assert fake_broad._symbol("CIFR") == "CIFR"
    assert fake_broad._CACHE == {"ts": 0.0, "payload": None}


def test_request_gate_skips_blocked_symbol_before_prior_helper(monkeypatch):
    _reset_hygiene(monkeypatch)
    calls = []

    def prior(symbol, period="5d", interval="5m"):
        calls.append((symbol, period, interval))
        return "provider-result"

    core = SimpleNamespace(download_prices=prior, local_ts_text=lambda: "2026-08-05 13:30:00")
    request_gate.install(core)

    assert core.download_prices("RGIT") is None
    assert calls == []
    assert core.download_prices("CIFR") == "provider-result"
    assert calls == [("CIFR", "5d", "5m")]


def test_request_gate_rebinds_after_underlying_helper_changes(monkeypatch):
    _reset_hygiene(monkeypatch)
    first_calls = []
    second_calls = []

    def first(symbol, period="5d", interval="5m"):
        first_calls.append(symbol)
        return "first"

    def second(symbol, period="5d", interval="5m"):
        second_calls.append(symbol)
        return "second"

    core = SimpleNamespace(download_prices=first, local_ts_text=lambda: "2026-08-05 13:30:00")
    request_gate.install(core)
    assert getattr(core.download_prices, "_market_data_request_gate_version", None) == request_gate.VERSION

    core.download_prices = second
    request_gate.install(core)

    assert getattr(core.download_prices, "_market_data_request_gate_version", None) == request_gate.VERSION
    assert core.download_prices("RGIT") is None
    assert second_calls == []
    assert core.download_prices("CIFR") == "second"
    assert second_calls == ["CIFR"]
    assert first_calls == []


def test_authority_contract_remains_observational(monkeypatch):
    _reset_hygiene(monkeypatch)
    payload = hygiene.status_payload(None)
    assert payload["authority"]["places_orders"] is False
    assert payload["authority"]["changes_strategy"] is False
    assert payload["authority"]["changes_hard_risk"] is False
    assert payload["execution_authority"] == "existing_rules_only"
    assert payload["ml_authority"] == "shadow_recommendation_only"
