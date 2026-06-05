"""Runtime module registry and startup verification.
Read-only. Reports critical overlay import/route status. No trading authority.
"""
from __future__ import annotations
import datetime as dt, os, sys
from typing import Any, Dict

VERSION = "runtime-module-registry-2026-06-04-v1-safe"
ENABLED = os.environ.get("RUNTIME_MODULE_REGISTRY_ENABLED", "true").lower() not in {"0", "false