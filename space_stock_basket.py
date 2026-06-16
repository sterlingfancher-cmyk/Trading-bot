"""Space stock basket overlay.

Adds a focused space / space-infrastructure theme to the active scanner universe
without rewriting app.py. The overlay is paper-only metadata and does not place
trades, change ML authority, bypass risk controls, or force entries.

The scanner still has to rank and filter these names normally. The market surge
module can then consider qualifying space leaders through its hybrid stock-leader
path when they appear in scanner state.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "space-stock-basket-2026-06-16-v1"
REGISTERED_APP_IDS: set[int] = set()

ENABLED = os.environ.get("SPACE_STOCK_BASKET_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

SPACE_LAUNCH_LUNAR = ["RKLB", "LUNR", "SPCE"]
SPACE_SATELLITE_CONNECTIVITY = ["ASTS", "IRDM", "GSAT", "VSAT", "SATS"]
SPACE_IMAGING_DATA = ["PL", "BKSY", "SATL", "SPIR"]
SPACE_INFRASTRUCTURE = ["RDW"]

SPACE_STOCKS = list(dict.fromkeys(
    SPACE_LAUNCH_LUNAR
    + SPACE_SATELLITE_CONNECTIVITY
    + SPACE_IMAGING_DATA
    + SPACE_INFRASTRUCTURE
))

SPACE_SECTOR_MAP = {
    "RKLB": "XLI",
    "LUNR": "XLI",
    "SPCE": "XLI",
    "RDW": "XLI",
    "ASTS": "XLK",
    "IRDM": "XLC",
    "GSAT": "XLC",
    "VSAT": "XLC",
    "SATS": "XLC",
    "PL": "XLK",
    "BKSY": "XLK",
    "SATL": "XLK",
    "SPIR": "XLK",
}

SPACE_BUCKET_NAME = "space_stocks"
SPACE_BUCKET_CONFIG = {
    "alloc_factor": float(os.environ.get("SPACE_STOCKS_ALLOC_FACTOR", "0.70")),
    "max_exposure_pct": float(os.environ.get("SPACE_STOCKS_MAX_EXPOSURE_PCT", "0.30")),
    "max_positions": int(os.environ.get("SPACE_STOCKS_MAX_POSITIONS", "3")),
}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now_text(core: Any | None = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _unique_extend(existing: Any, additions: List[str]) -> List[str]:
    base = list(existing) if isinstance(existing, list) else []
    seen = {str(item).upper() for item in base}
    for symbol in additions:
        symbol = str(symbol).upper().strip()
        if symbol and symbol not in seen:
            base.append(symbol)
            seen.add(symbol)
    return base


def apply(core: Any | None = None) -> Dict[str, Any]:
    core = core or _mod()
    if not ENABLED:
        return {"status": "disabled", "type": "space_stock_basket_status", "version": VERSION}
    if core is None:
        return {"status": "stand_down", "type": "space_stock_basket_status", "reason": "core_module_unavailable", "version": VERSION}

    before_universe = list(getattr(core, "UNIVERSE", [])) if isinstance(getattr(core, "UNIVERSE", []), list) else []
    before_count = len(before_universe)

    core.SPACE_LAUNCH_LUNAR = SPACE_LAUNCH_LUNAR  # type: ignore[attr-defined]
    core.SPACE_SATELLITE_CONNECTIVITY = SPACE_SATELLITE_CONNECTIVITY  # type: ignore[attr-defined]
    core.SPACE_IMAGING_DATA = SPACE_IMAGING_DATA  # type: ignore[attr-defined]
    core.SPACE_INFRASTRUCTURE = SPACE_INFRASTRUCTURE  # type: ignore[attr-defined]
    core.SPACE_STOCKS = SPACE_STOCKS  # type: ignore[attr-defined]

    core.UNIVERSE = _unique_extend(before_universe, SPACE_STOCKS)  # type: ignore[attr-defined]

    sector_map = getattr(core, "SYMBOL_SECTOR", None)
    if not isinstance(sector_map, dict):
        sector_map = {}
    for symbol, sector in SPACE_SECTOR_MAP.items():
        sector_map[symbol] = sector
    core.SYMBOL_SECTOR = sector_map  # type: ignore[attr-defined]

    bucket_map = getattr(core, "SYMBOL_BUCKET", None)
    if not isinstance(bucket_map, dict):
        bucket_map = {}
    for symbol in SPACE_STOCKS:
        bucket_map[symbol] = SPACE_BUCKET_NAME
    core.SYMBOL_BUCKET = bucket_map  # type: ignore[attr-defined]

    bucket_config = getattr(core, "BUCKET_CONFIG", None)
    if not isinstance(bucket_config, dict):
        bucket_config = {}
    bucket_config[SPACE_BUCKET_NAME] = dict(SPACE_BUCKET_CONFIG)
    core.BUCKET_CONFIG = bucket_config  # type: ignore[attr-defined]

    after_universe = list(getattr(core, "UNIVERSE", [])) if isinstance(getattr(core, "UNIVERSE", []), list) else []
    added = [symbol for symbol in SPACE_STOCKS if symbol in after_universe and symbol not in before_universe]

    return {
        "status": "ok",
        "overall": "pass",
        "type": "space_stock_basket_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "paper_only_metadata_overlay": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "does_not_force_entries": True,
        "does_not_bypass_risk_controls": True,
        "space_stocks": SPACE_STOCKS,
        "groups": {
            "launch_lunar": SPACE_LAUNCH_LUNAR,
            "satellite_connectivity": SPACE_SATELLITE_CONNECTIVITY,
            "imaging_data": SPACE_IMAGING_DATA,
            "infrastructure": SPACE_INFRASTRUCTURE,
        },
        "bucket_name": SPACE_BUCKET_NAME,
        "bucket_config": SPACE_BUCKET_CONFIG,
        "sector_map": SPACE_SECTOR_MAP,
        "universe_count_before": before_count,
        "universe_count_after": len(after_universe),
        "new_symbols_added_this_apply": added,
        "already_present": [symbol for symbol in SPACE_STOCKS if symbol in before_universe],
    }


def register_routes(flask_app: Any, core: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/space-stock-basket-status" not in existing:
        flask_app.add_url_rule(
            "/paper/space-stock-basket-status",
            "space_stock_basket_status",
            lambda: jsonify(apply(core or _mod())),
        )

    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
