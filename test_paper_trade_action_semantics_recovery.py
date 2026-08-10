import types
import unittest

import paper_accounting_integrity_guard as accounting
import paper_ledger_economic_integrity as economics
import paper_trade_action_semantics_recovery as recovery


class TradeActionSemanticsRecoveryTests(unittest.TestCase):
    def setUp(self):
        accounting._trade_fields = recovery.action_first_trade_fields
        economics._trade_fields = recovery.action_first_trade_fields

    def _core(self, portfolio):
        return types.SimpleNamespace(
            portfolio=portfolio,
            local_ts_text=lambda: "2026-08-10 12:00:00 CDT",
        )

    def test_long_exit_is_sell_not_second_buy(self):
        row = {
            "action": "exit",
            "symbol": "MARA",
            "side": "long",
            "price": 10.0,
            "shares": 100.0,
        }
        symbol, event, qty, price, _ = recovery.action_first_trade_fields(row)
        self.assertEqual(symbol, "MARA")
        self.assertEqual(event, "sell")
        self.assertEqual(qty, 100.0)
        self.assertEqual(price, 10.0)

    def test_entry_partial_exit_full_exit_reconstructs_cleanly(self):
        pf = {
            "history": [10000.0],
            "trades": [
                {"action": "entry", "symbol": "AAPL", "side": "long", "shares": 10, "price": 100},
                {"action": "partial_exit", "symbol": "AAPL", "side": "long", "shares": 4, "price": 110},
                {"action": "exit", "symbol": "AAPL", "side": "long", "shares": 6, "price": 120},
            ],
            "positions": {},
            "cash": 10160.0,
            "equity": 10160.0,
        }
        rebuilt = accounting.reconstruct_from_ledger(pf, self._core(pf))
        self.assertTrue(rebuilt["coverage_complete"])
        self.assertAlmostEqual(rebuilt["cash"], 10160.0, places=4)
        self.assertAlmostEqual(rebuilt["equity"], 10160.0, places=4)
        self.assertAlmostEqual(rebuilt["realized_total"], 160.0, places=4)
        self.assertEqual(rebuilt["open_positions"], {})

        economic = economics.status_payload(self._core(pf))
        self.assertEqual(economic["overall"], "pass")
        self.assertTrue(economic["promotion_evidence_eligible"])
        self.assertAlmostEqual(economic["reconstructed_cash_after_ledger"], 10160.0, places=4)

    def test_short_lifecycle_is_not_silently_reconstructed_by_long_lot_model(self):
        pf = {
            "history": [10000.0],
            "trades": [
                {"action": "entry", "symbol": "XYZ", "side": "short", "shares": 10, "price": 100},
                {"action": "exit", "symbol": "XYZ", "side": "short", "shares": 10, "price": 90},
            ],
            "positions": {},
        }
        rebuilt = accounting.reconstruct_from_ledger(pf, self._core(pf))
        self.assertFalse(rebuilt["coverage_complete"])
        economic = economics.status_payload(self._core(pf))
        self.assertEqual(economic["overall"], "fail")
        self.assertFalse(economic["promotion_evidence_eligible"])


if __name__ == "__main__":
    unittest.main()
