from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
CONTRACT_PATH = ROOT / "shadow_ai_research_contract.json"


class ShadowAIResearchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_stage_three_reviewer_has_no_execution_authority(self):
        contract = self.contract
        policy = contract["policy"]

        self.assertEqual(
            contract["implementation_stage"],
            "stage_3_async_adversarial_reviewer",
        )
        self.assertTrue(policy["paper_only"])
        self.assertTrue(policy["research_only"])
        self.assertTrue(policy["rules_engine_sole_execution_authority"])
        self.assertFalse(policy["automatic_promotion"])

        forbidden_true = [
            "changes_strategy",
            "changes_thresholds",
            "changes_ranking_or_selection",
            "changes_sizing_or_exposure",
            "changes_stops_or_targets",
            "changes_exits_or_allocation",
            "changes_risk_or_halts",
            "changes_accounting_or_canonical_history",
            "changes_live_or_ml_authority",
            "places_or_cancels_orders",
            "blocks_or_delays_execution",
        ]
        self.assertFalse(any(policy[name] for name in forbidden_true))

    def test_integration_extends_existing_observer_without_new_owner(self):
        integration = self.contract["integration"]
        queue = self.contract["queue"]

        self.assertEqual(integration["existing_cycle_owner"], "run_report_guard.py")
        self.assertEqual(integration["existing_cycle_callable"], "run_cycle")
        self.assertFalse(integration["adds_cycle_wrapper"])
        self.assertFalse(integration["adds_callable_owner"])
        self.assertFalse(integration["provider_calls_on_execution_thread"])
        self.assertFalse(integration["returned_trading_result_contains_ai_payload"])
        self.assertTrue(integration["state_persistence_owner_unchanged"])
        self.assertTrue(integration["canonical_ledger_read_only"])
        self.assertFalse(integration["import_time_provider_calls"])
        self.assertFalse(integration["import_time_worker_threads"])
        self.assertFalse(queue["execution_waits_for_result"])
        self.assertTrue(queue["implemented"])
        self.assertTrue(queue["runtime_registered_disabled_by_default"])
        self.assertEqual(queue["full_policy"], "drop_new_request_with_telemetry")

    def test_fail_closed_schema_has_only_shadow_decisions(self):
        client = self.contract["client"]
        result = self.contract["result_schema"]

        self.assertTrue(client["strict_json_schema"])
        self.assertTrue(client["implemented"])
        self.assertFalse(client["runtime_integrated"])
        self.assertFalse(client["bundled_network_transport"])
        self.assertEqual(client["pessimistic_fallback_decision"], "unavailable")
        self.assertEqual(
            set(result["decision_values"]),
            {"agree", "reject", "unavailable"},
        )
        self.assertFalse(result["free_text_drives_execution"])
        self.assertIn("cost_usd_exact", result["telemetry_fields"])
        self.assertIn("cached_tokens", result["telemetry_fields"])
        self.assertIn("reasoning_tokens", result["telemetry_fields"])

    def test_external_sources_are_untrusted_and_not_persisted_raw(self):
        sources = self.contract["untrusted_sources"]

        self.assertFalse(sources["retrieved_content_is_instructions"])
        self.assertTrue(sources["system_prompt_isolated_from_sources"])
        self.assertTrue(sources["embedded_tool_directives_ignored"])
        self.assertTrue(sources["citation_required_for_external_claims"])
        self.assertFalse(sources["raw_source_bodies_persisted"])
        self.assertFalse(sources["full_prompts_persisted"])
        self.assertFalse(sources["secrets_persisted"])
        self.assertEqual(sources["source_scheme_allowlist"], ["https"])

    def test_outcome_memory_is_canonical_read_only_and_rebuildable(self):
        memory = self.contract["canonical_outcome_memory"]
        scorecard = self.contract["counterfactual_scorecard"]

        self.assertEqual(memory["primary_key"], "canonical_execution_id")
        self.assertTrue(memory["canonical_source_read_only"])
        self.assertTrue(memory["rebuildable_derived_index"])
        self.assertEqual(
            memory["missing_or_contradictory_evidence_behavior"],
            "fail_closed_no_join",
        )
        self.assertFalse(scorecard["execution_input"])
        self.assertTrue(scorecard["subtracts_inference_cost"])
        self.assertFalse(scorecard["automatic_promotion"])

    def test_runtime_stages_require_every_governed_gate(self):
        validation = self.contract["validation"]
        required = [
            "exact_head_change_safety",
            "repository_safety_and_performance",
            "architecture_debt",
            "full_refactor_ownership_configuration_state_decision_runtime_startup_research",
            "exact_gunicorn_smoke_for_runtime_stages",
            "settled_splendid_self_check_for_runtime_stages",
            "successful_automatic_paper_cycle_for_runtime_stages",
            "behavior_change_requires_validation_policy",
        ]
        self.assertTrue(all(validation[name] for name in required))


if __name__ == "__main__":
    unittest.main()
