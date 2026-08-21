#!/usr/bin/env python3
"""Read-only incident triage for Trading-bot post-rebuild diagnostics.

This module consumes already-produced diagnostic dictionaries. It does not import
the trading runtime, read/write production state, clear halts, place orders, or
change strategy/risk/live/ML authority.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from change_safety_audit import CORE_TESTS, CONFIG_TESTS, RUNTIME_TESTS, STATE_TESTS

VERSION = "system-sentinel-shadow-2026-08-20-v1"
AUTHORITY = "advisory_only"


@dataclass(frozen=True)
class Incident:
    incident_id: str
    severity: str
    boundary: str
    reason_code: str
    evidence: Mapping[str, Any]
    suspected_cause: str
    confidence: float
    proposed_fix: str
    selected_tests: tuple[str, ...]
    full_audit_required: bool
    authority: str = AUTHORITY

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence"] = dict(self.evidence)
        row["selected_tests"] = list(self.selected_tests)
        return row


BOUNDARY_TESTS = {
    "state": STATE_TESTS,
    "valuation": ("test_architecture_stage_b.py",),
    "accounting": ("test_architecture_stage_e_accounting.py",),
    "execution": ("test_architecture_stage_e_accounting.py",),
    "risk": ("test_architecture_stage_c.py",),
    "startup_runtime": RUNTIME_TESTS,
    "configuration": CONFIG_TESTS,
    "architecture": (),
    "runner": RUNTIME_TESTS,
    "market_data": ("test_architecture_stage_b.py",),
}

FIX_LIBRARY = {
    "invalid_protected_valuation": "Trace the protected-mark/valuation input that violated the canonical invariant; repair only the proven source path and keep risk baseline initialization fail-closed.",
    "accounting_integrity_failure": "Trace the exact execution lifecycle producing the unmatched/duplicate/economic issue; preserve the append-only ledger and repair the prospective execution/accounting boundary only.",
    "execution_chain_invalid": "Stop promotion/cutover, verify append-only ledger ordering and integrity provenance, and repair the prospective ledger writer without rewriting historical rows.",
    "invalid_risk_baseline": "Trace the protected valuation used to seed day_start/day_peak; keep the halt/risk state unchanged and repair only the fresh-day initialization path.",
    "startup_failure": "Reproduce the exact bootstrap/Gunicorn failure and repair the smallest startup ownership or dependency defect without adding a second runtime owner.",
    "configuration_drift": "Reconcile the drift to the canonical typed-configuration owner; do not add another environment/default owner.",
    "architecture_ownership_regression": "Remove or consolidate the newly introduced duplicate owner/route/mutation path and preserve the canonical ownership boundary.",
    "runner_active_error": "Reproduce the active runner exception from its compact evidence, fix the narrow failing path, and retain the non-overlapping cycle guard.",
    "market_data_incomplete": "Trace the incomplete provider request lifecycle and repair request accounting/terminal classification without changing strategy thresholds.",
}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tests(boundary: str, *, full: bool) -> tuple[str, ...]:
    selected = list(CORE_TESTS)
    selected.extend(BOUNDARY_TESTS.get(boundary, ()))
    if full:
        selected.extend(RUNTIME_TESTS)
        selected.extend(STATE_TESTS)
        selected.extend(CONFIG_TESTS)
    out: list[str] = []
    seen: set[str] = set()
    for row in selected:
        if row not in seen:
            out.append(row)
            seen.add(row)
    return tuple(out)


def _incident(*, boundary: str, severity: str, reason: str, evidence: Mapping[str, Any], cause: str, confidence: float, full: bool) -> Incident:
    normalized = "|".join(f"{k}={evidence[k]!r}" for k in sorted(evidence))
    digest = hashlib.sha256(f"{boundary}|{reason}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return Incident(
        incident_id=f"{boundary}:{reason}:{digest}",
        severity=severity,
        boundary=boundary,
        reason_code=reason,
        evidence=dict(evidence),
        suspected_cause=cause,
        confidence=max(0.0, min(1.0, float(confidence))),
        proposed_fix=FIX_LIBRARY[reason],
        selected_tests=_tests(boundary, full=full),
        full_audit_required=bool(full),
    )


def diagnose(snapshot: Mapping[str, Any]) -> tuple[Incident, ...]:
    """Classify a compact diagnostic snapshot deterministically and read-only."""
    s = dict(snapshot)
    incidents: list[Incident] = []

    valuation = _d(s.get("valuation"))
    equity = valuation.get("equity")
    eligible = valuation.get("risk_baseline_eligible")
    if valuation and (valuation.get("status") in {"fail", "error"} or eligible is False or isinstance(equity, (int, float)) and equity <= 0):
        incidents.append(_incident(boundary="valuation", severity="critical", reason="invalid_protected_valuation", evidence={"status": valuation.get("status"), "equity": equity, "risk_baseline_eligible": eligible}, cause="Protected valuation is invalid or ineligible to seed canonical risk state.", confidence=0.98, full=True))

    accounting = _d(s.get("accounting"))
    coverage = accounting.get("coverage_complete")
    economic_count = int(accounting.get("economic_issue_count") or 0)
    coverage_count = int(accounting.get("coverage_issue_count") or 0)
    if accounting and (accounting.get("status") in {"fail", "partial", "error"} or coverage is False or economic_count or coverage_count):
        incidents.append(_incident(boundary="accounting", severity="critical", reason="accounting_integrity_failure", evidence={"status": accounting.get("status"), "coverage_complete": coverage, "economic_issue_count": economic_count, "coverage_issue_count": coverage_count}, cause="Canonical execution projection cannot prove complete economic/accounting coverage.", confidence=0.99, full=True))

    ledger = _d(s.get("execution_ledger"))
    if ledger and ledger.get("chain_valid") is False:
        incidents.append(_incident(boundary="execution", severity="critical", reason="execution_chain_invalid", evidence={"chain_valid": False, "row_count": ledger.get("row_count"), "epoch_id": ledger.get("current_epoch_id")}, cause="Canonical append-only execution chain integrity failed.", confidence=1.0, full=True))

    risk = _d(s.get("risk"))
    start = risk.get("day_start_equity")
    peak = risk.get("day_peak_equity")
    invalid_risk = False
    try:
        invalid_risk = float(start) <= 0 or float(peak) <= 0 or float(peak) < float(start)
    except (TypeError, ValueError):
        invalid_risk = bool(risk) and (start is not None or peak is not None)
    if risk and invalid_risk:
        incidents.append(_incident(boundary="risk", severity="critical", reason="invalid_risk_baseline", evidence={"day_start_equity": start, "day_peak_equity": peak, "halted": risk.get("halted")}, cause="Canonical daily-risk baseline violates positive/monotonic initialization invariants.", confidence=0.99, full=True))

    startup = _d(s.get("startup"))
    if startup and startup.get("status") in {"error", "fail", "failed"}:
        incidents.append(_incident(boundary="startup_runtime", severity="critical", reason="startup_failure", evidence={"status": startup.get("status"), "error": startup.get("error"), "phase": startup.get("phase")}, cause="Application bootstrap did not reach the canonical ready/delegating state.", confidence=0.97, full=True))

    config = _d(s.get("configuration"))
    config_violations = config.get("violations") or []
    if config and config_violations:
        incidents.append(_incident(boundary="configuration", severity="high", reason="configuration_drift", evidence={"violation_count": len(config_violations), "first_violation": config_violations[0]}, cause="Observed configuration no longer matches the canonical typed owner/units contract.", confidence=0.95, full=True))

    architecture = _d(s.get("architecture"))
    new_critical = architecture.get("new_critical") or []
    ownership = architecture.get("ownership_violations") or []
    if architecture and (new_critical or ownership):
        incidents.append(_incident(boundary="architecture", severity="high", reason="architecture_ownership_regression", evidence={"new_critical_count": len(new_critical), "ownership_violation_count": len(ownership)}, cause="A change introduced structural debt or duplicated an authoritative ownership boundary.", confidence=0.98, full=True))

    runner = _d(s.get("runner"))
    if runner and runner.get("active_error"):
        incidents.append(_incident(boundary="runner", severity="high", reason="runner_active_error", evidence={"active_error": True, "last_error": runner.get("last_error"), "last_attempt": runner.get("last_attempt")}, cause="The canonical cycle/runner reports an active exception after its most recent attempt.", confidence=0.94, full=False))

    market = _d(s.get("market_data"))
    if market and (market.get("status") in {"fail", "error"} or market.get("accounting_complete_at_snapshot") is False or int(market.get("in_flight_or_unclassified_requests") or 0) > 0):
        incidents.append(_incident(boundary="market_data", severity="high", reason="market_data_incomplete", evidence={"status": market.get("status"), "accounting_complete_at_snapshot": market.get("accounting_complete_at_snapshot"), "in_flight_or_unclassified_requests": market.get("in_flight_or_unclassified_requests")}, cause="Market-data request accounting has unresolved or unclassified terminal outcomes.", confidence=0.92, full=False))

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return tuple(sorted(incidents, key=lambda row: (order.get(row.severity, 9), row.boundary, row.reason_code)))


def report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    incidents = diagnose(snapshot)
    return {
        "version": VERSION,
        "authority": AUTHORITY,
        "status": "quiet" if not incidents else "incident",
        "incident_count": len(incidents),
        "incidents": [row.to_dict() for row in incidents],
        "policy": {
            "advisory_only": True,
            "mandatory_core_tests_never_skipped": True,
            "auto_merges": False,
            "writes_production_state": False,
            "clears_halts": False,
            "rewrites_execution_history": False,
            "changes_strategy_or_sizing": False,
            "changes_hard_risk_limits": False,
            "changes_live_or_ml_authority": False,
        },
    }
