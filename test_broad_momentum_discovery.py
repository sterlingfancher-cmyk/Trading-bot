import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("broad_momentum_discovery.py")
spec = importlib.util.spec_from_file_location("broad_momentum_discovery_tested", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_quote_normalization_and_liquidity_filter():
    quote = {
        "symbol": "TEST",
        "regularMarketPrice": 12.5,
        "regularMarketChangePercent": 6.0,
        "regularMarketVolume": 2_000_000,
        "averageDailyVolume3Month": 1_000_000,
        "marketCap": 750_000_000,
        "sector": "Technology",
    }
    row = module._normalize_quote(quote, "market_wide_momentum")
    assert row is not None
    assert row["symbol"] == "TEST"
    assert row["relative_volume"] == 2.0
    assert row["sector_proxy"] == "XLK"
    assert module._eligible(row) == (True, "liquid_market_wide_candidate")
    assert module._discovery_score(row) > 0


def test_universe_composition_prioritizes_positions_benchmarks_and_broad_movers():
    universe = module._compose_universe(
        positions=["HELD"],
        base=["BASE1", "BASE2", "BASE3"],
        broad=["MOVE1", "MOVE2", "BASE1"],
        cap=10,
        broad_cap=3,
        base_cap=2,
    )
    assert universe[:5] == ["SPY", "QQQ", "IWM", "DIA", "HELD"]
    assert universe.index("MOVE1") < universe.index("BASE2")
    assert len(universe) == len(set(universe))


def test_run_cycle_hook_changes_only_universe_before_existing_cycle(monkeypatch):
    class Core:
        UNIVERSE = ["BASE1", "BASE2"]
        SYMBOL_SECTOR = {}
        SYMBOL_BUCKET = {}
        BUCKET_CONFIG = {}
        portfolio = {"positions": {"HELD": {}}}

        def market_clock(self):
            return {"is_open": True}

        def local_ts_text(self):
            return "2026-08-04 12:00:00"

        def run_cycle(self, source="manual"):
            return {"source": source, "universe": list(self.UNIVERSE)}

    core = Core()
    payload = {
        "status": "ok",
        "selected_symbols": ["MOVE1", "MOVE2"],
        "candidates": [
            {"symbol": "MOVE1", "sector_proxy": "XLK"},
            {"symbol": "MOVE2", "sector_proxy": "XLI"},
        ],
    }
    monkeypatch.setattr(module, "discover", lambda *args, **kwargs: payload)
    result = module.apply(core)
    assert result["run_cycle_hook_active"] is True
    cycle = core.run_cycle(source="test")
    assert "MOVE1" in cycle["universe"]
    assert "HELD" in cycle["universe"]
    assert core.SYMBOL_BUCKET["MOVE1"] == "dynamic_momentum"
    assert core.SYMBOL_SECTOR["MOVE1"] == "XLK"
    assert cycle["source"] == "test"


def test_authority_contract_remains_rules_only():
    payload = module.status_payload(None, force=False)
    authority = payload["authority"]
    assert authority["places_orders"] is False
    assert authority["changes_entry_rules"] is False
    assert authority["changes_hard_risk"] is False
    assert authority["changes_sizing"] is False
    assert authority["changes_ml_authority"] is False
    assert authority["execution_authority"] == "existing_rules_only"
