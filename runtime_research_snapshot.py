#!/usr/bin/env python3
"""Capture a bounded, read-only Railway runtime and research snapshot.

The collector performs concurrent GET requests only. It never calls authenticated
cycle routes, initiates research, changes policy, mutates paper state, or places
orders. The authoritative verified-v2 recovery gate, fresh-day gate, and compact
active audit are captured automatically so manual per-event forensic requests are
not required during Issue #82 stabilization.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://web-production-e1796.up.railway.app"
VERSION = "runtime-research-snapshot-2026-08-24-v6-ready-settled-stabilization"

ENDPOINTS = {
    "bootstrap_status": "/bootstrap-status",
    "root": "/",
    "paper_status": "/paper/status",
    "self_check": "/paper/self-check",
    "fresh_day_check": "/paper/fresh-day-check",
    "daily_audit": "/paper/daily-audit",
    "verified_v2_recovery_gate": "/paper/verified-v2-successor-replay-status",
    "v1_status": "/paper/performance-audit-status",
    "v2_status": "/paper/performance-audit-v2-status",
    "v2_ablation": "/paper/performance-ablation-v2",
    "v2_regime": "/paper/performance-regime-report-v2",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _fetch_json(url: str, retries: int, timeout: float) -> dict[str, Any]:
    last_error: str | None = None
    for attempt in range(1, retries + 1):
        started = time.monotonic()
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Trading-bot-read-only-research-snapshot/5.0",
                },
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return {
                    "status": "ok",
                    "http_status": int(getattr(response, "status", 200)),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "attempt": attempt,
                    "payload": json.loads(raw),
                }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(4.0, 1.0 * attempt))
    return {
        "status": "error",
        "error": last_error or "unknown_fetch_error",
        "attempts": retries,
    }


def _wait_for_delegate_ready(
    base_url: str,
    *,
    wait_seconds: float,
    poll_seconds: float,
    timeout: float,
) -> dict[str, Any]:
    """Wait boundedly for the deferred WSGI delegate before broad capture.

    This performs GETs against bootstrap status only. It never invokes a paper
    cycle, mutates state, or changes runtime authority. A timeout is evidence,
    not permission to restart or repair the service.
    """
    started = time.monotonic()
    deadline = started + max(0.0, float(wait_seconds))
    attempts = 0
    last: dict[str, Any] = {}
    if wait_seconds <= 0:
        return {
            "ready_before_capture": None,
            "attempts": 0,
            "waited_seconds": 0.0,
            "last_status": None,
            "last_phase": None,
        }

    while True:
        attempts += 1
        last = _fetch_json(
            base_url.rstrip("/") + "/bootstrap-status",
            retries=1,
            timeout=max(5.0, min(float(timeout), 15.0)),
        )
        payload = _dict(last.get("payload"))
        status = payload.get("status")
        ready = bool(
            last.get("status") == "ok"
            and (payload.get("delegate_ready") or status == "ready")
        )
        now = time.monotonic()
        if ready:
            return {
                "ready_before_capture": True,
                "attempts": attempts,
                "waited_seconds": round(now - started, 3),
                "last_status": status,
                "last_phase": payload.get("phase"),
                "last_delegate_ready": payload.get("delegate_ready"),
            }
        if status == "error" or now >= deadline:
            return {
                "ready_before_capture": False,
                "attempts": attempts,
                "waited_seconds": round(now - started, 3),
                "last_status": status,
                "last_phase": payload.get("phase"),
                "last_delegate_ready": payload.get("delegate_ready"),
                "last_fetch_status": last.get("status"),
                "last_error": last.get("error") or payload.get("error"),
            }

        remaining = max(0.0, deadline - now)
        time.sleep(min(max(0.1, float(poll_seconds)), remaining))


def _metric_subset(value: Any) -> dict[str, Any]:
    row = _dict(value)
    wanted = (
        "status",
        "total_return_pct",
        "annualized_return_pct",
        "max_drawdown_pct",
        "sharpe",
        "profit_factor",
        "win_rate_pct",
        "trades",
        "trade_count",
        "average_exposure_pct",
        "turnover",
        "ending_equity",
        "objective",
    )
    return {key: row.get(key) for key in wanted if key in row}


def _profile_summary(payload: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, raw in _dict(payload.get("profiles")).items():
        row = _dict(raw)
        output[str(name)] = {
            "full_sample": _metric_subset(row.get("full_sample")),
            "walk_forward": _metric_subset(row.get("walk_forward")),
            "calendar_year_count": len(_dict(row.get("calendar_years"))),
            "regime_count": len(_dict(row.get("regime_report"))),
        }
    return output


def _recovery_gate_summary(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = _dict(payload.get("recovery_readiness"))
    ledger = _dict(payload.get("ledger"))
    comparison = _dict(payload.get("state_comparison"))
    projection = _dict(payload.get("projection"))
    return {
        "overall": payload.get("overall"),
        "version": payload.get("version"),
        "diagnosis": payload.get("diagnosis"),
        "generated_local": payload.get("generated_local"),
        "ledger_row_count": ledger.get("row_count"),
        "chain_valid": ledger.get("chain_valid"),
        "known_invalid_execution_count": payload.get("known_invalid_execution_count"),
        "all_known_invalid_signatures_exact": payload.get(
            "all_known_invalid_signatures_exact"
        ),
        "latest_invalid_is_last_canonical_execution": payload.get(
            "latest_invalid_is_last_canonical_execution"
        ),
        "projection_complete": projection.get("projection_complete"),
        "candidate_cash": projection.get("candidate_cash"),
        "candidate_equity_using_current_stored_marks": comparison.get(
            "candidate_equity_using_current_stored_marks"
        ),
        "unexplained_position_mismatches": comparison.get(
            "unexplained_position_mismatches"
        ),
        "mechanically_complete_for_successor_migration_design": readiness.get(
            "mechanically_complete_for_successor_migration_design"
        ),
        "manual_per_event_probe_required": readiness.get(
            "manual_per_event_probe_required"
        ),
        "state_write_authorized_by_probe": readiness.get(
            "state_write_authorized_by_this_probe"
        ),
        "halt_clear_authorized_by_probe": readiness.get(
            "halt_clear_authorized_by_this_probe"
        ),
        "risk_peak_repair_authorized_by_probe": readiness.get(
            "risk_peak_repair_authorized_by_this_probe"
        ),
    }


def _fresh_day_summary(payload: dict[str, Any]) -> dict[str, Any]:
    risk = _dict(payload.get("risk"))
    return {
        "overall": payload.get("overall"),
        "baseline_status": payload.get("baseline_status"),
        "date": payload.get("date") or risk.get("date"),
        "current_equity": payload.get("current_equity"),
        "day_start_equity": payload.get("day_start_equity")
        if payload.get("day_start_equity") is not None
        else risk.get("day_start_equity"),
        "day_peak_equity": payload.get("day_peak_equity")
        if payload.get("day_peak_equity") is not None
        else risk.get("day_peak_equity"),
        "fresh_day_reset_pending": payload.get("fresh_day_reset_pending"),
        "halted": payload.get("halted")
        if payload.get("halted") is not None
        else risk.get("halted"),
        "halt_reason": payload.get("halt_reason") or risk.get("halt_reason"),
        "intraday_drawdown_pct": payload.get("intraday_drawdown_pct")
        if payload.get("intraday_drawdown_pct") is not None
        else risk.get("intraday_drawdown_pct"),
    }


def _daily_audit_summary(payload: dict[str, Any]) -> dict[str, Any]:
    accounting = _dict(payload.get("accounting_integrity"))
    ledger = _dict(payload.get("execution_ledger"))
    market = _dict(payload.get("market_data"))
    runner = _dict(payload.get("runner"))
    risk = _dict(payload.get("risk"))
    epoch = _dict(payload.get("accounting_epoch"))
    return {
        "overall": payload.get("overall"),
        "generated_local": payload.get("generated_local"),
        "epoch_id": epoch.get("epoch_id"),
        "validation_hold": epoch.get("validation_hold"),
        "accounting_integrity_status": accounting.get("status"),
        "coverage_issue_count": accounting.get("coverage_issue_count"),
        "economic_issue_count": accounting.get("economic_issue_count"),
        "canonical_chain_valid": ledger.get("chain_valid"),
        "canonical_row_count": ledger.get("row_count"),
        "canonical_epoch_id": ledger.get("current_epoch_id"),
        "market_data_status": market.get("status"),
        "runner_status": runner.get("status"),
        "runner_active_error": runner.get("active_error"),
        "runner_last_successful_run": runner.get("last_successful_run"),
        "risk_status": risk.get("status"),
        "risk_halted": risk.get("halted"),
        "risk_halt_reason": risk.get("halt_reason"),
        "risk_intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
    }


def _summarize(raw: dict[str, dict[str, Any]]) -> dict[str, Any]:
    bootstrap_payload = _dict(_dict(raw.get("bootstrap_status")).get("payload"))
    root_payload = _dict(_dict(raw.get("root")).get("payload"))
    paper_payload = _dict(_dict(raw.get("paper_status")).get("payload"))
    self_payload = _dict(_dict(raw.get("self_check")).get("payload"))
    fresh_payload = _dict(_dict(raw.get("fresh_day_check")).get("payload"))
    audit_payload = _dict(_dict(raw.get("daily_audit")).get("payload"))
    recovery_payload = _dict(
        _dict(raw.get("verified_v2_recovery_gate")).get("payload")
    )
    fresh_day = _fresh_day_summary(fresh_payload)
    daily_audit = _daily_audit_summary(audit_payload)
    recovery_gate = _recovery_gate_summary(recovery_payload)
    v1_payload = _dict(_dict(raw.get("v1_status")).get("payload"))
    v2_payload = _dict(_dict(raw.get("v2_status")).get("payload"))
    latest = _dict(v2_payload.get("latest"))
    runner = _dict(v2_payload.get("resilient_runner"))
    ablation_payload = _dict(_dict(raw.get("v2_ablation")).get("payload"))
    ablation = _dict(ablation_payload.get("ablation"))
    regime_payload = _dict(_dict(raw.get("v2_regime")).get("payload"))

    ranking = _list(ablation.get("ranking"))
    best_variant = _dict(ablation.get("best_variant"))
    if not best_variant and ranking:
        best_variant = _dict(ranking[0])

    profiles = _profile_summary(latest) or _profile_summary(regime_payload)
    reachable = sorted(name for name, row in raw.items() if row.get("status") == "ok")
    failures = sorted(set(raw) - set(reachable))
    listener_reachable = any(
        name in reachable for name in ("bootstrap_status", "root")
    )
    delegate_ready = bool(
        bootstrap_payload.get("delegate_ready")
        or root_payload.get("delegate_ready")
        or "paper_status" in reachable
        or "self_check" in reachable
    )
    application_ready = bool(
        delegate_ready and ("paper_status" in reachable or "self_check" in reachable)
    )
    self_overall = self_payload.get("overall")
    recovery_overall = recovery_payload.get("overall")
    fresh_baseline_status = fresh_payload.get("baseline_status")
    audit_overall = audit_payload.get("overall")
    v2_run_status = v2_payload.get("run_status") or latest.get("status") or "unknown"

    if not listener_reachable:
        overall = "error"
    elif not application_ready:
        overall = "warn"
    elif self_overall not in {None, "pass"}:
        overall = "warn"
    elif fresh_baseline_status not in {None, "pass"}:
        overall = "warn"
    elif audit_overall not in {None, "pass"}:
        overall = "warn"
    elif recovery_overall not in {None, "pass"}:
        overall = "warn"
    elif str(v2_run_status).lower() == "error" or failures:
        overall = "warn"
    else:
        overall = "pass"

    return {
        "overall": overall,
        "connectivity": {
            "reachable_count": len(reachable),
            "total_count": len(raw),
            "reachable_endpoints": reachable,
            "failed_endpoints": failures,
            "listener_reachable": listener_reachable,
            "application_ready": application_ready,
            "delegate_ready": delegate_ready,
            "bootstrap_status": bootstrap_payload.get("status"),
            "bootstrap_phase": bootstrap_payload.get("phase"),
            "bootstrap_error": bootstrap_payload.get("error"),
            "bootstrap_elapsed_seconds": bootstrap_payload.get("elapsed_seconds"),
            "loader_thread_alive": bootstrap_payload.get("loader_thread_alive"),
            "root_status": root_payload.get("status"),
            "paper_status": paper_payload.get("status"),
        },
        "self_check": {
            "overall": self_overall,
            "version": self_payload.get("version"),
            "generated_local": self_payload.get("generated_local"),
            "components_checked": _dict(self_payload.get("summary")).get(
                "components_checked"
            ),
            "failing_components": _dict(self_payload.get("summary")).get(
                "failing_components"
            ),
            "base_failures": _dict(self_payload.get("summary")).get(
                "base_failures"
            ),
            "positions": _dict(self_payload.get("account")).get("positions"),
            "equity": _dict(self_payload.get("account")).get("equity"),
            "cash": _dict(self_payload.get("account")).get("cash"),
            "last_success": _dict(self_payload.get("auto_runner")).get(
                "last_success"
            ),
            "runtime_shadow_capture": _dict(
                _dict(self_payload.get("component_checks")).get(
                    "runtime_shadow_capture"
                )
            ),
        },
        "fresh_day": fresh_day,
        "daily_audit": daily_audit,
        "recovery_gate": recovery_gate,
        "v1": {
            "version": v1_payload.get("version"),
            "enabled": v1_payload.get("enabled"),
            "auto_backtest_enabled": _dict(v1_payload.get("settings")).get(
                "auto_backtest_enabled"
            ),
            "backtest_status": _dict(v1_payload.get("backtest")).get("status"),
            "forward_rows": _dict(v1_payload.get("forward_test")).get("rows_total"),
        },
        "v2": {
            "version": v2_payload.get("version"),
            "enabled": v2_payload.get("enabled"),
            "run_status": v2_run_status,
            "latest_key": v2_payload.get("latest_key"),
            "latest_generated_local": latest.get("generated_local"),
            "runner_state": runner.get("state"),
            "runner_phase": runner.get("phase"),
            "progress_current": runner.get("progress_current"),
            "progress_total": runner.get("progress_total"),
            "thread_alive": runner.get("thread_alive"),
            "engine_locked": runner.get("engine_locked"),
            "core_checkpoint_available": runner.get("core_checkpoint_available"),
            "activation_gate": _dict(latest.get("activation_gate")),
            "methodology": _dict(latest.get("methodology")),
            "profiles": profiles,
        },
        "ablation": {
            "status": ablation.get("status") or ablation_payload.get("status"),
            "variant_count": ablation.get("variant_count") or len(ranking),
            "best_variant": best_variant,
        },
        "regime": {
            "status": regime_payload.get("status"),
            "profile_names": sorted(_dict(regime_payload.get("profiles")).keys()),
            "generated_local": regime_payload.get("generated_local"),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    connectivity = _dict(summary.get("connectivity"))
    settlement = _dict(report.get("settlement"))
    self_check = _dict(summary.get("self_check"))
    fresh_day = _dict(summary.get("fresh_day"))
    daily_audit = _dict(summary.get("daily_audit"))
    recovery_gate = _dict(summary.get("recovery_gate"))
    v1 = _dict(summary.get("v1"))
    v2 = _dict(summary.get("v2"))
    ablation = _dict(summary.get("ablation"))
    lines = [
        "# Runtime Research Snapshot",
        "",
        f"- Snapshot status: **{str(report.get('status', 'unknown')).upper()}**",
        f"- Base URL: `{report.get('base_url')}`",
        f"- Ready before broad capture: `{settlement.get('ready_before_capture')}`",
        f"- Readiness wait: `{settlement.get('waited_seconds')}` seconds / `{settlement.get('attempts')}` attempts",
        f"- Reachable: `{connectivity.get('reachable_count')}/{connectivity.get('total_count')}`",
        f"- Listener reachable: `{connectivity.get('listener_reachable')}`",
        f"- Application ready: `{connectivity.get('application_ready')}`",
        f"- Bootstrap phase: `{connectivity.get('bootstrap_phase')}`",
        f"- Bootstrap error: `{connectivity.get('bootstrap_error')}`",
        f"- Failed endpoints: `{connectivity.get('failed_endpoints')}`",
        "",
        "## Paper Runtime",
        "",
        f"- Self-check: `{self_check.get('overall')}`",
        f"- Version: `{self_check.get('version')}`",
        f"- Components: `{self_check.get('components_checked')}`",
        f"- Generated: `{self_check.get('generated_local')}`",
        f"- Positions: `{self_check.get('positions')}`",
        f"- Equity: `{self_check.get('equity')}`",
        f"- Failing components: `{self_check.get('failing_components')}`",
        f"- Runtime shadow capture: `{self_check.get('runtime_shadow_capture')}`",
        "",
        "## Fresh Risk Day",
        "",
        f"- Baseline status: `{fresh_day.get('baseline_status')}`",
        f"- Date: `{fresh_day.get('date')}`",
        f"- Day start / peak: `{fresh_day.get('day_start_equity')}` / `{fresh_day.get('day_peak_equity')}`",
        f"- Reset pending: `{fresh_day.get('fresh_day_reset_pending')}`",
        f"- Halted / reason: `{fresh_day.get('halted')}` / `{fresh_day.get('halt_reason')}`",
        f"- Intraday drawdown: `{fresh_day.get('intraday_drawdown_pct')}`",
        "",
        "## Compact Active Audit",
        "",
        f"- Overall: `{daily_audit.get('overall')}`",
        f"- Accounting integrity: `{daily_audit.get('accounting_integrity_status')}`",
        f"- Coverage / economic issues: `{daily_audit.get('coverage_issue_count')}` / `{daily_audit.get('economic_issue_count')}`",
        f"- Canonical chain / rows: `{daily_audit.get('canonical_chain_valid')}` / `{daily_audit.get('canonical_row_count')}`",
        f"- Market data: `{daily_audit.get('market_data_status')}`",
        f"- Runner / active error: `{daily_audit.get('runner_status')}` / `{daily_audit.get('runner_active_error')}`",
        f"- Risk / halted: `{daily_audit.get('risk_status')}` / `{daily_audit.get('risk_halted')}`",
        f"- Risk halt reason: `{daily_audit.get('risk_halt_reason')}`",
        "",
        "## Verified-v2 Recovery Gate",
        "",
        f"- Overall: `{recovery_gate.get('overall')}`",
        f"- Diagnosis: `{recovery_gate.get('diagnosis')}`",
        f"- Version: `{recovery_gate.get('version')}`",
        f"- Ledger rows / chain: `{recovery_gate.get('ledger_row_count')}` / `{recovery_gate.get('chain_valid')}`",
        f"- Invalid signatures exact: `{recovery_gate.get('all_known_invalid_signatures_exact')}`",
        f"- Projection complete: `{recovery_gate.get('projection_complete')}`",
        f"- Mechanically complete: `{recovery_gate.get('mechanically_complete_for_successor_migration_design')}`",
        f"- Manual per-event probe required: `{recovery_gate.get('manual_per_event_probe_required')}`",
        f"- Candidate cash: `{recovery_gate.get('candidate_cash')}`",
        f"- Candidate equity from stored marks: `{recovery_gate.get('candidate_equity_using_current_stored_marks')}`",
        f"- Unexplained position mismatches: `{recovery_gate.get('unexplained_position_mismatches')}`",
        "",
        "## Research V1",
        "",
        f"- Version: `{v1.get('version')}`",
        f"- Enabled: `{v1.get('enabled')}`",
        f"- Auto backtest: `{v1.get('auto_backtest_enabled')}`",
        f"- Backtest status: `{v1.get('backtest_status')}`",
        f"- Forward rows: `{v1.get('forward_rows')}`",
        "",
        "## Research V2",
        "",
        f"- Version: `{v2.get('version')}`",
        f"- Enabled: `{v2.get('enabled')}`",
        f"- Run status: `{v2.get('run_status')}`",
        f"- Latest key: `{v2.get('latest_key')}`",
        f"- Runner: `{v2.get('runner_state')}` / `{v2.get('runner_phase')}`",
        f"- Progress: `{v2.get('progress_current')}` / `{v2.get('progress_total')}`",
        f"- Core checkpoint: `{v2.get('core_checkpoint_available')}`",
        "",
        "## Profiles",
        "",
    ]
    profiles = _dict(v2.get("profiles"))
    if not profiles:
        lines.append("No completed profile metrics were available.")
    else:
        for name, row in profiles.items():
            lines.extend(
                [
                    f"### {name}",
                    "",
                    f"- Full sample: `{_dict(row).get('full_sample')}`",
                    f"- Walk-forward: `{_dict(row).get('walk_forward')}`",
                    "",
                ]
            )
    lines.extend(
        [
            "## Ablation",
            "",
            f"- Status: `{ablation.get('status')}`",
            f"- Variants: `{ablation.get('variant_count')}`",
            f"- Best variant: `{ablation.get('best_variant')}`",
            "",
            "This report is read-only and does not initiate research or place orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ready-wait-seconds", type=float, default=180.0)
    parser.add_argument("--ready-poll-seconds", type=float, default=5.0)
    parser.add_argument("--json", default="runtime_research_snapshot.json")
    parser.add_argument("--markdown", default="runtime_research_snapshot.md")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    settlement = _wait_for_delegate_ready(
        base_url,
        wait_seconds=max(0.0, args.ready_wait_seconds),
        poll_seconds=max(0.1, args.ready_poll_seconds),
        timeout=max(5.0, args.timeout),
    )
    raw: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, len(ENDPOINTS)))
    ) as executor:
        futures = {
            executor.submit(
                _fetch_json,
                base_url + path,
                max(1, args.retries),
                max(5.0, args.timeout),
            ): name
            for name, path in ENDPOINTS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                raw[name] = future.result()
            except Exception as exc:
                raw[name] = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }

    summary = _summarize(raw)
    status = str(summary.get("overall") or "error")
    report = {
        "status": status,
        "type": "runtime_research_snapshot",
        "version": VERSION,
        "base_url": base_url,
        "read_only": True,
        "settlement": settlement,
        "endpoints": ENDPOINTS,
        "summary": summary,
        "raw": raw,
        "authority": {
            "starts_backtest": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_sizing": False,
            "changes_risk": False,
            "places_orders": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
        },
    }

    Path(args.json).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(args.markdown).write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "summary": summary}, indent=2, sort_keys=True))
    return 1 if status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
