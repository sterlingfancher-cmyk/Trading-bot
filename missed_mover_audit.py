"""Missed mover audit plus shadow-only speculative momentum diagnostics.

Advisory only: no trades, sizing, risk controls, ML authority, thresholds, or
scanner behavior are changed.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set

VERSION = "missed-mover-audit-2026-06-05-v3-compact-shadow-diagnostics"
REGISTERED_APP_IDS: set[int] = set()

SMALL_CAP_ETFS = ["I