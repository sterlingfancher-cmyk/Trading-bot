from __future__ import annotations

import unittest
from types import SimpleNamespace

import paper_accounting_integrity_guard as guard


class Core(SimpleNamespace):
    def local_ts_text(self):
        return "2026-08-07 10:37:15 CDT"

    def save_state(self, *args, **kwargs):
        self.saved = True


class PaperAccountingIntegrityTests(unittest.TestCase):
    def _core(self):
        pf = {
            "history": [10000.0],
            "cash": 10387.365768,
            "equity": 14008.61,
            "positions": {
                "QQQ": {
                    "symbol": "QQQ",
                    "qty": 5.0,
                    "shares": 5.0,
                    "entry": 180.0,
                    "entry_price": 720.0,
                    "last_price": 722.8,
                    "unrealized_pnl": 2713.32,
                }
            },
            "trades": [
                {"timestamp": "2026-08-07 09:30:00", "symbol": "QQQ", "side": "buy", "qty": 5.0, "price": 720.0},
            ],
            "performance": {"unrealized_pnl": 2713.32, "realized_pnl_today": 1331.21, "realized_pnl_total": 1295.29},
            "risk_controls": {"profit_guard_active": True, "profit_guard_reason": "day profit pause reached"},
        }
        return Core(portfolio=pf, saved=False)

    def test_reconstructs_cash_equity_and_basis_from_execution_ledger(self):
        core = self._core()
        rebuilt = guard.reconstruct_from_ledger(core.portfolio, core)
        self.assertTrue(rebuilt["coverage_complete"])
        self.assertAlmostEqual(rebuilt["cash"], 6400.0, places=2)
        self.assertAlmostEqual(rebuilt["equity"], 10014.0, places=2)
        self.assertAlmostEqual(rebuilt["unrealized_pnl"], 14.0, places=2)
        self.assertAlmostEqual(rebuilt["open_positions"]["QQQ"]["entry_price"], 720.0, places=2)

    def test_reconcile_repairs_bad_accounting_and_quarantines_profit_guard(self):
        core = self._core()
        result = guard.reconcile(core, persist=True)
        self.assertTrue(result["repaired"])
        self.assertAlmostEqual(core.portfolio["cash"], 6400.0, places=2)
        self.assertAlmostEqual(core.portfolio["equity"], 10014.0, places=2)
        self.assertAlmostEqual(core.portfolio["performance"]["unrealized_pnl"], 14.0, places=2)
        self.assertFalse(core.portfolio["risk_controls"]["profit_guard_active"])
        self.assertTrue(core.saved)

    def test_partial_ledger_does_not_repair(self):
        core = self._core()
        core.portfolio["trades"].append({"symbol": "QQQ", "side": "partial_sell", "qty": 1, "price": 723.0})
        result = guard.reconcile(core, persist=True)
        self.assertFalse(result["repaired"])
        self.assertEqual(result["overall"], "warn")
        self.assertAlmostEqual(core.portfolio["equity"], 14008.61, places=2)


if __name__ == "__main__":
    unittest.main()
