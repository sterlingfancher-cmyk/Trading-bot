import unittest

import orla_hygiene_overlay
import yfinance_data_hygiene as hygiene


class OrlaHygieneTests(unittest.TestCase):
    def test_orla_is_static_blocked_after_apply(self):
        orla_hygiene_overlay.apply(None)
        self.assertIn("ORLA", hygiene.static_blocked_symbols())
        cleaned, allowed, blocked = hygiene.sanitize_tickers(["ORLA", "SPY"])
        self.assertIn("SPY", allowed)
        self.assertNotIn("ORLA", allowed)
        self.assertTrue(any(row.get("symbol") == "ORLA" for row in blocked))


if __name__ == "__main__":
    unittest.main()
