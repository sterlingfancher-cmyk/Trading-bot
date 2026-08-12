"""Reporting-only bridge for bounded Stable Paper accounting defect evidence.

When accounting coverage fails, the compact daily audit needs enough evidence to
identify whether an unmatched exit has a real pre-existing entry row without
mutating state or inventing executions.  This bridge exposes all bounded coverage
issues plus a few earlier same-symbol entry-like rows from the persisted trade
mirror for forensic comparison.

No state repair, execution, strategy, sizing, risk, live, or ML authority is
changed.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List

VERSION = "daily-audit-accounting-issue-bridge-2026-08-12-v2-entry-evidence"
_APPLIED = False
_MAX_ISSUES = 10
_MAX_CANDIDATES_PER_ISSUE = 3


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _first_safe(value: Any) -> Any:
    rows = _l(value)
    return rows[0] if rows else None


def _portfolio(core: Any = None) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _entry_like(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or "").lower().strip()
    side = str(row.get("side") or "").lower().strip()
    row_type = str(row.get("type") or "").lower().strip()
    return (
        action in {"entry", "buy", "open", "open_long", "open_short"}
        or side in {"buy", "b"}
        or row_type == "paper_market_surge_deployment"
    )


def _safe_trade_evidence(index: int, row: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "action", "side", "source", "type", "symbol", "ticker", "qty", "shares",
        "quantity", "price", "entry", "entry_price", "fill_price", "time",
        "timestamp", "ts_local", "execution_id", "accounting_epoch_id",
        "canonical_ledger_version", "entry_tag", "trade_authority",
    )
    out = {"trade_index": index}
    for key in keys:
        if key in row:
            out[key] = row.get(key)
    return out


def _candidate_entries(core: Any, issue: Dict[str, Any]) -> List[Dict[str, Any]]:
    symbol = str(issue.get("symbol") or "").upper().strip()
    issue_index = issue.get("trade_index")
    try:
        before = int(issue_index)
    except Exception:
        before = 10**9
    if not symbol:
        return []

    trades = _l(_portfolio(core).get("trades"))
    found: List[Dict[str, Any]] = []
    for index, raw in enumerate(trades):
        if index >= before or not isinstance(raw, dict):
            continue
        raw_symbol = str(raw.get("symbol") or raw.get("ticker") or "").upper().strip()
        if raw_symbol != symbol or not _entry_like(raw):
            continue
        found.append(_safe_trade_evidence(index, raw))
    return found[-_MAX_CANDIDATES_PER_ISSUE:]


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import final_daily_audit_compactor as compactor
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(compactor, "compact_payload", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "compact_payload_missing"}

    if getattr(current, "_accounting_issue_bridge_version", None) == VERSION:
        _APPLIED = True
        return status_payload()

    prior = getattr(current, "_accounting_issue_bridge_prior", current)

    @functools.wraps(prior)
    def wrapped(payload: Dict[str, Any], runtime_core: Any = None) -> Dict[str, Any]:
        out = prior(payload, runtime_core)
        if not isinstance(out, dict):
            return out

        sections = _d(payload.get("sections"))
        integrity = _d(sections.get("10b_market_data_and_path_integrity"))
        accounting = _d(integrity.get("paper_accounting_integrity"))
        rebuilt = _d(accounting.get("reconstructed"))
        economics = _d(integrity.get("paper_ledger_economic_integrity"))

        coverage_issues = _l(rebuilt.get("coverage_issues"))[:_MAX_ISSUES]
        evidence = []
        for issue in coverage_issues:
            if not isinstance(issue, dict):
                continue
            evidence.append({
                "issue": issue,
                "prior_same_symbol_entry_candidates": _candidate_entries(runtime_core or core, issue),
            })

        target = _d(out.get("accounting_integrity"))
        target["first_coverage_issue"] = _first_safe(coverage_issues)
        target["first_economic_issue"] = _first_safe(
            economics.get("economic_issues") or rebuilt.get("economic_issues")
        )
        target["coverage_issues"] = coverage_issues
        target["unmatched_exit_entry_evidence"] = evidence
        target["reconstructed_open_positions"] = sorted(
            str(symbol) for symbol in _d(rebuilt.get("open_positions")).keys()
        )
        target["parsed_trade_rows"] = rebuilt.get("parsed_trade_rows")
        out["accounting_integrity"] = target
        return out

    wrapped._accounting_issue_bridge_version = VERSION  # type: ignore[attr-defined]
    wrapped._accounting_issue_bridge_prior = prior  # type: ignore[attr-defined]
    compactor.compact_payload = wrapped
    _APPLIED = True
    return status_payload()


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "reporting_only": True,
        "surfaces_bounded_coverage_issues": True,
        "surfaces_prior_same_symbol_entry_candidates": True,
        "max_issues": _MAX_ISSUES,
        "max_candidates_per_issue": _MAX_CANDIDATES_PER_ISSUE,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
