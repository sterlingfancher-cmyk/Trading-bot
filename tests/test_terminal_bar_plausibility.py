from __future__ import annotations

import math
import time
import importlib

import pytest

import app
import market_data_resilience


@pytest.fixture(autouse=True)
def ensure_fresh_install(monkeypatch):
    # Because install() is idempotent, force a fresh environment by deleting
    # any existing installation attributes on the app module between tests.
    for attr in ["_terminal_plausibility_installed", "_plausible_price_cache"]:
        if hasattr(app, attr):
            try:
                delattr(app, attr)
            except Exception:
                try:
                    delattr(app, attr)
                except Exception:
                    pass
    # Re-import to ensure deterministic state
    importlib.reload(market_data_resilience)
    yield


def _make_download_prices_returns(prior_value: float, n_prior: int, last_value):
    prior = [float(prior_value)] * int(n_prior)
    return {"Close": prior + [float(last_value)]}


def test_reject_catastrophic_terminal_bar_not_cached(monkeypatch):
    # Simulate 300 prior bars ~312.90 and a catastrophic terminal tick 18.401199340820312
    bad_last = 18.401199340820312
    prior_val = 312.9
    df_like = _make_download_prices_returns(prior_val, 300, bad_last)

    def fake_download(symbol, *args, **kwargs):
        return df_like

    monkeypatch.setattr(app, "download_prices", fake_download, raising=False)

    # Install the wrapper which will patch app.latest_price
    market_data_resilience.install(app)

    # Call latest_price; wrapper should reject catastrophic terminal bar and return None
    out = app.latest_price("LRCX")
    assert out is None

    # And the internal plausible cache should not contain a positive price entry
    cache = getattr(app, "_plausible_price_cache", {})
    assert "LRCX" not in cache or cache.get("LRCX", {}).get("price") is None


def test_accept_plausible_terminal_bar_and_cache(monkeypatch):
    # Simulate 300 prior bars ~312.90 and a plausible terminal tick ~315.0
    plausible_last = 315.0
    prior_val = 312.9
    df_like = _make_download_prices_returns(prior_val, 300, plausible_last)

    def fake_download(symbol, *args, **kwargs):
        return df_like

    monkeypatch.setattr(app, "download_prices", fake_download, raising=False)

    market_data_resilience.install(app)

    out = app.latest_price("LRCX")
    assert out is not None
    assert isinstance(out, float)
    assert math.isclose(out, float(plausible_last), rel_tol=1e-9)

    # And the internal plausible cache must contain the symbol with a recent ts
    cache = getattr(app, "_plausible_price_cache", {})
    assert "LRCX" in cache
    entry = cache["LRCX"]
    assert entry.get("price") == float(plausible_last)
    assert (time.time() - entry.get("ts", 0)) < 5
