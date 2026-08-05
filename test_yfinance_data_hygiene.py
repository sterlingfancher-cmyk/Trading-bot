from __future__ import annotations

import sys
from types import SimpleNamespace

import market_data_resilience as resilience
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


def test_canonical_provider_owner_filters_rgit_before_request(monkeypatch):
    _reset_hygiene(monkeypatch)
    cleaned, allowed, blocked = resilience._sanitize_symbol_request(["RGIT", "CIFR"])
    assert cleaned == ["CIFR"]
    assert allowed == ["CIFR"]
    assert blocked == [{"symbol": "RGIT", "reason": "known_no_data_symbol"}]


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


def test_provider_confirmed_no_data_creates_symbol_quarantine(monkeypatch):
    _reset_hygiene(monkeypatch)
    hygiene._apply_failure("TESTX", "no_data", "possibly delisted; no price data found")
    assert hygiene.is_blocked_symbol("TESTX") is True
    assert hygiene.blocked_reason("TESTX") == "provider_confirmed_no_data"


def test_timeout_backoff_is_symbol_specific(monkeypatch):
    _reset_hygiene(monkeypatch)
    hygiene._apply_failure("CIFR", "timeout", "curl: (28) resolving timed out")
    assert hygiene.is_blocked_symbol("CIFR") is False
    hygiene._apply_failure("CIFR", "timeout", "curl: (28) resolving timed out")
    assert hygiene.is_blocked_symbol("CIFR") is True
    assert hygiene.is_blocked_symbol("SPY") is False


def test_authority_contract_remains_observational(monkeypatch):
    _reset_hygiene(monkeypatch)
    payload = hygiene.status_payload(None)
    assert payload["authority"]["places_orders"] is False
    assert payload["authority"]["changes_strategy"] is False
    assert payload["authority"]["changes_hard_risk"] is False
    assert payload["execution_authority"] == "existing_rules_only"
    assert payload["ml_authority"] == "shadow_recommendation_only"
