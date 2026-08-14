import types

import paper_exit_price_integrity_guard as guard


def test_latest_price_uses_current_download_owner_after_installation():
    calls = []

    def original_latest(symbol):
        return None

    def download_v1(symbol, period="1d", interval="5m"):
        calls.append(("v1", symbol))
        return [100.0, 100.2, 99.9, 100.1, 100.0, 100.3, 100.2]

    def download_v2(symbol, period="1d", interval="5m"):
        calls.append(("v2", symbol))
        return [200.0, 200.2, 199.9, 200.1, 200.0, 200.3, 200.2]

    core = types.SimpleNamespace(
        latest_price=original_latest,
        download_prices=download_v1,
        price_series=lambda frame, column="Close": frame,
        _price_cache={"data": {}},
    )

    assert guard._wrap_latest_price(core) is True
    assert core.latest_price("TEST") == 100.2
    assert calls == [("v1", "TEST")]

    core.download_prices = download_v2
    core._price_cache["data"].clear()

    assert core.latest_price("TEST") == 200.2
    assert calls == [("v1", "TEST"), ("v2", "TEST")]
