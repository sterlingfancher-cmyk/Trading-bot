import copy
import unittest

import pandas as pd

import multi_asset_shadow_ranker as ranker


class FakeCore:
    def __init__(self):
        self.calls = []
        self.portfolio = {
            "auto_runner": {
                "last_result": {
                    "market_mode": "risk_on",
                    "regime": "bull",
                    "risk_score": 78,
                    "cycle_id": "cycle-test-1",
                    "entries": [
                        {"symbol": "AMD", "score": 0.041, "side": "long", "sector": "XLK"}
                    ],
                    "blocked_entries": [
                        {"symbol": "QQQ", "score": 0.032, "side": "long", "reason": "profit_guard"}
                    ],
                    "rejected_signals": [
                        {"symbol": "AAPL", "score": 0.015, "side": "long", "reason": "extended"}
                    ],
                    "long_signals": ["AMD", "QQQ", "AAPL"],
                    "short_signals": [],
                }
            }
        }

    def download_prices(self, symbol, period="30d", interval="1h"):
        self.calls.append((symbol, period, interval))
        base = {"BTC-USD": 60000.0, "ETH-USD": 3000.0, "SOL-USD": 150.0}[symbol]
        closes = [base * (1.0 + i * 0.0005) for i in range(120)]
        return pd.DataFrame({"Close": closes})


class MultiAssetShadowRankerTests(unittest.TestCase):
    def setUp(self):
        ranker._LAST = {}

    def test_status_and_apply_do_not_call_provider(self):
        core = FakeCore()
        before = copy.deepcopy(core.portfolio)
        payload = ranker.apply(core)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(core.calls, [])
        self.assertEqual(core.portfolio, before)
        self.assertFalse(payload["authority"]["places_orders"])
        self.assertFalse(payload["authority"]["feeds_execution_candidates"])

    def test_refresh_combines_scanner_and_bounded_crypto(self):
        core = FakeCore()
        before = copy.deepcopy(core.portfolio)
        payload = ranker.refresh(core)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(core.calls), 3)
        self.assertEqual({call[0] for call in core.calls}, set(ranker.CRYPTO_SYMBOLS))
        self.assertEqual(core.portfolio, before)
        classes = {row["asset_class"] for row in payload["rows"]}
        self.assertIn("equity", classes)
        self.assertIn("etf", classes)
        self.assertIn("crypto", classes)
        self.assertEqual(payload["external_provider_calls"], 3)
        self.assertTrue(all(row.get("execution_authority") is False for row in payload["rows"]))

    def test_second_refresh_hits_cache(self):
        core = FakeCore()
        first = ranker.refresh(core)
        second = ranker.refresh(core)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(core.calls), 3)


if __name__ == "__main__":
    unittest.main()
