from __future__ import annotations

import unittest

import runtime_research_snapshot as snapshot


class RuntimeResearchSnapshotTests(unittest.TestCase):
    def _raw(
        self,
        recovery_overall="pass",
        fresh_baseline_status="pass",
        audit_overall="pass",
        epoch_id="stable-paper-v2-20260812-verified01",
    ):
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
        raw["fresh_day_check"]["payload"] = {
            "overall": "pass" if fresh_baseline_status == "pass" else "fail",
            "baseline_status": fresh_baseline_status,
            "date": "2026-08-24",
            "current_equity": 101.0,
            "day_start_equity": 100.0,
            "day_peak_equity": 101.0,
            "fresh_day_reset_pending": False,
            "halted": False,
            "halt_reason": None,
            "intraday_drawdown_pct": 0.0,
        }
        raw["daily_audit"]["payload"] = {
            "overall": audit_overall,
            "generated_local": "2026-08-24 10:30:00 CDT",
            "accounting_epoch": {
                "epoch_id": epoch_id,
                "validation_hold": True,
            },
            "accounting_integrity": {
                "status": "pass" if audit_overall == "pass" else "warn",
                "coverage_issue_count": 0 if audit_overall == "pass" else 1,
                "economic_issue_count": 0 if audit_overall == "pass" else 1,
            },
            "execution_ledger": {
                "chain_valid": True,
                "row_count": 39,
                "current_epoch_id": epoch_id,
            },
            "market_data": {"status": "pass"},
            "runner": {
                "status": "pass",
                "active_error": False,
                "last_successful_run": "2026-08-24 10:25:00 CDT",
            },
            "risk": {
                "status": "pass",
                "halted": False,
                "halt_reason": None,
                "intraday_drawdown_pct": 0.0,
            },
        }
        raw["verified_v2_recovery_gate"]["payload"] = {
            "overall": recovery_overall,
            "version": "gate-test",
            "diagnosis": (
                "verified_v2_consolidated_recovery_gate_mechanically_complete"
                if recovery_overall == "pass"
                else "known_invalid_execution_signature_not_exact_recovery_gate_blocked"
            ),
            "known_invalid_execution_count": 7,
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

    def test_authoritative_default_and_stabilization_endpoints_are_canonical(self):
        self.assertEqual(
            snapshot.DEFAULT_BASE_URL,
            "https://web-production-e1796.up.railway.app",
        )
        self.assertEqual(
            snapshot.ENDPOINTS["verified_v2_recovery_gate"],
            "/paper/verified-v2-successor-replay-status",
        )
        self.assertEqual(
            snapshot.ENDPOINTS["fresh_day_check"],
            "/paper/fresh-day-check",
        )
        self.assertEqual(
            snapshot.ENDPOINTS["daily_audit"],
            "/paper/daily-audit",
        )

    def test_recovery_fresh_day_and_active_audit_are_compacted_together(self):
        summary = snapshot._summarize(self._raw())

        self.assertEqual(summary["overall"], "pass")
        gate = summary["recovery_gate"]
        self.assertEqual(gate["overall"], "pass")
        self.assertTrue(gate["classification_applicable"])
        self.assertEqual(gate["ledger_row_count"], 39)
        self.assertEqual(gate["known_invalid_execution_count"], 7)
        self.assertTrue(gate["all_known_invalid_signatures_exact"])
        self.assertTrue(gate["mechanically_complete_for_successor_migration_design"])
        self.assertFalse(gate["manual_per_event_probe_required"])
        self.assertFalse(gate["state_write_authorized_by_probe"])
        self.assertFalse(gate["halt_clear_authorized_by_probe"])
        self.assertFalse(gate["risk_peak_repair_authorized_by_probe"])

        fresh = summary["fresh_day"]
        self.assertEqual(fresh["baseline_status"], "pass")
        self.assertEqual(fresh["date"], "2026-08-24")
        self.assertEqual(fresh["day_start_equity"], 100.0)
        self.assertEqual(fresh["day_peak_equity"], 101.0)
        self.assertFalse(fresh["fresh_day_reset_pending"])
        self.assertFalse(fresh["halted"])

        audit = summary["daily_audit"]
        self.assertEqual(audit["overall"], "pass")
        self.assertEqual(audit["accounting_integrity_status"], "pass")
        self.assertEqual(audit["coverage_issue_count"], 0)
        self.assertEqual(audit["economic_issue_count"], 0)
        self.assertTrue(audit["canonical_chain_valid"])
        self.assertEqual(audit["canonical_row_count"], 39)
        self.assertEqual(audit["market_data_status"], "pass")
        self.assertEqual(audit["runner_status"], "pass")
        self.assertFalse(audit["runner_active_error"])
        self.assertFalse(audit["risk_halted"])

    def test_failed_fresh_day_gate_warns_snapshot_without_mutation(self):
        summary = snapshot._summarize(
            self._raw(fresh_baseline_status="fail")
        )

        self.assertEqual(summary["overall"], "warn")
        self.assertEqual(summary["fresh_day"]["baseline_status"], "fail")
        self.assertFalse(
            summary["recovery_gate"]["state_write_authorized_by_probe"]
        )

    def test_failed_active_audit_warns_snapshot_without_error_exit_class(self):
        summary = snapshot._summarize(
            self._raw(audit_overall="fail")
        )

        self.assertEqual(summary["overall"], "warn")
        self.assertEqual(summary["daily_audit"]["overall"], "fail")
        self.assertEqual(summary["daily_audit"]["coverage_issue_count"], 1)
        self.assertEqual(summary["daily_audit"]["economic_issue_count"], 1)

    def test_failed_recovery_gate_warns_on_active_verified_v2_lineage(self):
        summary = snapshot._summarize(self._raw(recovery_overall="fail"))

        self.assertEqual(summary["overall"], "warn")
        gate = summary["recovery_gate"]
        self.assertEqual(gate["overall"], "fail")
        self.assertTrue(gate["classification_applicable"])
        self.assertEqual(
            gate["classification_reason"], "active_verified_v2_recovery_gate"
        )
        self.assertFalse(gate["mechanically_complete_for_successor_migration_design"])
        self.assertFalse(gate["manual_per_event_probe_required"])

    def test_failed_verified_v2_gate_is_superseded_on_active_v4_lineage(self):
        raw = self._raw(
            recovery_overall="fail",
            epoch_id="stable-paper-v4-20260826-successor01",
        )
        raw["verified_v2_recovery_gate"]["payload"]["diagnosis"] = (
            "canonical_ledger_epoch_lineage_not_exactly_verified_v2"
        )

        summary = snapshot._summarize(raw)

        self.assertEqual(summary["overall"], "pass")
        gate = summary["recovery_gate"]
        self.assertEqual(gate["overall"], "fail")
        self.assertFalse(gate["classification_applicable"])
        self.assertEqual(
            gate["classification_reason"],
            "superseded_by_active_v4_plus_lineage",
        )
        self.assertEqual(
            gate["active_epoch_id"], "stable-paper-v4-20260826-successor01"
        )

    def test_optional_root_failure_does_not_warn_when_required_runtime_is_healthy(self):
        raw = self._raw(
            recovery_overall="fail",
            epoch_id="stable-paper-v4-20260826-successor01",
        )
        raw["root"] = {"status": "error", "error": "HTTPError: 404"}

        summary = snapshot._summarize(raw)

        self.assertEqual(summary["overall"], "pass")
        connectivity = summary["connectivity"]
        self.assertIn("root", connectivity["failed_endpoints"])
        self.assertNotIn("root", connectivity["classification_failed_endpoints"])
        self.assertIn("root", connectivity["nonblocking_failed_endpoints"])
        self.assertTrue(connectivity["root_optional_nonblocking"])

    def test_root_failure_stays_blocking_when_required_self_check_is_unhealthy(self):
        raw = self._raw(epoch_id="stable-paper-v4-20260826-successor01")
        raw["root"] = {"status": "error", "error": "HTTPError: 404"}
        raw["self_check"]["payload"]["overall"] = "fail"

        summary = snapshot._summarize(raw)

        self.assertEqual(summary["overall"], "warn")
        self.assertIn("root", summary["connectivity"]["classification_failed_endpoints"])
        self.assertFalse(summary["connectivity"]["root_optional_nonblocking"])

    def test_required_endpoint_failure_still_warns_on_v4(self):
        raw = self._raw(epoch_id="stable-paper-v4-20260826-successor01")
        raw["paper_status"] = {"status": "error", "error": "timeout"}

        summary = snapshot._summarize(raw)

        self.assertEqual(summary["overall"], "warn")
        self.assertIn(
            "paper_status", summary["connectivity"]["classification_failed_endpoints"]
        )


if __name__ == "__main__":
    unittest.main()
