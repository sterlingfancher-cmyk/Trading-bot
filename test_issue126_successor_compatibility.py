from __future__ import annotations

import copy
import types
import unittest
from unittest import mock

import clean_epoch_successor_compatibility as clean_compat
import verified_v2_successor_epoch_migration as v2_migration
import verified_v2_successor_epoch_migration_precondition_compatibility as v2_compat


class Issue126SuccessorCompatibilityTests(unittest.TestCase):
    @staticmethod
    def _v4_core(*, canonical_history_retained_immutably=True, released=False):
        return types.SimpleNamespace(portfolio={
            "accounting_epoch_id": clean_compat.ISSUE126_V4_EPOCH_ID,
            "paper_accounting_epoch": {
                "id": clean_compat.ISSUE126_V4_EPOCH_ID,
                "prior_epoch_id": clean_compat.ISSUE82_V3_EPOCH_ID,
                "historical_recovery_decision": clean_compat.ISSUE126_V4_DECISION,
                "historical_evidence_archived": True,
                "validation_hold": not released,
                "validation_released": released,
                "validation_release_status": "released" if released else "blocked",
                "canonical_history_retained_immutably": canonical_history_retained_immutably,
            },
        })

    def test_clean_epoch_compatibility_accepts_only_exact_v4_successor(self):
        core = self._v4_core()
        self.assertEqual(clean_compat._successor_epoch(core), clean_compat.ISSUE126_V4_EPOCH_ID)
        self.assertTrue(clean_compat._is_verified_successor(core))

        for field, bad in (
            ("prior_epoch_id", "wrong-prior"),
            ("historical_recovery_decision", "wrong-decision"),
            ("historical_evidence_archived", False),
            ("validation_hold", False),
        ):
            changed = copy.deepcopy(core.portfolio)
            changed["paper_accounting_epoch"][field] = bad
            if field == "validation_hold":
                changed["paper_accounting_epoch"]["validation_released"] = False
                changed["paper_accounting_epoch"]["validation_release_status"] = "blocked"
            self.assertFalse(clean_compat._is_verified_successor(types.SimpleNamespace(portfolio=changed)))

    def test_v2_migration_compatibility_treats_exact_v4_as_superseded_without_write(self):
        core = self._v4_core()
        self.assertTrue(v2_compat._exact_issue126_v4_successor(v2_migration, core))
        before = copy.deepcopy(core.portfolio)
        calls = {"original": 0}

        def original(runtime_core=None):
            calls["original"] += 1
            return {"status": "error", "overall": "fail", "reason": "should_not_run"}

        with mock.patch.object(v2_migration, "apply", original):
            v2_compat._install_migration_apply_compatibility(v2_migration)
            result = v2_migration.apply(core)

        self.assertEqual(result["status"], "superseded")
        self.assertEqual(result["active_epoch_id"], clean_compat.ISSUE126_V4_EPOCH_ID)
        self.assertEqual(calls["original"], 0)
        self.assertEqual(core.portfolio, before)
        self.assertFalse(result["writes_state"])

    def test_released_v4_remains_exact_successor_for_legacy_compatibility(self):
        core = self._v4_core(released=True)
        self.assertEqual(clean_compat._successor_epoch(core), clean_compat.ISSUE126_V4_EPOCH_ID)
        self.assertTrue(v2_compat._exact_issue126_v4_successor(v2_migration, core))

    def test_v2_migration_compatibility_fails_closed_on_v4_lineage_mismatch(self):
        core = self._v4_core(canonical_history_retained_immutably=False)
        self.assertFalse(v2_compat._exact_issue126_v4_successor(v2_migration, core))

    def test_compatibility_adds_no_trading_or_state_authority(self):
        authority = v2_compat.status_payload(None)["authority"]
        self.assertFalse(authority["writes_state"])
        self.assertFalse(authority["edits_or_deletes_canonical_rows"])
        self.assertFalse(authority["rewrites_current_day_peak"])
        self.assertFalse(authority["clears_hard_halt"])
        self.assertFalse(authority["places_orders"])
        self.assertFalse(authority["changes_strategy"])
        self.assertFalse(authority["changes_thresholds"])
        self.assertFalse(authority["changes_risk_or_sizing"])
        self.assertFalse(authority["changes_live_or_ml_authority"])


if __name__ == "__main__":
    unittest.main()
