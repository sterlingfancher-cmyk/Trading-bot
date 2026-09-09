#!/usr/bin/env python3
"""Run Performance Audit V2 in a dedicated, persistent research process.

This entry point deliberately has no Flask, paper-runner, broker, or order
surface.  Its JSON checkpoint can be restored by a later isolated run, so the
expensive core result and completed ablation variants are not repeated.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
from typing import Any


VERSION = "performance-audit-v2-offline-2026-09-08-v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"checkpoint must contain a JSON object: {path}")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


class OfflineResearchCore:
    """Minimal durable state adapter; intentionally not a trading core."""

    def __init__(self, checkpoint: Path) -> None:
        self.checkpoint = checkpoint
        stored = _read_json(checkpoint)
        portfolio = stored.get("portfolio", stored)
        self.portfolio = portfolio if isinstance(portfolio, dict) else {}

    @staticmethod
    def local_ts_text() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def save_state(self, portfolio: dict[str, Any]) -> None:
        self.portfolio = portfolio
        _atomic_json(
            self.checkpoint,
            {
                "format_version": 1,
                "runner_version": VERSION,
                "saved_utc": self.local_ts_text(),
                "portfolio": portfolio,
            },
        )


def execute(
    *,
    period: str,
    max_symbols: int,
    include_ablation: bool,
    checkpoint: Path,
    output: Path,
    force: bool = False,
) -> dict[str, Any]:
    # Imports occur only after automatic/web-owned research is disabled.
    os.environ["PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED"] = "false"
    import performance_audit_lab_v2 as lab
    import performance_audit_v2_async_route as resumable

    core = OfflineResearchCore(checkpoint)
    section = lab._section(core)
    if force:
        section.pop("resilient_core_checkpoint", None)
        section.pop("resilient_ablation_partial", None)
    prior_checkpoint = resumable._matching_checkpoint(section, period, max_symbols)
    prior_partial = section.get("resilient_ablation_partial")
    partial_matches = bool(
        isinstance(prior_partial, dict)
        and resumable._request_matches(prior_partial, period, max_symbols)
        and prior_partial.get("engine_version") == lab.VERSION
    )
    can_resume = bool(prior_checkpoint or partial_matches)
    section["queued_request"] = {
        "period": period,
        "max_symbols": max_symbols,
        "force": force,
        "include_ablation": include_ablation,
        "resume": can_resume and not force,
    }
    section["status"] = "queued"
    core.save_state(core.portfolio)

    resumable._background_run(
        core,
        period=period,
        max_symbols=max_symbols,
        force=force,
        include_ablation=include_ablation,
    )

    section = lab._section(core)
    result = section.get("latest")
    if not isinstance(result, dict) or section.get("status") != "ok":
        runner = section.get("resilient_runner")
        error = section.get("async_launcher_error")
        failure = {
            "status": "error",
            "type": "performance_audit_v2_offline_result",
            "runner_version": VERSION,
            "engine_version": lab.VERSION,
            "error": error or "isolated research run did not produce an ok result",
            "runner": runner if isinstance(runner, dict) else {},
        }
        _atomic_json(output, failure)
        return failure

    artifact = {
        "status": "ok",
        "type": "performance_audit_v2_offline_result",
        "runner_version": VERSION,
        "engine_version": lab.VERSION,
        "generated_utc": OfflineResearchCore.local_ts_text(),
        "source_commit": os.environ.get("GITHUB_SHA") or os.environ.get("SOURCE_COMMIT"),
        "execution_boundary": {
            "isolated_process": True,
            "production_web_worker": False,
            "paper_runner": False,
            "broker_access": False,
            "order_authority": False,
        },
        "request": {
            "period": period,
            "max_symbols": max_symbols,
            "include_ablation": include_ablation,
            "resumed": can_resume and not force,
        },
        "result": result,
    }
    _atomic_json(output, artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="5y", choices=("2y", "3y", "5y", "10y"))
    parser.add_argument("--max-symbols", type=int, default=45)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not 20 <= args.max_symbols <= 75:
        parser.error("--max-symbols must be between 20 and 75")
    result = execute(
        period=args.period,
        max_symbols=args.max_symbols,
        include_ablation=not args.no_ablation,
        checkpoint=args.checkpoint,
        output=args.output,
        force=args.force,
    )
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
