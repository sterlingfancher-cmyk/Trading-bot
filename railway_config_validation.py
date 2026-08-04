#!/usr/bin/env python3
"""Validate that Railway has exactly one canonical deployment configuration.

This check is dependency-free and read-only. It prevents a stale railway.toml,
Procfile, or dashboard-equivalent command from silently diverging from the
validated railway.json startup contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_START_COMMAND = (
    "DEFERRED_WSGI_BOOTSTRAP=true PYTHONPATH=bootstrap:. "
    "gunicorn bootstrap_wsgi:app --bind 0.0.0.0:$PORT "
    "--workers 1 --threads 4 --timeout 180"
)
EXPECTED_HEALTHCHECK_PATH = "/bootstrap-status"
EXPECTED_HEALTHCHECK_TIMEOUT = 120
EXPECTED_PROCFILE = f"web: {EXPECTED_START_COMMAND}"


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
    return report, errors


def main() -> int:
    report, errors = validate()
    output = ROOT / "railway_config_validation_report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
