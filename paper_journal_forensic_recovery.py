"""Read-only forensic recovery candidate from the append-only trade journal.

Before a clean accounting epoch is established, this builds a deduplicated
execution candidate from /data/trade_journal.json and checks whether it can
reconstruct a complete, economically plausible paper account.

After the historical decision is resolved in favor of a clean epoch, the old
journal is treated as archived forensic evidence rather than an active recovery
warning.  This module never mutates state, clears halts, or places orders.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

VERSION = "paper-journal-forensic-recovery-2026-08-10-v2-clean-epoch"


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _semantic_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        str(row.get("time") or row.get("timestamp") or row.get("ts_local") or ""),
        str(row.get("action") or "").lower(),
        str(row.get("symbol") or row.get("ticker") or "").upper(),
        str(row.get("side") or "").lower(),
        round(_f(row.get("shares", row.get("qty", row.get("quantity"))), 0.0), 9),
        round(_f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0), 6),
        str(row.get("exit_reason") or ""),
    )


def _load_journal() -> Tuple[Dict[str, Any], str | None]:
    try:
        import trade_journal as tj
        path = str(getattr(tj, "TRADE_JOURNAL_FILE", "") or "")
        if not path:
            return {}, "journal_path_missing"
        with open(path, "r", encoding="utf-8") as handle:
            obj = json.load(handle)
        return (obj if isinstance(obj, dict) else {}), None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _candidate_rows(journal: Dict[str, Any]) -> List[Dict[str, Any]]:
    supported = {"entry", "exit", "partial_exit"}
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in _l(journal.get("trades")):
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").lower().strip()
        if action not in supported:
            continue
        key = _semantic_key(raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(raw))
    return out


def _clean_epoch_disposition(core: Any) -> Dict[str, Any] | None:
    pf = _portfolio(core)
    epoch = _d(pf.get("paper_accounting_epoch"))
    if not bool(epoch.get("clean_start")) or epoch.get("historical_recovery_decision") != "clean_epoch":
        return None
    journal, error = _load_journal()
    return {
        "status": "archived",
        "overall": "pass",
        "type": "paper_journal_forensic_recovery_status",
        "version": VERSION,
        "journal_available": not bool(error),
        "journal_trade_rows": len(_l(journal.get("trades"))),
        "deduplicated_execution_rows": len(_candidate_rows(journal)),
        "entry_rows": sum(1 for row in _candidate_rows(journal) if str(row.get("action") or "").lower() == "entry"),
        "exit_rows": sum(1 for row in _candidate_rows(journal) if str(row.get("action") or "").lower() in {"exit", "partial_exit"}),
        "coverage_complete": None,
        "coverage_issue_count": int(epoch.get("journal_coverage_issue_count") or 0),
        "economic_issue_count": int(epoch.get("journal_economic_issue_count") or 0),
        "candidate_cash": None,
        "candidate_equity": None,
        "candidate_open_positions": [],
        "trusted_recovery_candidate": False,
        "decision_complete": True,
        "historical_recovery_disposition": "archived_after_incomplete_coverage",
        "clean_epoch_id": epoch.get("id"),
        "forensic_archive_dir": epoch.get("forensic_archive_dir"),
        "error": error,
        "authority": {
            "reporting_only": True,
            "repairs_state": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    disposition = _clean_epoch_disposition(core)
    if disposition is not None:
        return disposition

    journal, error = _load_journal()
    rows = _candidate_rows(journal)
    entries = sum(1 for row in rows if str(row.get("action") or "").lower() == "entry")
    exits = sum(1 for row in rows if str(row.get("action") or "").lower() in {"exit", "partial_exit"})
    if error:
        return {
            "status": "warn", "overall": "warn", "version": VERSION,
            "journal_available": False, "error": error,
            "authority": {"reporting_only": True, "repairs_state": False, "places_orders": False},
        }

    try:
        import paper_ledger_matched_exit_guard as matched
        pf = dict(_portfolio(core))
        pf["trades"] = rows
        rebuilt = matched.analyze_ledger(pf, core)
    except Exception as exc:
        rebuilt = {"coverage_complete": False, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    economic_issue_count = int(rebuilt.get("economic_issue_count") or 0)
    coverage_issue_count = int(rebuilt.get("coverage_issue_count") or 0)
    coverage_complete = bool(rebuilt.get("coverage_complete"))
    trustworthy = coverage_complete and economic_issue_count == 0 and coverage_issue_count == 0
    return {
        "status": "ok" if trustworthy else "warn",
        "overall": "pass" if trustworthy else "warn",
        "type": "paper_journal_forensic_recovery_status",
        "version": VERSION,
        "journal_available": True,
        "journal_trade_rows": len(_l(journal.get("trades"))),
        "deduplicated_execution_rows": len(rows),
        "entry_rows": entries,
        "exit_rows": exits,
        "coverage_complete": coverage_complete,
        "coverage_issue_count": coverage_issue_count,
        "economic_issue_count": economic_issue_count,
        "candidate_cash": rebuilt.get("cash"),
        "candidate_equity": rebuilt.get("equity"),
        "candidate_open_positions": sorted(_d(rebuilt.get("open_positions")).keys()),
        "trusted_recovery_candidate": trustworthy,
        "decision_complete": False,
        "historical_recovery_disposition": "pending",
        "authority": {
            "reporting_only": True,
            "repairs_state": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return status_payload(core)
