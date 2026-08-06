#!/usr/bin/env python3
"""Validate that Railway has exactly one canonical deployment configuration.

This check is dependency-free and read-only. It prevents a stale railway.toml,
Procfile, or dashboard-equivalent command from silently diverging from the
validated railway.json startup contract.

The temporary afternoon-audit branch also captures public read-only status
surfaces into the validation artifact. That branch-only capture never mutates
trading state and is not intended for merge.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXPECTED_START_COMMAND = (
    "DEFERRED_WSGI_BOOTSTRAP=true PYTHONPATH=bootstrap:. "
    "gunicorn bootstrap_wsgi:app --bind 0.0.0.0:$PORT "
    "--workers 1 --threads 4 --timeout 180"
)
EXPECTED_HEALTHCHECK_PATH = "/bootstrap-status"
EXPECTED_HEALTHCHECK_TIMEOUT = 120
EXPECTED_PROCFILE = f"web: {EXPECTED_START_COMMAND}"
AFTERNOON_CAPTURE_BRANCH = "afternoon-audit-validation-20260806-clean"


def _capture_afternoon_audit() -> dict[str, Any] | None:
    if os.environ.get("GITHUB_HEAD_REF") != AFTERNOON_CAPTURE_BRANCH:
        return None
    base = "https://web-production-e1796.up.railway.app"
    endpoints = {
        "daily_audit": "/paper/daily-audit",
        "data_integrity_audit": "/paper/data-integrity-audit-status",
        "mae_mfe_integrity": "/paper/mae-mfe-integrity-status",
        "intratrade_path_integrity": "/paper/intratrade-path-integrity-status",
        "yfinance_data_hygiene": "/paper/yfinance-data-hygiene-status",
        "provider_health": "/paper/provider-health-status",
        "paper_status_full": "/paper/status?full=1",
        "scanner_runtime_contract": "/paper/scanner-runtime-contract-status",
        "broad_momentum_status": "/paper/broad-momentum-discovery-status",
        "broad_momentum_candidates": "/paper/broad-momentum-candidates?limit=100",
        "state_persistence": "/paper/state-persistence-contract-status",
        "cycle_completion": "/paper/cycle-completion-contract-status",
        "journal_truth": "/paper/journal-truth-status",
    }
    capture: dict[str, Any] = {
        "base_url": base,
        "read_only": True,
        "capture_type": "afternoon_audit",
        "endpoints": {},
    }
    for name, path in endpoints.items():
        request = urllib.request.Request(
            base + path,
            headers={"Accept": "application/json", "User-Agent": "afternoon-audit-validation/1.2"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                http_status = getattr(response, "status", 200)
            try:
                payload: Any = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = {"raw_text": raw.decode("utf-8", errors="replace")[:20000]}
            capture["endpoints"][name] = {
                "status": "ok",
                "http_status": http_status,
                "path": path,
                "payload": payload,
            }
        except Exception as exc:
            capture["endpoints"][name] = {
                "status": "error",
                "path": path,
                "error": f"{type(exc).__name__}: {exc}",
            }
        time.sleep(0.5)
    return capture


def validate() -> tuple[dict, list[str]]:
    errors: list[str] = []
    railway_json = ROOT / "railway.json"
    railway_toml = ROOT / "railway.toml"
    procfile = ROOT / "Procfile"

    if not railway_json.exists():
        errors.append("railway.json is missing")
        config: dict = {}
    else:
        try:
            config = json.loads(railway_json.read_text(encoding="utf-8"))
        except Exception as exc:
            config = {}
            errors.append(f"railway.json is invalid: {type(exc).__name__}: {exc}")

    if railway_toml.exists():
        errors.append(
            "railway.toml must not coexist with railway.json; remove the legacy config"
        )

    deploy = config.get("deploy") if isinstance(config, dict) else None
    if not isinstance(deploy, dict):
        deploy = {}
        errors.append("railway.json deploy section is missing")

    if deploy.get("startCommand") != EXPECTED_START_COMMAND:
        errors.append(
            "railway.json startCommand does not match the validated deferred bootstrap command"
        )
    if deploy.get("healthcheckPath") != EXPECTED_HEALTHCHECK_PATH:
        errors.append("railway.json healthcheckPath must be /bootstrap-status")
    if deploy.get("healthcheckTimeout") != EXPECTED_HEALTHCHECK_TIMEOUT:
        errors.append("railway.json healthcheckTimeout must be 120 seconds")

    if not procfile.exists():
        errors.append("Procfile is missing")
        procfile_text = ""
    else:
        procfile_text = procfile.read_text(encoding="utf-8").strip()
        if procfile_text != EXPECTED_PROCFILE:
            errors.append("Procfile diverges from railway.json startCommand")

    report = {
        "status": "pass" if not errors else "fail",
        "type": "railway_config_validation",
        "canonical_config": "railway.json",
        "railway_json_present": railway_json.exists(),
        "railway_toml_present": railway_toml.exists(),
        "procfile_present": procfile.exists(),
        "start_command_matches": deploy.get("startCommand") == EXPECTED_START_COMMAND,
        "healthcheck_path_matches": deploy.get("healthcheckPath") == EXPECTED_HEALTHCHECK_PATH,
        "healthcheck_timeout_matches": deploy.get("healthcheckTimeout") == EXPECTED_HEALTHCHECK_TIMEOUT,
        "procfile_matches": procfile_text == EXPECTED_PROCFILE,
        "errors": errors,
    }
    afternoon_capture = _capture_afternoon_audit()
    if afternoon_capture is not None:
        report["afternoon_audit_capture"] = afternoon_capture
    return report, errors


def main() -> int:
    report, errors = validate()
    output = ROOT / "railway_config_validation_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())