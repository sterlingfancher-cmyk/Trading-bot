#!/usr/bin/env python3
"""Capture a read-only Railway research and paper-runtime snapshot.

The collector performs GET requests only. It does not call authenticated run
routes, initiate a backtest, alter strategy parameters, mutate paper state, or
place orders. The output is intended for scheduled engineering review.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://trading-bot-clean.up.railway.app"
VERSION = "runtime-research-snapshot-2026-08-03-v1"

ENDPOINTS = {
    "self_check": "/paper/self-check",
    "v2_status": "/paper/performance-audit-v2-status",
    "v2_ablation": "/paper/performance-ablation-v2",
    "v2_regime": "/paper/performance-regime-report-v2",
    "v2_recovery": "/paper/performance-v2-recovery-status",
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
                    "User-Agent": "Trading-bot-read-only-research-snapshot/1.0",
                },
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                elapsed = round(time.monotonic() - started, 3)
                payload = json.loads(raw)
                return {
                    "status": "ok",
                    "http_status": int(getattr(response, "status", 200)),
                    "elapsed_seconds": elapsed,
                    "attempt": attempt,
                    "payload": payload,
                }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(8.0, 1.5 * attempt))
    return {
        "status": "error",
        "error": last_error or "unknown_fetch_error",
        "attempts": retries,
    }


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
    profiles = _dict(payload.get("profiles"))
    output: dict[str, Any] = {}
    for name, raw in profiles.items():
        row = _dict(raw)
        output[str(name)] = {
            "full_sample": _metric_subset(row.get("full_sample")),
            "walk_forward": _metric_subset(row.get("walk_forward")),
            "calendar_year_count": len(_dict(row.get("calendar_years"))),
            "regime_count": len(_dict(row.get("regime_report"))),
        }
    return output


def _summarize(raw: dict[str, dict[str, Any]]) -> dict[str, Any]:
    self_payload = _dict(_dict(raw.get("self_check")).get("payload"))
    status_payload = _dict(_dict(raw.get("v2_status")).get("payload"))
    latest = _dict(status_payload.get("latest"))
    runner = _dict(status_payload.get("resilient_runner"))
    ablation_payload = _dict(_dict(raw.get("v2_ablation")).get("payload"))
    ablation = _dict(ablation_payload.get("ablation"))
    regime_payload = _dict(_dict(raw.get("v2_regime")).get("payload"))
    recovery_payload = _dict(_dict(raw.get("v2_recovery")).get("payload"))
    recovery_guard = _dict(recovery_payload.get("guard"))

    ranking = _list(ablation.get("ranking"))
    best_variant = _dict(ablation.get("best_variant"))
    if not best_variant and ranking:
        best_variant = _dict(ranking[0])

    profiles = _profile_summary(latest)
    if not profiles:
        profiles = _profile_summary(regime_payload)

    fetch_failures = sorted(
        name for name, row in raw.items() if _dict(row).get("status") != "ok"
    )
    v2_run_status = status_payload.get("run_status") or latest.get("status") or "unknown"
    if fetch_failures:
        overall = "warn"
    elif self_payload.get("overall") not in {None, "pass"}:
        overall = "warn"
    elif str(v2_run_status).lower() == "error":
        overall = "warn"
    else:
        overall = "pass"

    return {
        "overall": overall,
        "fetch_failures": fetch_failures,
        "self_check": {
            "overall": self_payload.get("overall"),
            "version": self_payload.get("version"),
            "generated_local": self_payload.get("generated_local"),
            "failing_components": _dict(self_payload.get("summary")).get("failing_components"),
            "base_failures": _dict(self_payload.get("summary")).get("base_failures"),
            "positions": _dict(self_payload.get("account")).get("positions"),
            "equity": _dict(self_payload.get("account")).get("equity"),
            "cash": _dict(self_payload.get("account")).get("cash"),
            "last_success": _dict(self_payload.get("auto_runner")).get("last_success"),
        },
        "v2": {
            "version": status_payload.get("version"),
            "run_status": v2_run_status,
            "latest_key": status_payload.get("latest_key"),
            "latest_generated_local": latest.get("generated_local"),
            "latest_generated_epoch": latest.get("generated_epoch"),
            "runner_state": runner.get("state"),
            "runner_phase": runner.get("phase"),
            "runner_detail": runner.get("detail"),
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
        "recovery": {
            "version": recovery_payload.get("version"),
            "watchdog_started": recovery_payload.get("watchdog_started"),
            "guard_status": recovery_guard.get("status"),
            "observed_state": recovery_guard.get("observed_state"),
            "thread_alive": recovery_guard.get("thread_alive"),
            "engine_locked": recovery_guard.get("engine_locked"),
            "recovery_attempt_count": recovery_guard.get("recovery_attempt_count"),
            "last_result": recovery_guard.get("last_result"),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    self_check = _dict(summary.get("self_check"))
    v2 = _dict(summary.get("v2"))
    ablation = _dict(summary.get("ablation"))
    recovery = _dict(summary.get("recovery"))
    lines = [
        "# Runtime Research Snapshot",
        "",
        f"- Snapshot status: **{str(report.get('status', 'unknown')).upper()}**",
        f"- Base URL: `{report.get('base_url')}`",
        f"- Fetch failures: `{', '.join(summary.get('fetch_failures', [])) or 'none'}`",
        "",
        "## Paper Runtime",
        "",
        f"- Self-check: `{self_check.get('overall')}`",
        f"- Self-check version: `{self_check.get('version')}`",
        f"- Generated: `{self_check.get('generated_local')}`",
        f"- Positions: `{self_check.get('positions')}`",
        f"- Equity: `{self_check.get('equity')}`",
        f"- Cash: `{self_check.get('cash')}`",
        f"- Failing components: `{self_check.get('failing_components')}`",
        "",
        "## Performance Research V2",
        "",
        f"- Version: `{v2.get('version')}`",
        f"- Run status: `{v2.get('run_status')}`",
        f"- Latest key: `{v2.get('latest_key')}`",
        f"- Latest generated: `{v2.get('latest_generated_local')}`",
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
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- Full sample: `{_dict(row).get('full_sample')}`")
            lines.append(f"- Walk-forward: `{_dict(row).get('walk_forward')}`")
            lines.append("")

    lines.extend(
        [
            "## Ablation",
            "",
            f"- Status: `{ablation.get('status')}`",
            f"- Variants: `{ablation.get('variant_count')}`",
            f"- Best variant: `{ablation.get('best_variant')}`",
            "",
            "## Recovery",
            "",
            f"- Watchdog started: `{recovery.get('watchdog_started')}`",
            f"- Observed state: `{recovery.get('observed_state')}`",
            f"- Thread alive: `{recovery.get('thread_alive')}`",
            f"- Engine locked: `{recovery.get('engine_locked')}`",
            f"- Recovery attempts: `{recovery.get('recovery_attempt_count')}`",
            "",
            "This report is read-only. It does not promote research settings or place orders.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--json", default="runtime_research_snapshot.json")
    parser.add_argument("--markdown", default="runtime_research_snapshot.md")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    raw = {
        name: _fetch_json(base_url + path, max(1, args.retries), max(5.0, args.timeout))
        for name, path in ENDPOINTS.items()
    }
    summary = _summarize(raw)
    reachable = sum(1 for row in raw.values() if row.get("status") == "ok")
    status = "pass" if reachable == len(raw) and summary.get("overall") == "pass" else "warn"
    if reachable == 0:
        status = "error"

    report = {
        "status": status,
        "type": "runtime_research_snapshot",
        "version": VERSION,
        "base_url": base_url,
        "read_only": True,
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

    Path(args.json).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.markdown).write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "reachable_endpoints": reachable,
        "total_endpoints": len(raw),
        "summary": summary,
    }, indent=2, sort_keys=True))
    return 1 if status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
