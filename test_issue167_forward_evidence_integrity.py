from types import SimpleNamespace
import time
import unittest

import performance_audit_lab as lab


def _row(symbol="VZLA", side="long", entry=4.16):
    return {
        "captured_local": "2026-09-03 01:00:00 CDT",
        "captured_epoch": time.time() - 4000,
        "symbol": symbol,
        "side": side,
        "entry_price": entry,
        "actual_entered": False,
        "shadow_policy_acceptance": {"current_proxy": True, "balanced": True, "permissive": True},
        "outcomes": {},
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
    }


def _core(rows, price):
    return SimpleNamespace(
        portfolio={"positions": {}, "performance_audit_lab": {"forward_rows": rows}},
        latest_price=lambda symbol: price,
        local_ts_text=lambda: "2026-09-03 02:00:00 CDT",
    )


class ForwardEvidenceIntegrityTests(unittest.TestCase):
    def test_catastrophic_shadow_mark_cannot_poison_or_resolve_vzla_row(self):
        row = _row()
        lab._resolve_forward(_core([row], 456.30))
        self.assertEqual(row["mfe_pct"], 0.0)
        self.assertEqual(row["mae_pct"], 0.0)
        self.assertEqual(row["outcomes"], {})
        self.assertNotIn("last_mark_price", row)
        self.assertEqual(row["integrity_rejection_count"], 1)
        self.assertEqual(row["last_integrity_rejection"]["reason"], "catastrophic_forward_mark_outlier")
        self.assertGreater(row["last_integrity_rejection"]["price_to_entry_ratio"], 100)

    def test_valid_shadow_mark_updates_excursion_and_due_horizon(self):
        row = _row(entry=100.0)
        lab._resolve_forward(_core([row], 101.25))
        self.assertEqual(row["mfe_pct"], 1.25)
        self.assertEqual(row["mae_pct"], 0.0)
        self.assertEqual(row["last_mark_price"], 101.25)
        self.assertEqual(row["outcomes"]["one_hour"]["return_pct"], 1.25)

    def test_short_shadow_mark_uses_same_symmetric_source_envelope(self):
        row = _row(symbol="SHORT", side="short", entry=100.0)
        lab._resolve_forward(_core([row], 30.0))
        self.assertEqual(row["mfe_pct"], 0.0)
        self.assertEqual(row["outcomes"], {})
        self.assertEqual(row["last_integrity_rejection"]["price_to_entry_ratio"], 0.3)

    def test_legacy_contaminated_rows_are_excluded_without_rewrite(self):
        good = _row(symbol="GOOD", entry=100.0)
        good["mfe_pct"] = 2.0
        good["mae_pct"] = -1.0
        bad = _row(symbol="SRPT", entry=22.82)
        bad["mfe_pct"] = 6705.4559
        bad["mae_pct"] = -54.7765
        original = dict(bad)
        core = _core([good, bad], 100.0)

        summary = lab.forward_summary(core)

        self.assertEqual(summary["evidence_status"], "inconclusive")
        self.assertIs(summary["promotion_eligible"], False)
        self.assertEqual(summary["integrity"]["eligible_rows"], 1)
        self.assertEqual(summary["integrity"]["excluded_rows"], 1)
        self.assertEqual(summary["policy_summary"]["balanced"]["accepted_rows"], 1)
        self.assertEqual(summary["policy_summary"]["balanced"]["average_mfe_pct"], 2.0)
        self.assertEqual(summary["policy_summary"]["balanced"]["average_mae_pct"], -1.0)
        self.assertEqual(bad, original)
        self.assertIs(summary["recent_rows"][-1]["research_integrity"]["eligible"], False)


if __name__ == "__main__":
    unittest.main()
