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
    assert row["sources"] == ["market_wide_momentum"]
    assert module._eligible(row) == (True, "liquid_market_wide_candidate")
    assert module._discovery_score(row) > 0


def test_source_labels_survive_deduplication_and_receive_confirmation_bonus(monkeypatch):
    quote_a = {
        "symbol": "DUPE",
        "regularMarketPrice": 10.0,
        "regularMarketChangePercent": 5.0,
        "regularMarketVolume": 1_000_000,
        "averageDailyVolume3Month": 500_000,
        "marketCap": 750_000_000,
    }
    quote_b = dict(quote_a, regularMarketPrice=10.1, regularMarketVolume=1_200_000)
    monkeypatch.setattr(
        module,
        "_screen_calls",
        lambda: [
            ("day_gainers", {"quotes": [quote_a]}),
            ("market_wide_momentum", {"quotes": [quote_b]}),
        ],
    )
    payload = module._build_payload(None)
    row = payload["candidates"][0]
    assert row["sources"] == ["day_gainers", "market_wide_momentum"]
    assert row["source_confirmation_bonus"] == 0.02


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


def test_run_cycle_and_scanner_boundary_enforce_final_cap(monkeypatch):
    class Core:
        UNIVERSE = [f"BASE{i}" for i in range(80)] + [f"EXTRA{i}" for i in range(80)]
        SYMBOL_SECTOR = {}
        SYMBOL_BUCKET = {}
        BUCKET_CONFIG = {}
        portfolio = {"positions": {"HELD": {}}}

        def market_clock(self):
            return {"is_open": True}

        def local_ts_text(self):
            return "2026-08-05 10:00:00"

        def scan_signals(self):
            return list(self.UNIVERSE)

        def run_cycle(self, source="manual"):
            return {"source": source, "universe": self.scan_signals()}

    core = Core()
    payload = {
        "status": "ok",
        "selected_symbols": [f"MOVE{i}" for i in range(100)],
        "candidates": [
            {"symbol": f"MOVE{i}", "sector_proxy": "XLK", "sources": ["market_wide_momentum"]}
            for i in range(100)
        ],
        "source_counts": {},
        "source_errors": {},
        "eligible_unique_count": 100,
    }
    monkeypatch.setattr(module, "discover", lambda *args, **kwargs: payload)
    monkeypatch.setattr(module, "_schedule_sector_enrichment", lambda *args, **kwargs: None)
    result = module.apply(core)
    assert result["run_cycle_hook_active"] is True
    assert result["scan_boundary_hook_active"] is True
    cycle = core.run_cycle(source="test")
    assert len(cycle["universe"]) <= module.MAX_FINAL_UNIVERSE
    assert len(core.UNIVERSE) <= module.MAX_FINAL_UNIVERSE
    boundary = core.portfolio["broad_momentum_discovery"]
    assert boundary["within_policy_cap"] is True
    assert boundary["post_boundary_universe_count"] <= module.MAX_FINAL_UNIVERSE
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
