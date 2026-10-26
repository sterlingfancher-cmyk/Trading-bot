"""Pure adapter for fail-closed, session-scoped performance evidence.

The adapter consumes already archived JSON values.  It does not import the
paper runner, load runtime state, write evidence, or change any authority.  Its
purpose is to make the limits of the available evidence explicit before a
scorecard or performance experiment treats a session as eligible.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo


VERSION = "session-performance-evidence-2026-10-26-v1"
CHICAGO = ZoneInfo("America/Chicago")
STATE_PRIMARY_SUFFIX = "state.json:trades"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _local_datetime(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=CHICAGO)
    return parsed.astimezone(CHICAGO)


def _row_session_date(row: Mapping[str, Any]) -> str | None:
    explicit = str(row.get("session_date") or "").strip()
    if explicit:
        return explicit
    parsed = _local_datetime(row.get("recorded_local") or row.get("time"))
    return parsed.date().isoformat() if parsed else None


def verify_canonical_chain(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    errors: list[str] = []
    previous = ""
    execution_ids: set[str] = set()
    for index, source in enumerate(rows, start=1):
        row = dict(source)
        execution_id = str(row.get("execution_id") or "")
        if not execution_id:
            errors.append(f"row_{index}:missing_execution_id")
        elif execution_id in execution_ids:
            errors.append(f"row_{index}:duplicate_execution_id")
        execution_ids.add(execution_id)
        if str(row.get("previous_event_hash") or "") != previous:
            errors.append(f"row_{index}:previous_hash_mismatch")
        stored = str(row.pop("event_hash", "") or "")
        row.pop("previous_event_hash", None)
        expected = hashlib.sha256((previous + "|" + _canonical_json(row)).encode("utf-8")).hexdigest()
        if not stored or stored != expected:
            errors.append(f"row_{index}:event_hash_mismatch")
        previous = stored
    return {
        "valid": bool(rows) and not errors,
        "rows": len(rows),
        "last_event_hash": previous or None,
        "errors": errors,
    }


def _join_session_rows(
    canonical_rows: Sequence[Mapping[str, Any]],
    journal_rows: Sequence[Mapping[str, Any]],
    session_date: str,
    epoch_id: str,
) -> tuple[list[Dict[str, Any]], list[str]]:
    errors: list[str] = []
    canonical = [
        dict(row) for row in canonical_rows
        if str(row.get("accounting_epoch_id") or "") == epoch_id
        and _row_session_date(row) == session_date
    ]
    journal_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in journal_rows:
        execution_id = str(row.get("execution_id") or "")
        if execution_id:
            journal_by_id[execution_id].append(row)

    joined: list[Dict[str, Any]] = []
    for ordinal, ledger in enumerate(canonical, start=1):
        execution_id = str(ledger.get("execution_id") or "")
        matches = journal_by_id.get(execution_id, [])
        if len(matches) != 1:
            errors.append(f"execution_id:{execution_id}:journal_match_count:{len(matches)}")
            continue
        journal = dict(matches[0])
        if not str(journal.get("journal_source") or "").endswith(STATE_PRIMARY_SUFFIX):
            errors.append(f"execution_id:{execution_id}:journal_source_not_state_primary")
            continue
        for key in ("accounting_epoch_id", "action", "symbol", "side"):
            if str(ledger.get(key) or "").lower() != str(journal.get(key) or "").lower():
                errors.append(f"execution_id:{execution_id}:{key}_mismatch")
        for key in ("price", "shares"):
            if _number(ledger.get(key)) != _number(journal.get(key)):
                errors.append(f"execution_id:{execution_id}:{key}_mismatch")
        combined = copy.deepcopy(journal)
        combined["canonical_ordinal"] = ordinal
        combined["event_hash"] = ledger.get("event_hash")
        combined["previous_event_hash"] = ledger.get("previous_event_hash")
        joined.append(combined)
    return joined, errors


def _lifecycles(rows: Sequence[Mapping[str, Any]]) -> tuple[list[Dict[str, Any]], list[str]]:
    paths: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    for row in rows:
        path_id = str(row.get("execution_path_id") or "").strip()
        if not path_id:
            errors.append(f"execution_id:{row.get('execution_id')}:missing_execution_path_id")
            continue
        paths[path_id].append(row)

    complete: list[Dict[str, Any]] = []
    for path_id, events in paths.items():
        events = sorted(events, key=lambda row: int(row.get("canonical_ordinal") or 0))
        entries = [row for row in events if str(row.get("action") or "").lower() == "entry"]
        partials = [row for row in events if str(row.get("action") or "").lower() == "partial_exit"]
        exits = [row for row in events if str(row.get("action") or "").lower() == "exit"]
        if len(entries) != 1 or len(exits) != 1:
            errors.append(f"execution_path_id:{path_id}:incomplete_or_ambiguous_lifecycle")
            continue
        pnl_values = [_number(row.get("pnl_dollars")) for row in partials + exits]
        if any(value is None for value in pnl_values):
            errors.append(f"execution_path_id:{path_id}:missing_gross_pnl")
            continue
        complete.append({
            "execution_path_id": path_id,
            "symbol": str(entries[0].get("symbol") or "").upper(),
            "side": str(entries[0].get("side") or "").lower(),
            "admission_ordinal": int(entries[0].get("canonical_ordinal") or 0),
            "execution_ids": [row.get("execution_id") for row in events],
            "partial_exit_count": len(partials),
            "gross_pnl": round(sum(value or 0.0 for value in pnl_values), 6),
            "exit_reason": exits[0].get("exit_reason"),
        })
    complete.sort(key=lambda row: row["admission_ordinal"])
    return complete, errors


def _close_observation(
    observations: Sequence[Mapping[str, Any]],
    session_date: str,
    epoch_id: str,
    close_window: tuple[str, str],
) -> tuple[Dict[str, Any] | None, list[str]]:
    start = dt.datetime.combine(dt.date.fromisoformat(session_date), dt.time.fromisoformat(close_window[0]), CHICAGO)
    end = dt.datetime.combine(dt.date.fromisoformat(session_date), dt.time.fromisoformat(close_window[1]), CHICAGO)
    eligible: list[tuple[dt.datetime, Dict[str, Any]]] = []
    for source in observations:
        row = dict(source)
        observed = _local_datetime(row.get("observed_at") or row.get("mirrored_local") or row.get("generated_local"))
        if observed and start <= observed <= end and str(row.get("accounting_epoch_id") or "") == epoch_id:
            eligible.append((observed, row))
    if not eligible:
        return None, ["session_close_observation_missing"]
    eligible.sort(key=lambda item: item[0])
    observation = eligible[-1][1]
    missing = [key for key in ("equity", "unrealized_pnl", "gross_exposure") if _number(observation.get(key)) is None]
    return observation, [f"session_close_missing:{key}" for key in missing]


def build_session_evidence(
    *,
    session_date: str,
    accounting_epoch_id: str,
    canonical_rows: Sequence[Mapping[str, Any]],
    journal_rows: Sequence[Mapping[str, Any]],
    account_observations: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    explicit_costs: Mapping[str, Mapping[str, Any]] | None = None,
    suspect_execution_path_ids: Iterable[str] = (),
    close_window: tuple[str, str] = ("15:55:00", "16:10:00"),
) -> Dict[str, Any]:
    """Build evidence without mutating inputs or inferring missing values."""
    dt.date.fromisoformat(session_date)
    ledger = copy.deepcopy(list(canonical_rows))
    journal = copy.deepcopy(list(journal_rows))
    observations = copy.deepcopy(list(account_observations))
    chain = verify_canonical_chain(ledger)
    joined, join_errors = _join_session_rows(ledger, journal, session_date, accounting_epoch_id)
    lifecycles, lifecycle_errors = _lifecycles(joined)
    close, close_errors = _close_observation(observations, session_date, accounting_epoch_id, close_window)

    costs = copy.deepcopy(dict(explicit_costs or {}))
    cost_errors: list[str] = []
    for row in joined:
        execution_id = str(row.get("execution_id") or "")
        item = costs.get(execution_id)
        if not isinstance(item, Mapping) or _number(item.get("fees")) is None or _number(item.get("slippage")) is None:
            cost_errors.append(f"execution_id:{execution_id}:costs_missing")
    cost_coverage_complete = bool(joined) and not cost_errors

    suspect = set(suspect_execution_path_ids)
    eligible = [row for row in lifecycles if row["execution_path_id"] not in suspect]
    excluded = [dict(row, exclusion_reason="suspect_price_or_execution_integrity") for row in lifecycles if row["execution_path_id"] in suspect]
    gross = round(sum(row["gross_pnl"] for row in lifecycles), 6) if lifecycles else None
    eligible_gross = round(sum(row["gross_pnl"] for row in eligible), 6) if eligible else None
    total_costs = None
    net_after_costs = None
    if cost_coverage_complete:
        joined_ids = {str(row.get("execution_id") or "") for row in joined}
        total_costs = round(sum(
            (_number(costs[execution_id].get("fees")) or 0.0)
            + (_number(costs[execution_id].get("slippage")) or 0.0)
            for execution_id in joined_ids
        ), 6)
        net_after_costs = round((gross or 0.0) - total_costs, 6)

    errors = list(chain["errors"]) + join_errors + lifecycle_errors + close_errors + cost_errors
    evidence_complete = bool(chain["valid"] and joined and not errors)
    return {
        "schema_version": VERSION,
        "session_date": session_date,
        "accounting_epoch_id": accounting_epoch_id,
        "provenance": copy.deepcopy(dict(provenance)),
        "canonical_chain": chain,
        "evidence_complete": evidence_complete,
        "errors": errors,
        "execution_rows": joined,
        "completed_lifecycles": lifecycles,
        "gross_realized_pnl": gross,
        "eligible_gross_realized_pnl": eligible_gross,
        "research_exclusions": excluded,
        "session_close": close,
        "canonical_daily_pnl": None,
        "cost_coverage_complete": cost_coverage_complete,
        "total_explicit_costs": total_costs,
        "net_pnl_after_costs": net_after_costs,
        "admission_order": {
            "scope": "executed_admission_order_only",
            "complete_entry_universe": False,
            "rows": [
                {key: row.get(key) for key in ("admission_ordinal", "execution_path_id", "symbol", "side")}
                for row in lifecycles
            ],
        },
        "research_eligibility": {
            "eligible": False,
            "reason": "complete_ordered_admission_universe_unavailable",
            "promotion_allowed": False,
        },
        "guardrails": {
            "runtime_imported": False,
            "state_or_history_written": False,
            "balance_change_used_as_pnl": False,
            "partial_exits_counted_as_separate_wins": False,
            "missing_costs_treated_as_zero": False,
            "suspect_rows_deleted": False,
        },
    }
