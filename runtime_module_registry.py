"""Runtime module registry and startup verification.

Read-only observability for the overlay architecture. It reports critical
module import/route status. It never trades or changes authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "runtime-module-registry-2026-06-04-v1"
ENABLED = os.environ.get("RUNTIME_MODULE_REGISTRY_ENABLED