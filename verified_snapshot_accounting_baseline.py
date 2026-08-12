"""Accounting adapter for a verified snapshot epoch with an open paper position.

The 2026-08-12 recovery cannot honestly restart from a zero-position baseline:
independent market evidence proves that the catastrophic LRCX 36.26 paper exit
was a bad tick and the remaining 3.42486-share lot must be restored.  This
adapter lets the existing bidirectional reconciler start from a verified cash +
open-lot snapshot while keeping all future executions on the canonical ledger.

No strategy, sizing, risk-limit, live, or ML authority is changed.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

VERSION = "verified-snapshot-accounting-baseline-2026-08-12-v1"
_APPLIED = False


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


def _snapshot(pf: Dict[str, Any]) -> Dict[str, Any]:
    epoch = _d(pf.get("paper_accounting_epoch"))
    if str(epoch.get("baseline_type") or "") != "verified_snapshot_with_open_position":
        return {}
    snap = _d(epoch.get("verified_snapshot_baseline"))
    return snap if bool(snap.get("verified", False)) else {}


def _synthetic_entry_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for symbol, raw in _d(snapshot.get("positions")).items():
        pos = _d(raw)
        side = str(pos.get("side") or "long").lower().strip()
        qty = _f(pos.get("qty", pos.get("shares")), 0.0)
        entry = _f(pos.get("entry_price", pos.get("entry")), 0.0)
        if side not in {"long", "short"} or qty <= 0.0 or entry <= 0.0:
            continue
        out.append({
            "action": "entry",
            "symbol": str(symbol).upper().strip(),
            "side": side,
            "shares": qty,
            "price": entry,
            "timestamp": str(snapshot.get("started_utc") or snapshot.get("started_local") or ""),
            "verified_snapshot_synthetic_opening_lot": True,
        })
    return out


def _adjust_issue_indexes(rows: Any, synthetic_count: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in _l(rows):
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        try:
            idx = int(row.get("trade_index"))
            row["trade_index"] = idx - synthetic_count
            if row["trade_index"] < 0:
                row["trade_index"] = None
                row["baseline_issue"] = True
        except Exception:
            pass
        out.append(row)
    return out


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import paper_bidirectional_accounting_guard as bidirectional
        import paper_accounting_integrity_guard as accounting
        import paper_ledger_matched_exit_guard as matched
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(bidirectional, "analyze_ledger", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "bidirectional_analyze_missing"}
    if getattr(current, "_verified_snapshot_baseline_version", None) == VERSION:
        _APPLIED = True
        accounting.reconstruct_from_ledger = current
        matched.analyze_ledger = current
        return status_payload(core)

    prior = getattr(current, "_verified_snapshot_baseline_prior", current)

    def wrapped(pf: Dict[str, Any], runtime_core: Any = None) -> Dict[str, Any]:
        snap = _snapshot(pf if isinstance(pf, dict) else {})
        if not snap:
            return prior(pf, runtime_core)

        synthetic = _synthetic_entry_rows(snap)
        if not synthetic and _d(snap.get("positions")):
            return {
                "status": "partial",
                "coverage_complete": False,
                "parsed_trade_rows": 0,
                "ignored_trade_rows": 1,
                "coverage_issues": [{"reason": "verified_snapshot_position_invalid"}],
                "coverage_issue_count": 1,
                "economic_issues": [],
                "economic_issue_count": 0,
                "accounting_model": "bidirectional_margin_v1",
                "supports_long_short": True,
                "baseline_type": "verified_snapshot_with_open_position",
            }

        working = copy.deepcopy(pf)
        actual_trades = _l(working.get("trades"))
        reserved = sum(_f(row.get("shares")) * _f(row.get("price")) for row in synthetic)
        baseline_cash = _f(snap.get("cash"), 0.0)
        working["initial_cash"] = baseline_cash + reserved
        working["starting_cash"] = baseline_cash + reserved
        working["initial_equity"] = _f(snap.get("equity"), baseline_cash + reserved)
        working["trades"] = synthetic + actual_trades

        rebuilt = dict(prior(working, runtime_core))
        n = len(synthetic)
        rebuilt["parsed_trade_rows"] = max(0, int(rebuilt.get("parsed_trade_rows") or 0) - n)
        rebuilt["coverage_issues"] = _adjust_issue_indexes(rebuilt.get("coverage_issues"), n)
        rebuilt["coverage_issue_count"] = len(_l(rebuilt.get("coverage_issues")))
        rebuilt["economic_issues"] = _adjust_issue_indexes(rebuilt.get("economic_issues"), n)
        rebuilt["economic_issue_count"] = len(_l(rebuilt.get("economic_issues")))
        rebuilt["initial_cash"] = round(baseline_cash, 6)
        rebuilt["baseline_cash"] = round(baseline_cash, 6)
        rebuilt["baseline_equity"] = round(_f(snap.get("equity"), baseline_cash), 6)
        rebuilt["baseline_type"] = "verified_snapshot_with_open_position"
        rebuilt["baseline_position_count"] = len(synthetic)
        rebuilt["verified_snapshot_epoch"] = True
        rebuilt["realized_today"] = round(_f(snap.get("realized_today"), 0.0) + _f(rebuilt.get("realized_today"), 0.0), 6)
        rebuilt["realized_total"] = round(_f(snap.get("realized_total"), 0.0) + _f(rebuilt.get("realized_total"), 0.0), 6)
        rebuilt["coverage_complete"] = bool(
            rebuilt.get("status") in {"ok", "partial"}
            and not rebuilt["coverage_issues"]
            and not rebuilt["economic_issues"]
        )
        rebuilt["status"] = "ok" if rebuilt["coverage_complete"] else "partial"
        return rebuilt

    wrapped._verified_snapshot_baseline_version = VERSION  # type: ignore[attr-defined]
    wrapped._verified_snapshot_baseline_prior = prior  # type: ignore[attr-defined]
    bidirectional.analyze_ledger = wrapped
    accounting.reconstruct_from_ledger = wrapped
    matched.analyze_ledger = wrapped
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    active = False
    try:
        import paper_bidirectional_accounting_guard as bidirectional
        active = getattr(getattr(bidirectional, "analyze_ledger", None), "_verified_snapshot_baseline_version", None) == VERSION
    except Exception:
        active = False
    return {
        "status": "ok" if active else "pending",
        "overall": "pass" if active else "warn",
        "version": VERSION,
        "snapshot_baseline_supported": bool(active),
        "paper_accounting_only": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
