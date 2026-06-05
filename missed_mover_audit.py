"""Advisory missed-mover audit.

Read-only route for checking why a symbol such as MNTS may not have been entered.
It does not scan, trade, resize, change thresholds, or alter ML authority.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

VERSION = "missed-mover-audit-2026-06-04-v1"
REGISTERED_APP_IDS: set[int] = set()

MICROCAP_MARKET_CAP = 300_000_000
SMALLCAP_MARKET_CAP = 2_000_000_000

SPACE_KEYWORDS = ("space", "aerospace", "satellite", "rocket",