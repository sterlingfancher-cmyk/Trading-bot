"""Expansion impact monitor. Read-only advisory monitor for paper expansion."""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List

VERSION = "expansion-impact-monitor-2026-06-04-v2-observed-outcome-fix"
REGISTERED_APP_IDS: set[int] = set()
BASELINE_EXECUTION_ROWS = int(os.environ.get("EXPANSION_BASELINE_EXECUTION_ROWS", "82"