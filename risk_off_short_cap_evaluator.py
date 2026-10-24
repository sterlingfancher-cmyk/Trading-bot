"""Isolated deterministic replay for the Issue #316 short-admission hypothesis.

The evaluator never imports the runner, mutates trading state, or invents fills.
It compares observed, completed, integrity-eligible lifecycles under one change:
while the entry regime is ``risk_off``, admit at most the first new short
lifecycle in each market session.  Ranking, size, exits, and recorded cost model
are inherited unchanged from the source lifecycle.

This is a static admission replay, not execution authority.  It fails closed
unless the entry universe, lifecycle outcomes, costs, same-epoch binding, and
research/holdout coverage are explicit.
"""
from __future__ import annotations

import copy
import math
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence

VERSION = "risk-off-short-cap-evaluator-2026-10-24-v1"

REQUIRED_LIFECYCLE_FIELDS = (
    "execution_path_id",
    "accounting_epoch_id",
    "session_date",
    "entry_time",
    "side",
    "entry_market_mode",
    "net_pnl_after_costs",
    "gross_entry_notional",
    "partition",
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _metrics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    pnls = [_number(row.get("net_pnl_after_costs")) or 0.0 for row in rows]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "completed_lifecycles": len(rows),
        "session_count": len({row["session_date"] for row in rows}),
        "net_pnl_after_costs": round(sum(pnls), 2),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100.0 * len(wins) / len(pnls), 2) if pnls else None,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else ("infinite" if gross_profit else None),
        "average_win": round(gross_profit / len(wins), 2) if wins else None,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "largest_loss": round(min(losses), 2) if losses else None,
        "max_realized_drawdown_dollars": round(max_drawdown, 2),
        "gross_entry_notional": round(sum(_number(row.get("gross_entry_notional")) or 0.0 for row in rows), 2),
    }


