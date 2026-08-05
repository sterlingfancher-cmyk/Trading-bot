from __future__ import annotations

import sys
from types import SimpleNamespace

import scanner_runtime_contract as contract


def test_canonical_scanner_owner_applies_broad_boundary_before_delegate(monkeypatch):
    calls = []

    class Core:
        portfolio = {"positions": {}}
        UNIVERSE = [f"OLD{i}" for i in range(150)]

        def local_ts_text(self):
            return "2026-08-05 10:30:00"

        def scan_signals(self, market=None):
            calls.append(("delegate", len(self.UNIVERSE)))
            return list(self.UNIVERSE)

    core = Core()

    def enforce(runtime):
        calls.append(("boundary", len(runtime.UNIVERSE)))
        runtime.UNIVERSE = runtime.UNIVERSE[:110]
        return {"post_boundary_universe_count": len(runtime.UNIVERSE), "within_policy_cap": True}

    fake_broad = SimpleNamespace(
        VERSION="broad-momentum-discovery-2026-08-05-v2.1-ownership-safe",
        enforce_scanner_boundary=enforce,
    )
    monkeypatch.setitem(sys.modules, "broad_momentum_discovery", fake_broad)

    assert contract._patch_universe_boundary(core) is True
    result = core.scan_signals({})
    assert calls[0][0] == "boundary"
    assert calls[1] == ("delegate", 110)
    assert len(result) == 110
    assert core.SCANNER_UNIVERSE_BOUNDARY_VERSION == fake_broad.VERSION

    inspection = contract._inspect(core.scan_signals)
    assert inspection["universe_boundary_count"] == 1
    assert inspection["opening_surge_count"] == 0
    assert inspection["cycle_detected"] is False
    assert inspection["current"]["universe_boundary"] is True
    assert inspection["current"]["opening_surge"] is False


def test_boundary_does_not_inherit_opening_surge_markers(monkeypatch):
    def base_scan(market=None):
        return ["SPY", "QQQ"]

    class Core:
        portfolio = {"positions": {}}
        UNIVERSE = [f"OLD{i}" for i in range(125)]

        def local_ts_text(self):
            return "2026-08-05 10:35:00"

        def scan_signals(self, market=None):
            return base_scan(market)

    Core.scan_signals._opening_surge_scan_guard = True
    Core.scan_signals._opening_surge_scan_prior = base_scan
    core = Core()

    fake_broad = SimpleNamespace(
        VERSION="broad-momentum-discovery-2026-08-05-v2.1-ownership-safe",
        enforce_scanner_boundary=lambda runtime: {
            "post_boundary_universe_count": len(runtime.UNIVERSE),
            "within_policy_cap": True,
        },
    )
    monkeypatch.setitem(sys.modules, "broad_momentum_discovery", fake_broad)

    assert contract._patch_universe_boundary(core) is True
    inspection = contract._inspect(core.scan_signals)
    assert inspection["universe_boundary_count"] == 1
    assert inspection["opening_surge_count"] == 1
    assert inspection["universe_boundary_depth"] == 0
    assert inspection["opening_surge_depth"] == 1
    assert inspection["universe_boundary_ordered"] is True
    assert inspection["cycle_detected"] is False
    assert inspection["current"]["opening_surge"] is False


def test_boundary_fallback_preserves_existing_scanner_when_discovery_errors(monkeypatch):
    class Core:
        portfolio = {}
        UNIVERSE = ["SPY", "QQQ"]

        def scan_signals(self, market=None):
            return list(self.UNIVERSE)

    fake_broad = SimpleNamespace(
        VERSION="test-version",
        enforce_scanner_boundary=lambda core: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    monkeypatch.setitem(sys.modules, "broad_momentum_discovery", fake_broad)
    core = Core()
    assert contract._patch_universe_boundary(core) is True
    assert core.scan_signals({}) == ["SPY", "QQQ"]


def test_scanner_boundary_changes_no_trade_authority():
    class Core:
        portfolio = {"auto_runner": {}}

        def scan_signals(self, market=None):
            return [], [], []

    core = Core()
    inspection = contract._inspect(core.scan_signals, core)
    assert inspection["universe_boundary_count"] == 0
