from __future__ import annotations

import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import daily_data_integrity_audit_overlay as integrity_overlay
import daily_operational_audit as audit


class DailyOperationalAuditTests(unittest.TestCase):
    def _core(self) -> SimpleNamespace:
        now = time.time()
        return SimpleNamespace(
            portfolio={
                "cash": 9_878.62,
                "equity": 9_999.56,
                "positions": {"TSM": {"unrealized_pnl": -0.44}},
                "trades": [{"symbol": "TSM", "side": "buy"}],
                "performance": {
                    "realized_pnl_today": 0.0,
                    "realized_pnl_total": 0.0,
                    "unrealized_pnl": -0.44,
                    "wins_total": 0,
                    "losses_total": 0,
                },
                "auto_runner": {
                    "enabled": True,
                    "thread_started": True,
                    "interval_seconds": 300,
                    "last_attempt_ts": now - 30,
                    "last_attempt_source": "auto",
                    "last_successful_run_local": "2026-08-04 08:58:20 CDT",
                    "last_successful_run_source": "auto",
                    "last_error": None,
                },
                "risk_controls": {
                    "halted": False,
                    "self_defense_active": False,
                    "daily_loss_pct": 0.0,
                    "intraday_drawdown_pct": 0.0044,
                },
                "scanner_audit": {
                    "signals_found": 13,
                    "blocked_entries": [
                        {"symbol": "AMD", "category": "capacity", "reason": "position capacity reached"}
                    ],
                },
                "decision_audit": {
                    "signals_found": 13,
                    "entries_count": 0,
                    "rejected_signals_count": 1,
                },
                "blocked_entry_reason_audit": {"signals_found": 13},
                "trade_journal": {
                    "journal_summary": {
                        "execution_rows_count": 1,
                        "open_positions_count": 1,
                        "realized_total": 0.0,
                        "unrealized_pnl": -0.44,
                    }
                },
                "runtime_shadow_capture": {
                    "capture_state": "captured",
                    "latest_parity": True,
                },
            },
            local_ts_text=lambda: "2026-08-04 09:43:00 CDT",
            scan_signals=lambda *args, **kwargs: None,
            try_entries_and_rotations=lambda *args, **kwargs: None,
        )

    @staticmethod
    def _passing_integrity_section():
        return {
            "status": "pass",
            "reasons": [],
            "provider_circuit_open": False,
            "protected_symbols_blocked": [],
            "active_contaminated_feature_count": 0,
            "provider_request_accounting": {
                "in_flight_or_unclassified_requests": 0,
                "accounting_complete_at_snapshot": True,
            },
        }

    def test_curated_audit_has_exactly_thirteen_bounded_sections_after_integrity_overlay(self) -> None:
        core = self._core()
        composition = {
            "stack_stable": True,
            "recursion_safe": True,
            "participation_valve_chain_cycle_free": True,
            "direct_core_base": True,
        }
        bear = {
            "owned": True,
            "wrapper_counts": {"bear_wrapper_count": 1, "xray_wrapper_count": 1},
        }
        shadow = {
            "capture_state": "captured",
            "latest_parity": True,
            "latest_cycle_id": "observed-cycle",
            "total_cycles": 1,
            "total_candidates": 28,
        }
        persistence = {
            "state_file": "/data/state.json",
            "state_file_exists": True,
            "state_file_size_bytes": 1_024,
            "state_file_modified_age_seconds": 10.0,
            "persistent_volume_configured": True,
            "backup_count": 1,
            "latest_backup": "/data/state.json.bak",
            "transaction_status": "ok",
            "recovery_status": "ok",
            "archive_status": "ok",
            "provenance_status": "ok",
            "corruption_detected": False,
            "last_error": None,
            "recovery_failed": False,
        }

        def status(module_name, _core, argument=None):
            if module_name == "entry_pipeline_composition_guard":
                return composition
            if module_name == "bear_recovery_stack_contract":
                return bear
            if module_name == "runtime_shadow_capture":
                return shadow
            return {}

        with patch.object(audit, "_status_payload", side_effect=status), patch.object(
            audit, "_state_persistence", return_value=persistence
        ), patch.object(
            integrity_overlay,
            "build_integrity_section",
            return_value=self._passing_integrity_section(),
        ):
            payload = audit.build_payload(core)

        self.assertEqual(payload["overall"], "pass")
        self.assertEqual(len(payload["sections"]), 13)
        self.assertEqual(payload["sections"]["11_conclusion"]["checked_sections"], 11)
        self.assertEqual(payload["sections"]["12_next_action"]["status"], "none")
        self.assertEqual(payload["performance_contract"]["route_fanout_count"], 0)
        self.assertEqual(payload["performance_contract"]["external_provider_calls"], 0)
        self.assertLess(payload["duration_seconds"], 5.0)

    def test_active_recursion_is_fail_with_one_specific_action(self) -> None:
        core = self._core()
        core.portfolio["auto_runner"].update(
            {
                "last_attempt_ts": time.time(),
                "last_error": "RecursionError: maximum recursion depth exceeded",
                "last_successful_run_local": None,
            }
        )
        persistence = {
            "state_file": "/data/state.json",
            "state_file_exists": True,
            "state_file_size_bytes": 1_024,
            "state_file_modified_age_seconds": 10.0,
            "persistent_volume_configured": True,
            "backup_count": 1,
            "latest_backup": "/data/state.json.bak",
            "transaction_status": "ok",
            "recovery_status": "ok",
            "archive_status": "ok",
            "provenance_status": "ok",
            "corruption_detected": False,
            "last_error": None,
            "recovery_failed": False,
        }
        with patch.object(audit, "_status_payload", return_value={}), patch.object(
            audit, "_state_persistence", return_value=persistence
        ), patch.object(
            integrity_overlay,
            "build_integrity_section",
            return_value=self._passing_integrity_section(),
        ):
            payload = audit.build_payload(core)

        self.assertEqual(payload["overall"], "fail")
        self.assertEqual(payload["sections"]["03_active_errors_and_recursion"]["status"], "fail")
        action = payload["sections"]["12_next_action"]
        self.assertEqual(action["status"], "required")
        self.assertEqual(action["section"], "03_active_errors_and_recursion")
        self.assertIn("active runtime error", action["action"])

    def test_source_contains_no_route_fanout_or_trading_actions(self) -> None:
        source = Path(audit.__file__).read_text(encoding="utf-8")
        forbidden = (
            "requests.get(",
            "urlopen(",
            "test_client(",
            '"/paper/run"',
            "try_entries_and_rotations(",
            "scan_signals(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
