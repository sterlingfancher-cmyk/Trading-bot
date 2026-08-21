from __future__ import annotations

import unittest

import runtime_research_snapshot as snapshot


class RuntimeResearchSnapshotTests(unittest.TestCase):
    def _raw(self, recovery_overall="pass"):
        raw = {
            name: {"status": "ok", "payload": {}}
            for name in snapshot.ENDPOINTS
        }
        raw["bootstrap_status"]["payload"] = {
            "status": "ready",
            "delegate_ready": True,
        }
        raw["root"]["payload"] = {"status": "ok", "delegate_ready": True}
        raw["paper_status"]["payload"] = {"status": "ok"}
        raw["self_check"]["payload"] = {
            "overall": "pass",
            "version": "self-check-test",
            "summary": {"components_checked": 9, "failing_components": []},
            "account": {"cash": 100.0, "equity": 101.0, "positions": []},
            "auto_runner": {"last_success": "now"},
        }
        raw["verified_v2_recovery_gate"]["payload"] = {
            "overall": recovery_overall,
            "version": "gate-test",
            "diagnosis": (
                "verified_v2_consolidated_recovery_gate_mechanically_complete"
                if recovery_overall == "pass"
                else "known_invalid_execution_signature_not_exact_recovery_gate_blocked"
            ),
            "known_invalid_execution_count": 5,
            "all_known_invalid_signatures_exact": recovery_overall == "pass",
            "latest_invalid_is_last_canonical_execution": True,
            "ledger": {"row_count": 39, "chain_valid": True},
            "projection": {
                "projection_complete": recovery_overall == "pass",
                "candidate_cash": 12759.65,
            },
            "state_comparison": {
                "candidate_equity_using_current_stored_marks": 13178.63,
                "unexplained_position_mismatches": [],
            },
            "recovery_readiness": {
                "mechanically_complete_for_successor_migration_design": recovery_overall == "pass",
                "manual_per_event_probe_required": False,
                "state_write_authorized_by_this_probe": False,
                "halt_clear_authorized_by_this_probe": False,
                "risk_peak_repair_authorized_by_this_probe": False,
            },
        }
        raw["v2_status"]["payload"] = {"run_status": "idle"}
        return raw

    def test_authoritative_default_and_recovery_gate_endpoint_are_canonical(self):
        self.assertEqual(
            snapshot.DEFAULT_BASE_URL,
            "https://web-production-e1796.up.railway.app",
        )
        self.assertEqual(
            snapshot.ENDPOINTS["verified_v2_recovery_gate"],
            "/paper/verified-v2-successor-replay-status",
        )

    def test_recovery_gate_is_compacted_into_automatic_runtime_summary(self):
        summary = snapshot._summarize(self._raw("pass"))

        self.assertEqual(summary["overall"], "pass")
        gate = summary["recovery_gate"]
        self.assertEqual(gate["overall"], "pass")
        self.assertEqual(gate["ledger_row_count"], 39)
        self.assertEqual(gate["known_invalid_execution_count"], 5)
        self.assertTrue(gate["all_known_invalid_signatures_exact"])
        self.assertTrue(gate["mechanically_complete_for_successor_migration_design"])
        self.assertFalse(gate["manual_per_event_probe_required"])
        self.assertFalse(gate["state_write_authorized_by_probe"])
        self.assertFalse(gate["halt_clear_authorized_by_probe"])
        self.assertFalse(gate["risk_peak_repair_authorized_by_probe"])

    def test_failed_recovery_gate_warns_snapshot_without_mutation_or_error_exit_class(self):
        summary = snapshot._summarize(self._raw("fail"))

        self.assertEqual(summary["overall"], "warn")
        gate = summary["recovery_gate"]
        self.assertEqual(gate["overall"], "fail")
        self.assertFalse(gate["mechanically_complete_for_successor_migration_design"])
        self.assertFalse(gate["manual_per_event_probe_required"])


if __name__ == "__main__":
    unittest.main()
