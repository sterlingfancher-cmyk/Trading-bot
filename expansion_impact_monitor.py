"""Expansion impact monitor for paper-only controlled expansion.

Read-only observability layer. Tracks whether the paper expansion is producing
clean, tagged execution data without increasing risk/state warnings.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "expansion-impact-monitor-2026-06-04-v1"
ENABLED = os.environ.get("EXPANSION_IMPACT_MONITOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}