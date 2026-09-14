from __future__ import annotations

import copy
import unittest

import paper_accounting_integrity_guard as accounting


REBUILT = {
    "coverage_complete": True,
    "cash": 12708.218885,
    "equity": 13394.151144,
    "market_value": 685.932259,
    "unrealized_pnl": 13.654189,
    "open_positions": {
        "ORCL": {
            "qty": 4.383374,
            "entry_price": 153.37,
            "last_price": 150.255005,
            "market_value": 685.932259,
            "unrealized_pnl": 13.654189,
        }
    },
}


def _portfolio():
    return {
        "cash": 12708.21877,
        "equity": 13394.15,
        "positions": {
            "ORCL": {
                "entry": 153.369995,
                "last_price": 150.255005,
                "shares": 4.383375,
                "side": "short",
            }
        },
        "performance": {"unrealized_pnl": 13.65},
    }


class OptionalPositionUnrealizedTests(unittest.TestCase):
    def test_absent_optional_position_pnl_is_not_coerced_to_zero(self):
        self.assertEqual(accounting._discrepancies(_portfolio(), REBUILT), [])

    def test_present_stale_position_pnl_alias_remains_visible(self):
        portfolio = _portfolio()
        portfolio["positions"]["ORCL"]["unrealized_pnl"] = 0.0

        self.assertEqual(accounting._discrepancies(portfolio, REBUILT), [
            {
                "field": "positions.ORCL.unrealized_pnl",
                "stored": 0.0,
                "expected": 13.6542,
            }
        ])

    def test_present_stale_aggregate_pnl_remains_visible_without_position_alias(self):
        portfolio = _portfolio()
        portfolio["performance"]["unrealized_pnl"] = 0.0

        self.assertEqual(accounting._discrepancies(portfolio, REBUILT), [
            {
                "field": "performance.unrealized_pnl",
                "stored": 0.0,
                "expected": 13.6542,
            }
        ])

    def test_present_correct_position_and_aggregate_pnl_pass(self):
        portfolio = _portfolio()
        portfolio["positions"]["ORCL"]["pnl_dollars"] = 13.65

        self.assertEqual(accounting._discrepancies(copy.deepcopy(portfolio), REBUILT), [])


if __name__ == "__main__":
    unittest.main()
