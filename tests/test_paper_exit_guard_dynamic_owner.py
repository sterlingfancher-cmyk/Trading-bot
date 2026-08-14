import types

import pytest

import paper_exit_price_integrity_guard as guard


class DummyCore:
    pass


def test_latest_price_uses_current_download_owner_after_install_and_cache_clear():
    core = DummyCore()

    calls = []

    def download_v1(symbol):
        calls.append(("v1", symbol))
        return 1.23

    def download_v2(symbol):
        calls.append(("v2", symbol))
        return 4.56

    # Install initial download_prices implementation
    core.download_prices = download_v1

    # Install the guard wrapper (this must NOT capture download_v1 for future fetches)
    wrapper = guard._wrap_latest_price(core, ttl_seconds=60)

    # Assign back as core.latest_price to emulate real installation
    core.latest_price = wrapper

    # First call should use download_v1
    p1 = core.latest_price("FOO")
    assert p1 == 1.23
    assert calls == [("v1", "FOO")]

    # Replace the core.download_prices implementation to emulate market_data_resilience
    core.download_prices = download_v2

    # Force an uncached fetch by clearing the wrapper cache for the symbol
    # (production behavior uses a 60s TTL; test forces refresh deterministically)
    core.latest_price.clear_cache("FOO")

    # Next call should use download_v2, proving the wrapper resolved the
    # current owner at fetch time rather than calling a previously-captured
    # reference.
    p2 = core.latest_price("FOO")
    assert p2 == 4.56
    # The call list should show both versions were invoked in order
    assert calls == [("v1", "FOO"), ("v2", "FOO")]

