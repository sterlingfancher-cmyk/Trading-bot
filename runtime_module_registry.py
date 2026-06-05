"""Runtime module registry and startup verification.
Read-only. Reports critical overlay import/route status. No trading authority.
"""
from __future__ import annotations
import datetime as dt, os, sys
from typing import Any, Dict

VERSION = "runtime-module-registry-2026-06-04-v1"
ENABLED = os.environ.get("RUNTIME_MODULE_REGISTRY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
REGISTERED_APP_IDS = set()
REGISTRY: Dict[str, Dict[str, Any]] = {}
CRITICAL = {
    "state_io_hardening": ["/paper/state-io-status"],
    "runner_safety": ["/paper/runner-safety-status"],
    "trade_journal": ["/paper/trade-journal"],
    "state_journal