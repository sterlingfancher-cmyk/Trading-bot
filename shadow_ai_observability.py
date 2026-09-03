"""Read-only Stage 5 observability for the shadow-AI research subsystem."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

import shadow_ai_adversarial_reviewer as reviewer
from shadow_ai_evidence_store import (
    EvidenceStoreConfig,
    ShadowAIEvidenceStore,
    VERSION as STORE_VERSION,
    default_evidence_path,
)


VERSION = "shadow-ai-observability-2026-09-03-v1"
MIN_FORWARD_RESULTS = 100
MAX_UNAVAILABLE_RATE = 0.20
_REGISTERED_APP_IDS: set[int] = set()
_STORE = ShadowAIEvidenceStore(EvidenceStoreConfig(path=default_evidence_path()))


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if parsed >= 0 else 0


def _telemetry(records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    models: Counter[str] = Counter()
    prompt_tokens = completion_tokens = reasoning_tokens = cached_tokens = 0
    citations = source_count = fallback_count = exact_cost_rows = 0
    total_cost = 0.0
    join_eligible = 0
    unique_cycles: set[str] = set()
    for record in records:
        result = record.get("result") if isinstance(record.get("result"), Mapping) else {}
        telemetry = result.get("telemetry") if isinstance(result.get("telemetry"), Mapping) else {}
        decision = str(result.get("decision") or "unknown")
        decisions[decision] += 1
        providers[str(telemetry.get("provider") or "unknown")] += 1
        models[str(telemetry.get("model") or "unknown")] += 1
        prompt_tokens += _nonnegative_int(telemetry.get("prompt_tokens"))
        completion_tokens += _nonnegative_int(telemetry.get("completion_tokens"))
        reasoning_tokens += _nonnegative_int(telemetry.get("reasoning_tokens"))
        cached_tokens += _nonnegative_int(telemetry.get("cached_tokens"))
        source_count += _nonnegative_int(telemetry.get("source_count"))
        result_citations = result.get("citations")
        citations += len(result_citations) if isinstance(result_citations, list) else 0
        fallback_count += int(bool(result.get("fallback_used")))
        cost = telemetry.get("cost_usd_exact")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            exact_cost_rows += 1
            total_cost += float(cost)
        join_eligible += int(record.get("join_eligible") is True)
        if record.get("cycle_id"):
            unique_cycles.add(str(record.get("cycle_id")))
    count = len(records)
    unavailable = decisions.get("unavailable", 0)
    return {
        "record_count": count,
        "unique_cycle_count": len(unique_cycles),
        "join_eligible_count": join_eligible,
        "decision_counts": dict(sorted(decisions.items())),
        "provider_counts": dict(sorted(providers.items())),
        "model_counts": dict(sorted(models.items())),
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / count, 6) if count else None,
        "unavailable_count": unavailable,
        "unavailable_rate": round(unavailable / count, 6) if count else None,
        "citation_count": citations,
        "provider_source_count": source_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "exact_cost_rows": exact_cost_rows,
        "exact_cost_coverage_complete": bool(count and exact_cost_rows == count),
        "total_inference_cost_usd_exact": round(total_cost, 8) if count and exact_cost_rows == count else None,
    }


def build_payload() -> dict[str, Any]:
    reviewer_status = reviewer.status_payload()
    store_status = _STORE.status_payload()
    records = _STORE.records_snapshot() if store_status.get("integrity_valid") else ()
    telemetry = _telemetry(records)
    reviewer_enabled = reviewer_status.get("enabled") is True
    worker_alive = reviewer_status.get("worker_alive") is True
    enough_results = telemetry["join_eligible_count"] >= MIN_FORWARD_RESULTS
    unavailable_rate = telemetry["unavailable_rate"]
    availability_ok = unavailable_rate is not None and unavailable_rate <= MAX_UNAVAILABLE_RATE
    cost_complete = telemetry["exact_cost_coverage_complete"]
    durable = store_status.get("restart_loadable") is True
    forward_eligible = bool(
        reviewer_enabled
        and worker_alive
        and durable
        and enough_results
        and availability_ok
        and cost_complete
    )
    if not reviewer_enabled:
        evidence_state = "not_started_reviewer_disabled"
    elif not durable:
        evidence_state = "blocked_store_integrity"
    elif not enough_results:
        evidence_state = "collecting"
    elif not availability_ok or not cost_complete:
        evidence_state = "inconclusive_quality_or_cost_coverage"
    else:
        evidence_state = "forward_observation_threshold_met"
    overall = "warn" if store_status.get("integrity_valid") is False else "pass"
    return {
        "status": "ok" if overall == "pass" else "warn",
        "overall": overall,
        "type": "shadow_ai_research_observability",
        "version": VERSION,
        "reviewer": reviewer_status,
        "evidence_store": store_status,
        "telemetry": telemetry,
        "outcome_memory": {
            "implemented": True,
            "runtime_integrated": False,
            "canonical_sources_read_only": True,
            "exact_execution_binding_required": True,
        },
        "counterfactual_scorecards": {
            "implemented": True,
            "runtime_integrated": False,
            "automatic_promotion": False,
            "state": "awaiting_exact_completed_outcome_bindings",
        },
        "forward_evidence": {
            "state": evidence_state,
            "eligible": forward_eligible,
            "minimum_join_eligible_results": MIN_FORWARD_RESULTS,
            "maximum_unavailable_rate": MAX_UNAVAILABLE_RATE,
            "enough_results": enough_results,
            "availability_ok": availability_ok,
            "exact_cost_coverage_complete": cost_complete,
            "restart_durable": durable,
            "promotion_authorized": False,
        },
        "authority": {
            "read_only_observability": True,
            "rules_engine_sole_execution_authority": True,
            "execution_input": False,
            "changes_strategy_or_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_accounting_or_canonical_history": False,
            "places_or_cancels_orders": False,
            "automatic_promotion": False,
        },
    }


def install(flask_app: Any = None) -> dict[str, Any]:
    store_status = _STORE.load()
    reviewer.configure_evidence_sink(_STORE.append)
    if flask_app is not None and id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify

        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/shadow-ai-research-status" not in existing:
            flask_app.add_url_rule(
                "/paper/shadow-ai-research-status",
                "shadow_ai_research_status",
                lambda: jsonify(build_payload()),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return {
        "status": "ok" if store_status.get("integrity_valid") else "warn",
        "version": VERSION,
        "store_version": STORE_VERSION,
        "route_registered": flask_app is not None,
        "reviewer_evidence_sink_configured": True,
        "reviewer_enabled": reviewer.status_payload().get("enabled") is True,
        "execution_input": False,
    }
