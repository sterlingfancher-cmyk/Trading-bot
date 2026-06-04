"""Runtime module registry and startup patch verification.

Read-only observability for the overlay architecture. Records which modules were
attempted at startup, which startup functions returned, and whether expected
routes are present. Does not trade, alter risk controls, or change ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "runtime-module-registry-2026-06-04-v1"
ENABLED = os.environ.get("RUNTIME_MODULE_REGISTRY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
REG