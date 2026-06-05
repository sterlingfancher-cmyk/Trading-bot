"""Missed mover audit and shadow speculative momentum diagnostics.

Advisory-only. No trading, sizing, risk, ML authority, threshold, scanner, or
entry behavior is changed.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set

VERSION = "missed-mover-audit-2026-06-05-v2-shadow-speculative-momentum"
REGISTERED_APP_IDS: set[int] = set()

SMALL