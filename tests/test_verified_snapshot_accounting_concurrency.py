import pytest

import verified_snapshot_accounting_baseline as vsab


class NonCopyableTelemetry:
    """An object that will raise if someone attempts to deepcopy it.

    This simulates threaded scanner/telemetry objects that caused production
    tracebacks when the old code attempted to deep-copy the entire live
    portfolio.
    """

    def __deepcopy__(self, memo):  # pragma: no cover - exercised in test
        raise RuntimeError("deepcopy_not_allowed_on_telemetry")


class FakeCore:
    def __init__(self):
        # portfolio includes a mix of safe accounting fields and a heavy
        # telemetry object that must not be traversed/deepcopied.
        self.portfolio = {
            "cash": 10000.0,
            "equity": 10000.0,
            "trades": [{"id": "t1", "symbol": "ABC", "qty": 10}],
            "positions": {"ABC": {"qty": 10, "avg_price": 10.0}},
            "prices": {"ABC": {"last_price": 10.0}},
            # Non-copyable telemetry (scanner, research, or provider pool)
            "scanner": NonCopyableTelemetry(),
            "telemetry_lock": NonCopyableTelemetry(),
        }

    def load_state(self):
        # Emulate a state loader returning a similar structure; tests expect
        # the function to prefer self.portfolio and not attempt to deepcopy
        # the non-copyable telemetry.
        return self.portfolio


def test_build_accounting_view_does_not_deepcopy_telemetry():
    core = FakeCore()

    # The call must succeed without raising a deepcopy-related exception.
    view = vsab.build_accounting_view(core)

    # Basic sanity checks on the returned, detached accounting view.
    assert isinstance(view, dict)
    assert view["scalars"]["cash"] == 10000.0
    assert view["scalars"]["equity"] == 10000.0
    assert isinstance(view["trades"], list)
    assert view["positions"]["ABC"]["qty"] == 10

    # Ensure telemetry keys did not leak into the accounting-only view.
    assert "scanner" not in view
    assert "telemetry_lock" not in view
