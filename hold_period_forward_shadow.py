"""Fail-closed forward-shadow evidence for the frozen ``hold_10d`` candidate.

The comparator consumes two already-completed Performance Audit V2 simulations.
It never imports the runtime, fetches market data, writes state, or changes an
exit.  Recomputing the isolated audit therefore reconstructs the entire forward
sample from immutable policy identifiers and market inputs.
"""
from __future__ import annotations

import collections
import datetime as dt
import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

VERSION = "hold-period-forward-shadow-2026-09-09-v1-frozen-contract"
CANDIDATE_ID = "hold_10d"
FREEZE_DATE = "2026-09-09"
BASELINE_ID = "adaptive_baseline"
TRANSACTION_COST_BPS_PER_SIDE = 8.0
STRESS_COST_BPS_PER_SIDE = 25.0
OBSERVATION_LIMIT = 1000

CRITERIA: Dict[str, Any] = {
    "minimum_exact_matched_completed_lifecycles": 100,
    "minimum_exit_divergences": 30,
    "minimum_forward_sessions": 60,
    "minimum_calendar_months": 3,
    "minimum_neutral_entries": 20,
    "minimum_defensive_or_risk_off_entries": 20,
    "minimum_exact_pairing_coverage_pct": 60.0,
    "maximum_single_symbol_share_pct": 25.0,
    "minimum_mean_return_delta_pct_at_8bps": 0.0,
    "minimum_mean_return_delta_pct_at_25bps": 0.0,
    "require_nonnegative_neutral_delta": True,
    "require_nonnegative_defensive_or_risk_off_delta": True,
    "automatic_promotion": False,
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> List[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> str:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _entry_key(row: Mapping[str, Any]) -> Tuple[str, str, float]:
    return (
        str(row.get("symbol") or "").strip().upper(),
        _date(row.get("date")),
        round(_f(row.get("price")), 6),
    )


def _normalized_return(entry: Mapping[str, Any], exit_row: Mapping[str, Any]) -> float | None:
    allocation = _f(entry.get("allocation"))
    pnl = _f(exit_row.get("pnl"))
    if allocation <= 0:
        return None
    return round(pnl / allocation * 100.0, 6)


def _lifecycles(simulation: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    active: Dict[str, Mapping[str, Any]] = {}
    completed: List[Dict[str, Any]] = []
    errors: List[str] = []
    for row in _rows(simulation.get("trades")):
        symbol = str(row.get("symbol") or "").strip().upper()
        action = str(row.get("action") or "").lower()
        if not symbol:
            errors.append("trade_missing_symbol")
            continue
        if action == "entry":
            if symbol in active:
                errors.append(f"overlapping_entry:{symbol}")
            else:
                active[symbol] = row
            continue
        if action != "exit":
            continue
        entry = active.pop(symbol, None)
        if entry is None:
            errors.append(f"unmatched_exit:{symbol}")
            continue
        normalized = _normalized_return(entry, row)
        if normalized is None:
            errors.append(f"invalid_entry_allocation:{symbol}")
            continue
        completed.append({
            "entry_key": _entry_key(entry),
            "symbol": symbol,
            "entry_date": _date(entry.get("date")),
            "entry_price": round(_f(entry.get("price")), 6),
            "entry_regime": str(row.get("entry_regime") or entry.get("regime") or "unknown"),
            "exit_date": _date(row.get("date")),
            "exit_price": round(_f(row.get("price")), 6),
            "exit_reason": str(row.get("reason") or "unknown"),
            "return_pct": normalized,
        })
    return completed, sorted(set(errors))


def _index_lifecycles(rows: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str, float], List[Mapping[str, Any]]]:
    indexed: Dict[Tuple[str, str, float], List[Mapping[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        key = row.get("entry_key")
        if isinstance(key, tuple) and len(key) == 3:
            indexed[key].append(row)
    return dict(indexed)


def _pair_lifecycles(
    baseline_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    baseline = _index_lifecycles(baseline_rows)
    candidate = _index_lifecycles(candidate_rows)
    pairs: List[Dict[str, Any]] = []
    errors: List[str] = []
    for key in sorted(set(baseline) | set(candidate)):
        left = baseline.get(key, [])
        right = candidate.get(key, [])
        if len(left) != 1 or len(right) != 1:
            if left or right:
                prefix = "ambiguous_entry" if len(left) > 1 or len(right) > 1 else "unmatched_entry"
                errors.append(f"{prefix}:{key[0]}:{key[1]}:{key[2]:.6f}")
            continue
        current, proposed = left[0], right[0]
        delta = round(_f(proposed.get("return_pct")) - _f(current.get("return_pct")), 6)
        pairs.append({
            "observation_id": f"{key[0]}|{key[1]}|{key[2]:.6f}",
            "symbol": key[0],
            "entry_date": key[1],
            "entry_price": key[2],
            "entry_regime": current.get("entry_regime"),
            "baseline_exit_date": current.get("exit_date"),
            "baseline_exit_reason": current.get("exit_reason"),
            "baseline_return_pct": current.get("return_pct"),
            "candidate_exit_date": proposed.get("exit_date"),
            "candidate_exit_reason": proposed.get("exit_reason"),
            "candidate_return_pct": proposed.get("return_pct"),
            "return_delta_pct": delta,
            "exit_diverged": bool(
                current.get("exit_date") != proposed.get("exit_date")
                or current.get("exit_reason") != proposed.get("exit_reason")
                or current.get("exit_price") != proposed.get("exit_price")
            ),
        })
    return pairs, errors


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [_f(row.get(key)) for row in rows]
    return round(sum(values) / len(values), 6) if values else None


def _group_summary(rows: Sequence[Mapping[str, Any]], field: str) -> Dict[str, Any]:
    groups: Dict[str, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        groups[str(row.get(field) or "unknown")].append(row)
    return {
        name: {
            "observations": len(group),
            "exit_divergences": sum(bool(row.get("exit_diverged")) for row in group),
            "mean_return_delta_pct": _mean(group, "return_delta_pct"),
        }
        for name, group in sorted(groups.items())
    }


def _coverage(
    rows: Sequence[Mapping[str, Any]],
    available_dates: Sequence[Any],
    unmatched_entries: int,
) -> Dict[str, Any]:
    forward_dates = sorted({_date(value) for value in available_dates if _date(value) >= FREEZE_DATE})
    months = sorted({value[:7] for value in forward_dates})
    symbol_counts = collections.Counter(str(row.get("symbol") or "") for row in rows)
    largest = max(symbol_counts.values(), default=0)
    return {
        "available_forward_sessions": len(forward_dates),
        "calendar_months": len(months),
        "first_forward_session": forward_dates[0] if forward_dates else None,
        "last_forward_session": forward_dates[-1] if forward_dates else None,
        "largest_symbol_observation_share_pct": round(largest / max(1, len(rows)) * 100.0, 2),
        "unmatched_completed_entries": unmatched_entries,
        "exact_pairing_coverage_pct": round(
            len(rows) / max(1, len(rows) + unmatched_entries) * 100.0, 2
        ),
    }


def _criteria_results(
    rows: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    by_regime: Mapping[str, Any],
    stress_mean_delta: float | None,
) -> Dict[str, bool]:
    neutral = _d(by_regime.get("neutral"))
    defensive_count = sum(_f(_d(by_regime.get(name)).get("observations")) for name in ("defensive", "risk_off"))
    defensive_delta_rows = [row for row in rows if row.get("entry_regime") in {"defensive", "risk_off"}]
    return {
        "exact_matched_completed_lifecycles": len(rows) >= CRITERIA["minimum_exact_matched_completed_lifecycles"],
        "exit_divergences": sum(bool(row.get("exit_diverged")) for row in rows) >= CRITERIA["minimum_exit_divergences"],
        "forward_sessions": _f(coverage.get("available_forward_sessions")) >= CRITERIA["minimum_forward_sessions"],
        "calendar_months": _f(coverage.get("calendar_months")) >= CRITERIA["minimum_calendar_months"],
        "neutral_entries": _f(neutral.get("observations")) >= CRITERIA["minimum_neutral_entries"],
        "defensive_or_risk_off_entries": defensive_count >= CRITERIA["minimum_defensive_or_risk_off_entries"],
        "symbol_concentration": _f(coverage.get("largest_symbol_observation_share_pct"), 100.0) <= CRITERIA["maximum_single_symbol_share_pct"],
        "exact_pairing_coverage": _f(coverage.get("exact_pairing_coverage_pct")) >= CRITERIA["minimum_exact_pairing_coverage_pct"],
        "positive_mean_delta_at_8bps": (_mean(rows, "return_delta_pct") or -999.0) > CRITERIA["minimum_mean_return_delta_pct_at_8bps"],
        "nonnegative_mean_delta_at_25bps": stress_mean_delta is not None and stress_mean_delta >= CRITERIA["minimum_mean_return_delta_pct_at_25bps"],
        "nonnegative_neutral_delta": neutral.get("mean_return_delta_pct") is not None and _f(neutral.get("mean_return_delta_pct")) >= 0.0,
        "nonnegative_defensive_or_risk_off_delta": _mean(defensive_delta_rows, "return_delta_pct") is not None and (_mean(defensive_delta_rows, "return_delta_pct") or 0.0) >= 0.0,
    }


def build_report(
    baseline_simulation: Mapping[str, Any],
    candidate_simulation: Mapping[str, Any],
    available_dates: Sequence[Any],
    *,
    stress_baseline_simulation: Mapping[str, Any] | None = None,
    stress_candidate_simulation: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    baseline, baseline_errors = _lifecycles(baseline_simulation)
    candidate, candidate_errors = _lifecycles(candidate_simulation)
    paired, pair_errors = _pair_lifecycles(
        [row for row in baseline if row.get("entry_date", "") >= FREEZE_DATE],
        [row for row in candidate if row.get("entry_date", "") >= FREEZE_DATE],
    )
    stress_mean = None
    stress_errors: List[str] = []
    if stress_baseline_simulation is not None and stress_candidate_simulation is not None:
        stress_baseline, left_errors = _lifecycles(stress_baseline_simulation)
        stress_candidate, right_errors = _lifecycles(stress_candidate_simulation)
        stress_pairs, match_errors = _pair_lifecycles(
            [row for row in stress_baseline if row.get("entry_date", "") >= FREEZE_DATE],
            [row for row in stress_candidate if row.get("entry_date", "") >= FREEZE_DATE],
        )
        stress_mean = _mean(stress_pairs, "return_delta_pct")
        stress_errors = left_errors + right_errors + match_errors
    unmatched = [error for error in pair_errors if error.startswith("unmatched_entry:")]
    integrity_errors = sorted(set(
        baseline_errors
        + candidate_errors
        + [error for error in pair_errors if not error.startswith("unmatched_entry:")]
        + [error for error in stress_errors if not error.startswith("unmatched_entry:")]
    ))
    coverage = _coverage(paired, available_dates, len(unmatched))
    by_regime = _group_summary(paired, "entry_regime")
    checks = _criteria_results(paired, coverage, by_regime, stress_mean)
    eligible = bool(paired) and not integrity_errors
    all_criteria_met = eligible and all(checks.values())
    return {
        "status": "evidence_ready" if all_criteria_met else "collecting" if not integrity_errors else "inconclusive",
        "type": "hold_period_forward_shadow",
        "version": VERSION,
        "candidate_id": CANDIDATE_ID,
        "baseline_id": BASELINE_ID,
        "candidate_frozen_before_observation": True,
        "freeze_date": FREEZE_DATE,
        "transaction_cost_bps_per_side": TRANSACTION_COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": STRESS_COST_BPS_PER_SIDE,
        "exact_matched_completed_lifecycles": len(paired),
        "exit_divergences": sum(bool(row.get("exit_diverged")) for row in paired),
        "mean_return_delta_pct": _mean(paired, "return_delta_pct"),
        "stress_mean_return_delta_pct": stress_mean,
        "coverage": coverage,
        "by_regime": by_regime,
        "by_symbol": _group_summary(paired, "symbol"),
        "integrity": {
            "eligible": eligible,
            "errors": integrity_errors[:100],
            "ambiguous_or_unmatched_evidence_rejected": True,
            "full_recomputation_from_frozen_inputs": True,
        },
        "predeclared_criteria": dict(CRITERIA),
        "criteria_results": checks,
        "all_criteria_met": all_criteria_met,
        "automatic_promotion": False,
        "observations": paired[-OBSERVATION_LIMIT:],
        "authority": {
            "isolated_research_only": True,
            "read_only_comparator": True,
            "writes_production_state": False,
            "changes_runtime_exits": False,
            "changes_strategy_or_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_or_cancels_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }
