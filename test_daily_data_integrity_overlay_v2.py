from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import daily_data_integrity_audit_overlay as overlay
import provider_request_accounting_overlay as provider_accounting


class _Daily:
    @staticmethod
    def _next_action(sections):
        return {
            "status": "none",
            "priority": None,
            "section": None,
            "action": "none",
            "reason": None,
        }


def _base_payload():
    sections = {
        "01_account_and_open_position_performance": {"status": "pass", "reasons": []},
        "02_auto_runner_liveness": {"status": "pass", "reasons": []},
        "03_active_errors_and_recursion": {"status": "pass", "reasons": []},
        "04_risk_controls_and_drawdown": {
            "status": "pass",
            "reasons": [],
            "realized_loss_pct": 0.12,
            "intraday_drawdown_pct": 0.12,
        },
        "05_scanner_signals_entries_rejections": {"status": "pass", "reasons": []},
        "06_top_five_blockers": {"status": "pass", "reasons": [], "blockers": []},
        "07_entry_pipeline_ownership_and_stability": {"status": "pass", "reasons": []},
        "08_trade_journal_reconciliation": {"status": "pass", "reasons": []},
        "09_state_persistence_backup_recovery": {"status": "pass", "reasons": []},
        "10_runtime_shadow_cycles_and_parity": {"status": "pass", "reasons": []},
    }
    sections["11_conclusion"] = {
        "status": "pass",
        "pass_count": 10,
        "warn_count": 0,
        "fail_count": 0,
        "checked_sections": 10,
    }
    sections["12_next_action"] = {"status": "none", "action": "none"}
    return {
        "status": "ok",
        "overall": "pass",
        "version": "test",
        "generated_local": "2026-08-06 13:46:56 CDT",
        "duration_seconds": 0.2,
        "sections": sections,
        "links": {"routine_daily_audit": "https://example.test/paper/daily-audit"},
        "authority": {"reporting_only": True},
    }


def _integrity_section():
    return {
        "status": "pass",
        "reasons": [],
        "provider_circuit_open": False,
        "protected_symbols_blocked": [],
        "active_contaminated_feature_count": 0,
        "path_integrity": {
            "valid_rows": 0,
            "invalid_or_quarantined_rows": 4,
            "training_eligible_rows": 0,
            "recomputed_rows": 0,
        },
        "mae_mfe_integrity": {
            "valid_path_rows": 0,
            "invalid_or_quarantined_path_rows": 4,
            "training_eligible_feature_rows": 0,
            "quarantined_feature_rows": 4,
            "recomputed_rows": 0,
        },
        "forward_validation": {
            "valid_exact_lifecycle_rows_observed": 0,
            "complete": False,
            "historical_backfill_established": False,
        },
    }


class DailyDataIntegrityOverlayV2Tests(unittest.TestCase):
    def test_finalizer_counts_integrity_section_after_outer_wrappers(self):
        with patch.object(overlay, "build_integrity_section", return_value=_integrity_section()):
            payload = overlay._finalize_payload(_base_payload(), _Daily(), SimpleNamespace())

        conclusion = payload["sections"]["11_conclusion"]
        self.assertEqual(
            conclusion,
            {
                "status": "pass",
                "pass_count": 11,
                "warn_count": 0,
                "fail_count": 0,
                "checked_sections": 11,
            },
        )
        risk = payload["sections"]["04_risk_controls_and_drawdown"]
        self.assertEqual(risk["net_daily_loss_pct"], 0.12)
        self.assertEqual(risk["realized_loss_pct_source_key"], "risk_controls.daily_loss_pct")
        self.assertTrue(payload["links"]["full_daily_audit"].endswith("/paper/daily-audit?full=1"))

    def test_compact_payload_keeps_operator_fields_without_full_sections(self):
        with patch.object(overlay, "build_integrity_section", return_value=_integrity_section()):
            payload = overlay._finalize_payload(_base_payload(), _Daily(), SimpleNamespace())

        compact = overlay._compact_payload(payload)
        self.assertEqual(compact["type"], "daily_operational_audit_compact")
        self.assertEqual(compact["section_summary"]["checked"], 11)
        self.assertEqual(compact["section_summary"]["pass"], 11)
        self.assertEqual(compact["risk"]["net_daily_loss_pct"], 0.12)
        self.assertEqual(
            compact["data_integrity"]["path_integrity"]["invalid_or_quarantined_rows"],
            4,
        )
        self.assertNotIn("sections", compact)

    def test_integrity_counts_are_explicit_integers(self):
        counts = overlay._integrity_counts(
            {"invalid_or_quarantined_rows": 4, "training_eligible_rows": 0},
            {},
            {
                "valid_path_rows": 0,
                "ml_rows_quarantined": 3,
                "trade_rows_quarantined": 1,
            },
            {},
        )

        self.assertEqual(counts["valid_path_rows"], 0)
        self.assertEqual(counts["invalid_or_quarantined_path_rows"], 4)
        self.assertEqual(counts["training_eligible_feature_rows"], 0)
        self.assertEqual(counts["quarantined_feature_rows"], 4)
        self.assertEqual(counts["recomputed_rows"], 0)
        self.assertTrue(all(isinstance(value, int) for value in counts.values()))

    def test_provider_accounting_exposes_one_in_flight_request(self):
        accounting = provider_accounting.accounting_payload(
            {
                "requests": 228,
                "successes": 227,
                "failures": 0,
                "empty": 0,
                "hygiene_blocked": 0,
                "provider_circuit_skips": 0,
                "symbol_backoff_skips": 0,
                "timeouts": 0,
            }
        )
        self.assertEqual(accounting["classified_terminal_outcomes"], 227)
        self.assertEqual(accounting["in_flight_or_unclassified_requests"], 1)
        self.assertFalse(accounting["accounting_complete_at_snapshot"])

    def test_provider_timeouts_are_not_double_counted(self):
        accounting = provider_accounting.accounting_payload(
            {
                "requests": 10,
                "successes": 8,
                "failures": 2,
                "timeouts": 1,
            }
        )
        self.assertEqual(accounting["classified_terminal_outcomes"], 10)
        self.assertEqual(accounting["in_flight_or_unclassified_requests"], 0)
        self.assertEqual(accounting["timeouts_reported_separately"], 1)

    def test_bootstrap_source_contains_registration_heartbeat_contract(self):
        source = Path("bootstrap_wsgi.py").read_text(encoding="utf-8")
        self.assertIn("v6-registration-heartbeat", source)
        self.assertIn("registration_elapsed_seconds", source)
        self.assertIn("registration_slow", source)
        self.assertIn("runtime-registration-bootstrap-heartbeat", source)
        compile(source, "bootstrap_wsgi.py", "exec")


if __name__ == "__main__":
    unittest.main()
