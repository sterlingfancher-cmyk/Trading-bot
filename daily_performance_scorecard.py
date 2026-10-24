"""Pure, read-only daily performance scorecard construction.

This module deliberately does not load or write trading state.  Callers supply
dated canonical execution rows and separately persist the returned research
checkpoint.  Canonical outcomes remain visible even when an integrity finding
excludes a lifecycle from promotion/research metrics.
"""
from __future__ import annotations

import copy
import math
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Sequence

VERSION = "daily-performance-scorecard-2026-10-23-v1"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _metrics(trades: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    pnls = [_number(trade.get("pnl_dollars")) for trade in trades]
    pnls = [pnl for pnl in pnls if pnl is not None]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    flats = [pnl for pnl in pnls if pnl == 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    by_side: Dict[str, Dict[str, Any]] = {}
    for side in ("long", "short"):
        side_trades = [trade for trade in trades if trade.get("side") == side]
        side_pnls = [_number(trade.get("pnl_dollars")) for trade in side_trades]
        side_pnls = [pnl for pnl in side_pnls if pnl is not None]
        by_side[side] = {
            "completed_trades": len(side_trades),
            "realized_pnl": _rounded(sum(side_pnls)),
            "wins": sum(pnl > 0 for pnl in side_pnls),
            "losses": sum(pnl < 0 for pnl in side_pnls),
        }
    return {
        "completed_matched_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "flat_trades": len(flats),
        "realized_pnl": _rounded(sum(pnls)),
        "average_win": _rounded(sum(wins) / len(wins)) if wins else None,
        "average_loss": _rounded(sum(losses) / len(losses)) if losses else None,
        "win_rate_pct": _rounded(100.0 * len(wins) / len(pnls)) if pnls else None,
        "profit_factor": _rounded(gross_profit / gross_loss) if gross_loss else (None if not gross_profit else "infinite"),
        "largest_loss": _rounded(min(losses)) if losses else None,
        "long_short": by_side,
    }


def _match_lifecycles(rows: Sequence[Mapping[str, Any]]) -> tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Match by immutable execution_path_id and count only the final exit."""
    paths: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"entries": [], "partials": [], "exits": []})
    unmatched: List[str] = []
    # Journal/state rows are already append ordered. Preserve that ordering:
    # timestamps may be ISO strings, so numeric coercion can otherwise reorder
    # an entry behind its exit when execution IDs sort differently.
    for row in rows:
        action = str(row.get("action") or "").lower()
        if action not in {"entry", "partial_exit", "exit"}:
            continue
        path_id = str(row.get("execution_path_id") or "").strip()
        if not path_id:
            unmatched.append(str(row.get("execution_id") or "missing_execution_path_id"))
            continue
        if action == "entry":
            paths[path_id]["entries"].append(row)
        elif action == "partial_exit":
            paths[path_id]["partials"].append(row)
        else:
            paths[path_id]["exits"].append(row)

    completed: List[Dict[str, Any]] = []
    open_paths: List[str] = []
    for path_id, events in paths.items():
        if events["entries"] and not events["exits"]:
            open_paths.append(path_id)
            continue
        if not events["entries"] or not events["exits"]:
            unmatched.append(path_id)
            continue
        entry = events["entries"][0]
        final_exit = events["exits"][-1]
        partial_pnl = sum(_number(row.get("pnl_dollars")) or 0.0 for row in events["partials"])
        final_pnl = _number(final_exit.get("pnl_dollars"))
        if final_pnl is None:
            unmatched.append(path_id)
            continue
        completed.append({
            "execution_path_id": path_id,
            "symbol": str(entry.get("symbol") or final_exit.get("symbol") or "").upper(),
            "side": str(entry.get("side") or final_exit.get("side") or "").lower(),
            "entry_time": entry.get("time"),
            "exit_time": final_exit.get("time"),
            "entry_price": _number(entry.get("price")),
            "exit_price": _number(final_exit.get("price")),
            "pnl_dollars": _rounded(partial_pnl + final_pnl),
            "partial_exit_count": len(events["partials"]),
            "exit_reason": final_exit.get("exit_reason"),
            "execution_ids": [
                event.get("execution_id")
                for event in [entry] + events["partials"] + [final_exit]
            ],
        })
    return completed, sorted(set(unmatched)), sorted(set(open_paths))


def build_session_scorecard(
    *,
    session_date: str,
    observed_at: str,
    accounting_epoch_id: str,
    journal_rows: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    excluded_execution_path_ids: Iterable[str] = (),
    account_snapshot: Mapping[str, Any] | None = None,
    expected_execution_count: int | None = None,
) -> Dict[str, Any]:
    """Build one dated observation without mutating supplied rows or state."""
    date.fromisoformat(session_date)
    source_rows = copy.deepcopy(list(journal_rows))
    epoch_rows = [row for row in source_rows if row.get("accounting_epoch_id") == accounting_epoch_id]
    dated_rows = [row for row in epoch_rows if str(row.get("session_date") or "") == session_date]
    excluded = set(excluded_execution_path_ids)
    completed, unmatched, open_paths = _match_lifecycles(dated_rows)
    canonical_metrics = _metrics(completed)
    eligible = [trade for trade in completed if trade["execution_path_id"] not in excluded]
    research_metrics = _metrics(eligible)
    excluded_trades = [trade for trade in completed if trade["execution_path_id"] in excluded]
    actions = Counter(str(row.get("action") or "").lower() for row in dated_rows)
    exit_reasons = Counter(
        str(row.get("exit_reason") or "unknown")
        for row in dated_rows
        if str(row.get("action") or "").lower() in {"partial_exit", "exit"}
    )
    snapshot = dict(account_snapshot or {})
    expected_ok = expected_execution_count is not None and len(dated_rows) == expected_execution_count
    required_close_fields = ("canonical_daily_pnl", "equity", "unrealized_pnl", "gross_exposure")
    account_close_complete = all(_number(snapshot.get(key)) is not None for key in required_close_fields)
    fee_coverage_known = str(snapshot.get("fee_slippage_coverage") or "unknown") != "unknown"
    complete = bool(dated_rows) and expected_ok and not unmatched and account_close_complete and fee_coverage_known
    canonical_daily_pnl = _number(snapshot.get("canonical_daily_pnl"))
    if canonical_daily_pnl is not None and canonical_metrics["realized_pnl"] is not None:
        reconciliation_delta = _rounded(canonical_daily_pnl - canonical_metrics["realized_pnl"])
    else:
        reconciliation_delta = None
    proven_drivers: List[Dict[str, Any]] = []
    if excluded_trades:
        proven_drivers.append({
            "category": "bad_data_or_execution",
            "status": "proven_integrity_exclusion",
            "evidence": [trade["execution_path_id"] for trade in excluded_trades],
        })
    largest = canonical_metrics.get("largest_loss")
    total = canonical_metrics.get("realized_pnl")
    hypotheses: List[Dict[str, Any]] = []
    if largest is not None and total is not None and total < 0 and abs(largest) >= 0.5 * abs(total):
        hypotheses.append({
            "category": "position_sizing_or_exposure",
            "status": "hypothesis",
            "evidence": "largest valid loss supplies at least half of session net loss; causation not established",
        })
    return {
        "schema_version": VERSION,
        "session_date": session_date,
        "observed_at": observed_at,
        "accounting_epoch_id": accounting_epoch_id,
        "provenance": copy.deepcopy(dict(provenance)),
        "session_completeness": {
            "complete": complete,
            "execution_rows_observed": len(dated_rows),
            "expected_execution_rows": expected_execution_count,
            "execution_lifecycle_complete": bool(dated_rows) and expected_ok and not unmatched,
            "account_close_complete": account_close_complete,
            "fee_slippage_coverage_known": fee_coverage_known,
            "unmatched_execution_path_ids": unmatched,
            "open_execution_path_ids": open_paths,
            "missing_fields": [
                key
                for key in (
                    "canonical_daily_pnl",
                    "equity",
                    "unrealized_pnl",
                    "gross_exposure",
                    "fees",
                    "slippage",
                )
                if _number(snapshot.get(key)) is None
            ],
        },
        "event_counts": {
            "entries": actions["entry"],
            "final_exits": actions["exit"],
            "partial_exits": actions["partial_exit"],
        },
        "canonical_reporting": {
            **canonical_metrics,
            "canonical_daily_pnl": _rounded(canonical_daily_pnl),
            "daily_pnl_reconciliation_delta": reconciliation_delta,
            "unrealized_pnl": _rounded(_number(snapshot.get("unrealized_pnl"))),
            "equity": _rounded(_number(snapshot.get("equity"))),
            "gross_exposure": _rounded(_number(snapshot.get("gross_exposure"))),
            "fees": _rounded(_number(snapshot.get("fees"))),
            "slippage": _rounded(_number(snapshot.get("slippage"))),
            "fee_slippage_coverage": str(snapshot.get("fee_slippage_coverage") or "unknown"),
            "exit_reasons": dict(sorted(exit_reasons.items())),
            "completed_trade_lifecycles": completed,
        },
        "eligible_research_metrics": research_metrics,
        "research_exclusions": [{**trade, "reason": "suspect_price_or_execution_integrity"} for trade in excluded_trades],
        "loss_driver_classification": {
            "proven": proven_drivers,
            "hypotheses": hypotheses,
            "unclassified_categories": ["entry_selection", "exit_timing", "market_regime"],
        },
        "guardrails": {
            "source_rows_mutated": False,
            "balance_change_used_as_pnl": False,
            "partial_exits_counted_as_separate_wins": False,
            "cross_epoch_comparison_allowed": False,
            "automatic_promotion": False,
        },
    }


def upsert_scorecard(checkpoint: Mapping[str, Any] | None, observation: Mapping[str, Any], expected_session_dates: Sequence[str]) -> Dict[str, Any]:
    """Retain earlier observations and replace only the same dated session."""
    result = copy.deepcopy(dict(checkpoint or {}))
    observations = [
        copy.deepcopy(row) for row in result.get("observations", [])
        if row.get("session_date") != observation.get("session_date")
    ]
    observations.append(copy.deepcopy(dict(observation)))
    observations.sort(key=lambda row: row["session_date"])
    result.update({"schema_version": VERSION, "observations": observations})
    present = {row["session_date"] for row in observations}
    result["missing_sessions"] = [day for day in expected_session_dates if day not in present]
    same_epoch_complete = [
        row for row in observations
        if row.get("accounting_epoch_id") == observation.get("accounting_epoch_id")
        and row.get("session_completeness", {}).get("complete")
    ]
    for window in (5, 20):
        sample = same_epoch_complete[-window:]
        metrics = [row.get("eligible_research_metrics", {}) for row in sample]
        wins = sum(int(metric.get("wins") or 0) for metric in metrics)
        losses = sum(int(metric.get("losses") or 0) for metric in metrics)
        gross_profit = sum((_number(metric.get("average_win")) or 0.0) * int(metric.get("wins") or 0) for metric in metrics)
        gross_loss = abs(sum((_number(metric.get("average_loss")) or 0.0) * int(metric.get("losses") or 0) for metric in metrics))
        loss_values = [_number(metric.get("largest_loss")) for metric in metrics]
        loss_values = [value for value in loss_values if value is not None]
        exposures = [_number(row.get("canonical_reporting", {}).get("gross_exposure")) for row in sample]
        exposures = [value for value in exposures if value is not None]
        side_totals: Dict[str, Dict[str, Any]] = {}
        for side in ("long", "short"):
            cards = [metric.get("long_short", {}).get(side, {}) for metric in metrics]
            side_totals[side] = {
                "completed_trades": sum(int(card.get("completed_trades") or 0) for card in cards),
                "realized_pnl": _rounded(sum(_number(card.get("realized_pnl")) or 0.0 for card in cards)),
            }
        result[f"rolling_{window}_session"] = {
            "available_comparable_sessions": len(sample),
            "requested_sessions": window,
            "session_dates": [row["session_date"] for row in sample],
            "missing_sessions": result["missing_sessions"],
            "completed_matched_trades": sum(int(metric.get("completed_matched_trades") or 0) for metric in metrics),
            "eligible_realized_pnl": _rounded(sum(_number(metric.get("realized_pnl")) or 0.0 for metric in metrics)),
            "wins": wins,
            "losses": losses,
            "average_win": _rounded(gross_profit / wins) if wins else None,
            "average_loss": _rounded(-gross_loss / losses) if losses else None,
            "win_rate_pct": _rounded(100.0 * wins / (wins + losses)) if wins + losses else None,
            "profit_factor": _rounded(gross_profit / gross_loss) if gross_loss else (None if not gross_profit else "infinite"),
            "largest_loss": _rounded(min(loss_values)) if loss_values else None,
            "long_short": side_totals,
            "average_gross_exposure": _rounded(sum(exposures) / len(exposures)) if exposures else None,
            "exposure_sample_count": len(exposures),
            "insufficient_for_full_window": len(sample) < window,
        }
    return result