def evaluate_risk_off_short_cap(
    *,
    lifecycles: Sequence[Mapping[str, Any]],
    session_coverage: Sequence[Mapping[str, Any]],
    accounting_epoch_id: str,
    cap_per_session: int = 1,
    minimum_complete_sessions: int = 20,
    minimum_completed_lifecycles: int = 30,
    minimum_holdout_sessions: int = 5,
) -> Dict[str, Any]:
    """Compare baseline with one-short-per-session static admission replay."""
    if cap_per_session != 1:
        raise ValueError("Issue #316 permits exactly one variable: cap_per_session=1")
    original = copy.deepcopy(list(lifecycles))
    coverage_by_date = {
        str(row.get("session_date")): copy.deepcopy(dict(row))
        for row in session_coverage
        if row.get("accounting_epoch_id") == accounting_epoch_id
    }
    exclusions: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    for source in original:
        row = dict(source)
        path = str(row.get("execution_path_id") or "missing_execution_path_id")
        reasons: List[str] = []
        missing = [field for field in REQUIRED_LIFECYCLE_FIELDS if row.get(field) is None]
        if missing:
            reasons.append("missing_fields:" + ",".join(missing))
        if row.get("accounting_epoch_id") != accounting_epoch_id:
            reasons.append("cross_epoch")
        if str(row.get("side") or "").lower() != "short":
            reasons.append("not_short")
        if str(row.get("entry_market_mode") or "").lower() != "risk_off":
            reasons.append("not_risk_off_at_entry")
        if row.get("outcome_complete") is not True:
            reasons.append("incomplete_lifecycle_outcome")
        if row.get("integrity_eligible") is not True:
            reasons.append(str(row.get("integrity_exclusion_reason") or "integrity_ineligible"))
        if row.get("cost_coverage_complete") is not True:
            reasons.append("missing_fee_or_slippage_coverage")
        coverage = coverage_by_date.get(str(row.get("session_date") or ""), {})
        for field in ("complete_entry_universe", "complete_exit_outcomes", "cost_coverage_complete"):
            if coverage.get(field) is not True:
                reasons.append("session_coverage:" + field)
        if str(row.get("partition") or "") not in {"research", "holdout"}:
            reasons.append("invalid_partition")
        if reasons:
            exclusions.append({
                "execution_path_id": path,
                "session_date": row.get("session_date"),
                "canonical_net_pnl_after_costs": _number(row.get("net_pnl_after_costs")),
                "reasons": sorted(set(reasons)),
                "canonical_outcome_preserved": True,
            })
        else:
            eligible.append(row)

    eligible.sort(key=lambda row: (str(row["session_date"]), _number(row["entry_time"]) or 0.0, str(row["execution_path_id"])))
    by_session: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_session[str(row["session_date"])].append(row)
    candidate: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for session_date in sorted(by_session):
        rows = by_session[session_date]
        candidate.extend(rows[:cap_per_session])
        skipped.extend(rows[cap_per_session:])

    complete_sessions = sorted({row["session_date"] for row in eligible})
    holdout_sessions = sorted({row["session_date"] for row in eligible if row["partition"] == "holdout"})
    research_rows = [row for row in eligible if row["partition"] == "research"]
    holdout_rows = [row for row in eligible if row["partition"] == "holdout"]
    candidate_research = [row for row in candidate if row["partition"] == "research"]
    candidate_holdout = [row for row in candidate if row["partition"] == "holdout"]
    blockers: List[str] = []
    if len(complete_sessions) < minimum_complete_sessions:
        blockers.append(f"complete_sessions:{len(complete_sessions)}<{minimum_complete_sessions}")
    if len(eligible) < minimum_completed_lifecycles:
        blockers.append(f"eligible_lifecycles:{len(eligible)}<{minimum_completed_lifecycles}")
    if len(holdout_sessions) < minimum_holdout_sessions:
        blockers.append(f"holdout_sessions:{len(holdout_sessions)}<{minimum_holdout_sessions}")
    if not research_rows:
        blockers.append("research_partition_empty")
    if not holdout_rows:
        blockers.append("holdout_partition_empty")
    if not coverage_by_date:
        blockers.append("same_epoch_session_coverage_empty")
    if exclusions:
        blockers.append("source_rows_excluded_or_incomplete")

    baseline_metrics = _metrics(eligible)
    candidate_metrics = _metrics(candidate)
    research_baseline = _metrics(research_rows)
    research_candidate = _metrics(candidate_research)
    holdout_baseline = _metrics(holdout_rows)
    holdout_candidate = _metrics(candidate_holdout)
    observed_delta = round(candidate_metrics["net_pnl_after_costs"] - baseline_metrics["net_pnl_after_costs"], 2)
    if blockers:
        verdict = "insufficient_evidence"
    else:
        research_better = (
            research_candidate["net_pnl_after_costs"] > research_baseline["net_pnl_after_costs"]
            and research_candidate["max_realized_drawdown_dollars"] >= research_baseline["max_realized_drawdown_dollars"]
        )
        holdout_better = (
            holdout_candidate["net_pnl_after_costs"] > holdout_baseline["net_pnl_after_costs"]
            and holdout_candidate["max_realized_drawdown_dollars"] >= holdout_baseline["max_realized_drawdown_dollars"]
        )
        verdict = "candidate_improves_static_replay" if research_better and holdout_better else "candidate_not_proven_better"

    return {
        "schema_version": VERSION,
        "status": "research_only",
        "accounting_epoch_id": accounting_epoch_id,
        "question": "Does a one-new-risk_off-short-lifecycle-per-session cap improve eligible deterministic performance?",
        "one_variable": {"risk_off_new_short_cap_per_session": 1},
        "unchanged_contract": ["ranker", "position_sizing", "exit_rules", "cost_model", "hard_risk_limits", "runner"],
        "verdict": verdict,
        "promotion_ready": False,
        "blockers": sorted(set(blockers)),
        "coverage": {
            "complete_same_epoch_sessions": complete_sessions,
            "holdout_sessions": holdout_sessions,
            "eligible_lifecycles": len(eligible),
            "excluded_lifecycles": len(exclusions),
        },
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "observed_static_replay_delta_net_pnl": observed_delta,
        "partitions": {
            "research": {"baseline": research_baseline, "candidate": research_candidate},
            "holdout": {"baseline": holdout_baseline, "candidate": holdout_candidate},
        },
        "candidate_admitted_path_ids": [row["execution_path_id"] for row in candidate],
        "candidate_skipped_path_ids": [row["execution_path_id"] for row in skipped],
        "exclusions": exclusions,
        "limitations": [
            "Static replay removes later observed admissions; it does not simulate freed capital or changed future rankings.",
            "Observed outcomes are reused only for admitted baseline lifecycles; no replacement fills are synthesized.",
            "A favorable replay is not promotion evidence without full VALIDATION_POLICY gates and forward shadow.",
        ],
        "guardrails": {
            "source_rows_mutated": original != list(lifecycles),
            "canonical_outcomes_rewritten": False,
            "invented_outcomes": False,
            "execution_authority": False,
            "automatic_promotion": False,
        },
    }
