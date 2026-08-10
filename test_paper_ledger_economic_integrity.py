import types
import unittest

import paper_ledger_economic_integrity as econ


class EconomicLedgerIntegrityTests(unittest.TestCase):
    def _core(self, portfolio):
        return types.SimpleNamespace(portfolio=portfolio, local_ts_text=lambda: "2026-08-10 10:15:00 CDT")

    def test_clean_cash_only_ledger_passes(self):
        pf = {
            "initial_cash": 10000.0,
            "history": [10000.0],
            "trades": [
                {"symbol": "AAPL", "side": "buy", "qty": 10, "price": 100},
                {"symbol": "AAPL", "side": "sell", "qty": 10, "price": 105},
            ],
        }
        result = econ.status_payload(self._core(pf))
        self.assertEqual(result["overall"], "pass")
        self.assertTrue(result["promotion_evidence_eligible"])

    def test_oversized_buy_fails(self):
        pf = {
            "initial_cash": 10000.0,
            "history": [10000.0],
            "trades": [
                {"symbol": "MARA", "side": "buy", "qty": 10833.6864, "price": 9.87541484375, "source": "regression"},
            ],
        }
        result = econ.status_payload(self._core(pf))
        self.assertEqual(result["overall"], "fail")
        self.assertFalse(result["promotion_evidence_eligible"])
        reasons = [row["reason"] for row in result["economic_issues"]]
        self.assertIn("buy_exceeds_available_cash", reasons)
        self.assertIn("negative_cash_after_trade", reasons)

    def test_baseline_disagreement_fails(self):
        pf = {
            "initial_cash": 14000.0,
            "history": [10000.0],
            "trades": [{"symbol": "AAPL", "side": "buy", "qty": 1, "price": 100}],
        }
        result = econ.status_payload(self._core(pf))
        self.assertEqual(result["overall"], "fail")
        self.assertIn("baseline_provenance_disagreement", [row["reason"] for row in result["economic_issues"]])


if __name__ == "__main__":
    unittest.main()
