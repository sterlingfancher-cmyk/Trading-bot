"""Read-only canonical outcome memory and shadow-AI scorecards.

This module accepts already-derived, integrity-qualified outcome rows.  It never
reads or writes the canonical ledger itself and never infers lifecycle identity
from symbol or time.  A caller must provide an explicit immutable execution ID
and an exact AI-review-to-execution binding.  Missing or contradictory evidence
is excluded with diagnostics.

The output is rebuildable research evidence only.  It cannot promote a model,
change a rule decision, mutate state, or participate in execution.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


VERSION = "shadow-ai-outcome-memory-2026-09-02-v1"
DERIVATION_VERSION = "canonical-outcome-derived-v1"


@dataclass(frozen=True, slots=True)
class OutcomeMemoryConfig:
    max_records: int = 5_000
    min_scorecard_samples: int = 20
    max_symbol_concentration: float = 0.35

    def __post_init__(self) -> None:
        if not 1 <= int(self.max_records) <= 50_000:
            raise ValueError("max_records must be in [1, 50000]")
        if not 2 <= int(self.min_scorecard_samples) <= 10_000:
            raise ValueError("min_scorecard_samples must be in [2, 10000]")
        if not 0.05 <= float(self.max_symbol_concentration) <= 1.0:
            raise ValueError("max_symbol_concentration must be in [0.05, 1.0]")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any, *, upper: bool = False) -> str:
    result = str(value or "").strip()
    return result.upper() if upper else result.lower()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _signal_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    return _string_tuple(value)


def _normalized_outcome(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    execution_id = str(row.get("canonical_execution_id") or "").strip()
    source_ids = _string_tuple(row.get("canonical_source_ids"))
    symbol = _text(row.get("symbol"), upper=True)
    side = _text(row.get("side"))
    realized = _number(row.get("realized_return_pct"))
    mfe = _number(row.get("mfe_pct"))
    mae = _number(row.get("mae_pct"))
    notional = _number(row.get("entry_notional_usd"))
    holding_seconds = _number(row.get("holding_period_seconds"))

    required_text = {
        "canonical_execution_id": execution_id,
        "symbol": symbol,
        "strategy": _text(row.get("strategy")),
        "setup_family": _text(row.get("setup_family")),
        "side": side,
        "regime": _text(row.get("regime")),
        "sector": _text(row.get("sector"), upper=True),
        "bucket": _text(row.get("bucket")),
        "volatility_state": _text(row.get("volatility_state")),
        "session_phase": _text(row.get("session_phase")),
        "exit_reason": _text(row.get("exit_reason")),
        "calendar_segment": str(row.get("calendar_segment") or "").strip(),
        "path_source_id": str(row.get("path_source_id") or "").strip(),
    }
    missing = [key for key, value in required_text.items() if not value]
    if missing:
        return None, "missing_required_fields:" + ",".join(sorted(missing))
    if side not in {"long", "short"}:
        return None, "invalid_side"
    if not source_ids or execution_id not in source_ids:
        return None, "canonical_source_ids_do_not_include_primary"
    if row.get("canonical_evidence_status") != "valid":
        return None, "canonical_evidence_not_valid"
    if row.get("path_integrity_status") != "valid" or row.get("path_training_eligible") is not True:
        return None, "path_evidence_not_eligible"
    if realized is None or not -100.0 < realized < 500.0:
        return None, "invalid_realized_return_pct"
    if mfe is None or not 0.0 <= mfe < 500.0:
        return None, "invalid_mfe_pct"
    if mae is None or not -100.0 < mae <= 0.0:
        return None, "invalid_mae_pct"
    if notional is None or notional <= 0.0:
        return None, "invalid_entry_notional_usd"
    if holding_seconds is None or holding_seconds < 0.0:
        return None, "invalid_holding_period_seconds"

    normalized = {
        **required_text,
        "canonical_source_ids": list(source_ids),
        "canonical_evidence_status": "valid",
        "path_integrity_status": "valid",
        "path_training_eligible": True,
        "signal_characteristics": list(_signal_tuple(row.get("signal_characteristics"))),
        "realized_return_pct": realized,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "entry_notional_usd": notional,
        "holding_period_seconds": int(holding_seconds),
        "derivation_version": DERIVATION_VERSION,
    }
    return normalized, None


def build_outcome_memory(
    outcome_rows: Iterable[Mapping[str, Any]],
    config: OutcomeMemoryConfig | None = None,
) -> dict[str, Any]:
    """Build a bounded index without mutating or retaining source mappings."""
    settings = config or OutcomeMemoryConfig()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exclusions: list[dict[str, Any]] = []
    observed = 0
    for raw in outcome_rows:
        observed += 1
        if not isinstance(raw, Mapping):
            exclusions.append({"reason": "row_not_mapping"})
            continue
        normalized, error = _normalized_outcome(raw)
        if error or normalized is None:
            exclusions.append({
                "canonical_execution_id": str(raw.get("canonical_execution_id") or ""),
                "reason": error or "normalization_failed",
            })
            continue
        grouped[normalized["canonical_execution_id"]].append(normalized)

    accepted: list[dict[str, Any]] = []
    for execution_id in sorted(grouped):
        variants = {
            json.dumps(item, sort_keys=True, separators=(",", ":"))
            for item in grouped[execution_id]
        }
        if len(variants) != 1:
            exclusions.append({
                "canonical_execution_id": execution_id,
                "reason": "contradictory_rows_for_canonical_execution_id",
            })
            continue
        accepted.append(json.loads(next(iter(variants))))

    retained = accepted[-settings.max_records :]
    return {
        "status": "ok",
        "overall": "pass" if not exclusions else "warn",
        "type": "shadow_ai_canonical_outcome_memory",
        "version": VERSION,
        "derivation_version": DERIVATION_VERSION,
        "primary_key": "canonical_execution_id",
        "source_rows_observed": observed,
        "accepted_count": len(retained),
        "excluded_count": len(exclusions),
        "truncated_count": max(0, len(accepted) - len(retained)),
        "records": retained,
        "exclusions": exclusions[-100:],
        "authority": _authority(),
    }


def find_comparable_outcomes(
    memory: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    limit: int = 10,
) -> tuple[dict[str, Any], ...]:
    """Return deterministic similarity results; side is a mandatory match."""
    if not 1 <= int(limit) <= 100:
        raise ValueError("limit must be in [1, 100]")
    side = _text(context.get("side"))
    if side not in {"long", "short"}:
        return ()
    query_signals = set(_signal_tuple(context.get("signal_characteristics")))
    weights = {
        "strategy": 4,
        "setup_family": 4,
        "regime": 3,
        "sector": 2,
        "bucket": 2,
        "volatility_state": 2,
        "session_phase": 1,
    }
    ranked: list[dict[str, Any]] = []
    records = memory.get("records")
    if not isinstance(records, list):
        return ()
    for record in records:
        if not isinstance(record, Mapping) or _text(record.get("side")) != side:
            continue
        score = 5
        possible = 5 + sum(weights.values()) + 3
        matches = ["side"]
        for field, weight in weights.items():
            query_value = _text(context.get(field), upper=field == "sector")
            record_value = _text(record.get(field), upper=field == "sector")
            if query_value and query_value == record_value:
                score += weight
                matches.append(field)
        record_signals = set(_signal_tuple(record.get("signal_characteristics")))
        if query_signals and record_signals:
            overlap = len(query_signals & record_signals) / len(query_signals | record_signals)
            score += round(3 * overlap, 6)
            if overlap:
                matches.append("signal_characteristics")
        item = dict(record)
        item["comparison_score"] = round(score / possible, 6)
        item["matched_dimensions"] = matches
        ranked.append(item)
    ranked.sort(key=lambda item: (-item["comparison_score"], item["canonical_execution_id"]))
    return tuple(ranked[:limit])


def _review_identity(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("cycle_id") or ""),
        str(record.get("candidate_id") or ""),
        str(record.get("input_fingerprint") or ""),
    )


def _confidence_bucket(value: float) -> str:
    if value < 0.5:
        return "low"
    if value < 0.75:
        return "medium"
    return "high"


def _score_group(rows: list[dict[str, Any]], settings: OutcomeMemoryConfig) -> dict[str, Any]:
    count = len(rows)
    symbols = Counter(row["symbol"] for row in rows)
    concentration = max(symbols.values(), default=0) / max(1, count)
    cost_complete = all(row["inference_cost_usd"] is not None for row in rows)
    baseline = sum(row["rules_realized_pnl_usd"] for row in rows)
    hypothetical = sum(row["ai_counterfactual_pnl_usd"] for row in rows)
    incremental = hypothetical - baseline
    total_cost = sum(row["inference_cost_usd"] or 0.0 for row in rows)
    sufficient = count >= settings.min_scorecard_samples
    unconcentrated = concentration <= settings.max_symbol_concentration
    return {
        "sample_count": count,
        "symbol_count": len(symbols),
        "max_symbol_concentration": round(concentration, 6),
        "rules_realized_pnl_usd": round(baseline, 6),
        "ai_counterfactual_pnl_usd": round(hypothetical, 6),
        "incremental_pnl_before_cost_usd": round(incremental, 6),
        "inference_cost_usd": round(total_cost, 6) if cost_complete else None,
        "incremental_pnl_net_cost_usd": round(incremental - total_cost, 6) if cost_complete else None,
        "average_realized_return_pct": round(sum(row["realized_return_pct"] for row in rows) / max(1, count), 6),
        "average_mfe_pct": round(sum(row["mfe_pct"] for row in rows) / max(1, count), 6),
        "average_mae_pct": round(sum(row["mae_pct"] for row in rows) / max(1, count), 6),
        "exact_cost_coverage_complete": cost_complete,
        "sample_sufficient": sufficient,
        "concentration_acceptable": unconcentrated,
        "conclusion": "observational_only" if sufficient and unconcentrated and cost_complete else "inconclusive",
        "automatic_promotion": False,
    }


def build_counterfactual_scorecards(
    memory: Mapping[str, Any],
    review_records: Iterable[Mapping[str, Any]],
    execution_bindings: Iterable[Mapping[str, Any]],
    config: OutcomeMemoryConfig | None = None,
) -> dict[str, Any]:
    """Join reviews to outcomes only through exact, non-contradictory bindings."""
    settings = config or OutcomeMemoryConfig()
    memory_rows = memory.get("records", []) if memory.get("version") == VERSION else []
    verified_memory = build_outcome_memory(
        memory_rows if isinstance(memory_rows, list) else [],
        settings,
    )
    outcomes = {
        str(row.get("canonical_execution_id")): dict(row)
        for row in verified_memory["records"]
    }
    binding_groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for binding in execution_bindings:
        if not isinstance(binding, Mapping):
            continue
        identity = _review_identity(binding)
        execution_id = str(binding.get("canonical_execution_id") or "").strip()
        if all(identity) and execution_id:
            binding_groups[identity].add(execution_id)

    exclusions: list[dict[str, Any]] = []
    if memory.get("version") != VERSION:
        exclusions.append({"reason": "memory_version_untrusted"})
    exclusions.extend(
        {"reason": f"memory_{row.get('reason')}", "canonical_execution_id": row.get("canonical_execution_id")}
        for row in verified_memory["exclusions"]
    )
    joined: list[dict[str, Any]] = []
    review_groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for review in review_records:
        if not isinstance(review, Mapping):
            exclusions.append({"reason": "review_not_mapping"})
            continue
        identity = _review_identity(review)
        if not all(identity):
            exclusions.append({"candidate_id": identity[1], "reason": "missing_review_identity"})
            continue
        review_groups[identity].append(review)

    for identity in sorted(review_groups):
        group = review_groups[identity]
        if len(group) != 1:
            exclusions.append({"candidate_id": identity[1], "reason": "duplicate_review_identity"})
            continue
        review = group[0]
        if review.get("join_eligible") is not True:
            exclusions.append({"candidate_id": identity[1], "reason": "review_not_join_eligible"})
            continue
        bound_ids = binding_groups.get(identity, set())
        if len(bound_ids) != 1:
            exclusions.append({"candidate_id": identity[1], "reason": "missing_or_contradictory_execution_binding"})
            continue
        execution_id = next(iter(bound_ids))
        outcome = outcomes.get(execution_id)
        if outcome is None:
            exclusions.append({"candidate_id": identity[1], "reason": "canonical_outcome_missing"})
            continue
        result = review.get("result")
        if not isinstance(result, Mapping):
            exclusions.append({"candidate_id": identity[1], "reason": "result_missing"})
            continue
        decision = _text(result.get("decision"))
        confidence = _number(result.get("confidence"))
        telemetry = result.get("telemetry")
        cost = _number(telemetry.get("cost_usd_exact")) if isinstance(telemetry, Mapping) else None
        if decision not in {"agree", "reject"} or confidence is None or not 0.0 <= confidence <= 1.0:
            exclusions.append({"candidate_id": identity[1], "reason": "invalid_shadow_decision"})
            continue
        if cost is not None and cost < 0.0:
            exclusions.append({"candidate_id": identity[1], "reason": "invalid_inference_cost"})
            continue
        if _text(review.get("rules_decision")) != "enter":
            exclusions.append({"candidate_id": identity[1], "reason": "nonexecuted_rules_decision"})
            continue
        rules_pnl = outcome["entry_notional_usd"] * outcome["realized_return_pct"] / 100.0
        ai_pnl = rules_pnl if decision == "agree" else 0.0
        joined.append({
            "canonical_execution_id": execution_id,
            "candidate_id": identity[1],
            "symbol": outcome["symbol"],
            "agreement_state": "agree" if decision == "agree" else "disagree_reject",
            "confidence": confidence,
            "confidence_bucket": _confidence_bucket(confidence),
            "strategy": outcome["strategy"],
            "setup": outcome["setup_family"],
            "regime": outcome["regime"],
            "sector": outcome["sector"],
            "volatility_state": outcome["volatility_state"],
            "calendar_segment": outcome["calendar_segment"],
            "realized_return_pct": outcome["realized_return_pct"],
            "mfe_pct": outcome["mfe_pct"],
            "mae_pct": outcome["mae_pct"],
            "rules_realized_pnl_usd": rules_pnl,
            "ai_counterfactual_pnl_usd": ai_pnl,
            "inference_cost_usd": cost,
        })

    segments: dict[str, dict[str, dict[str, Any]]] = {}
    for field in (
        "agreement_state",
        "confidence_bucket",
        "strategy",
        "setup",
        "regime",
        "sector",
        "volatility_state",
        "calendar_segment",
    ):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in joined:
            grouped[str(row[field])].append(row)
        segments[field] = {
            key: _score_group(grouped[key], settings) for key in sorted(grouped)
        }

    return {
        "status": "ok",
        "overall": "pass" if joined else "warn",
        "type": "shadow_ai_rules_counterfactual_scorecards",
        "version": VERSION,
        "joined_count": len(joined),
        "excluded_count": len(exclusions),
        "aggregate": _score_group(joined, settings),
        "segments": segments,
        "joined_rows": joined[-settings.max_records :],
        "exclusions": exclusions[-100:],
        "authority": _authority(),
    }


def _authority() -> dict[str, bool]:
    return {
        "research_only": True,
        "canonical_sources_read_only": True,
        "rebuildable_derived_output": True,
        "execution_input": False,
        "changes_rule_decisions": False,
        "changes_strategy_or_thresholds": False,
        "changes_risk_or_sizing": False,
        "changes_accounting_or_canonical_history": False,
        "places_or_cancels_orders": False,
        "automatic_promotion": False,
    }
