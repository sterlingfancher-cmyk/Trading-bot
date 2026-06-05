"""Advisory missed-mover audit.

Small read-only diagnostic route for checking why a symbol may not have entered.
It does not trade, resize, change thresholds, change risk controls, or alter ML authority.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict

VERSION = "missed-mover-audit-2026-06-04-v1-compact"
REGISTERED_APP_IDS: set[int] = set()
MICROCAP_MARKET_CAP = 300_000_000


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any = None) -> Dict[str, Any]:
    try:
        s = core.load_state()
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _portfolio(core: Any = None) -> Dict[str, Any]:
    try:
        p = getattr(core, "portfolio", {})
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def _lookup_dict(d: Any, symbol