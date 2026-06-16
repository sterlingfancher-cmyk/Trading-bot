"""Direct SpaceX ticker overlay for the scanner universe.

Adds the reported SpaceX public ticker to the active universe as a normal scanner
candidate. This does not force entries and does not bypass price, risk, quality,
sector, bucket, cooldown, or max-position checks.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "spacex-direct-overlay-2026-06-16-v1"
REGISTERED_APP_IDS: set[int] = set()
ENABLED = os.environ.get("SPACEX_DIRECT_OVERLAY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
DIRECT_TICKER = os.environ.get("SPACEX_DIRECT_TICKER", "SPCX").upper().strip()
BUCKET_NAME = "space_stocks"
BUCKET_CONFIG = {
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


def _extend_unique(existing: Any, additions: List[str]) -> List[str]:
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
        return {"status": "disabled", "type": "spacex_direct_overlay_status", "version": VERSION}
    if core is None:
        return {"status": "stand_down", "type": "spacex_direct_overlay_status", "reason": "core_module_unavailable", "version": VERSION}
    if not DIRECT_TICKER:
        return {"status": "stand_down", "type": "spacex_direct_overlay_status", "reason": "empty_direct_ticker", "version": VERSION}

    before = list(getattr(core, "UNIVERSE", [])) if isinstance(getattr(core, "UNIVERSE", []), list) else []
    core.UNIVERSE = _extend_unique(before, [DIRECT_TICKER])  # type: ignore[attr-defined]

    sector_map = getattr(core, "SYMBOL_SECTOR", None)
    if not isinstance(sector_map, dict):
        sector_map = {}
    sector_map[DIRECT_TICKER] = os.environ.get("SPACEX_DIRECT_SECTOR", "XLI").upper().strip() or "XLI"
    core.SYMBOL_SECTOR = sector_map  # type: ignore[attr-defined]

    bucket_map = getattr(core, "SYMBOL_BUCKET", None)
    if not isinstance(bucket_map, dict):
        bucket_map = {}
    bucket_map[DIRECT_TICKER] = BUCKET_NAME
    core.SYMBOL_BUCKET = bucket_map  # type: ignore[attr-defined]

    bucket_config = getattr(core, "BUCKET_CONFIG", None)
    if not isinstance(bucket_config, dict):
        bucket_config = {}
    bucket_config[BUCKET_NAME] = dict(BUCKET_CONFIG)
    core.BUCKET_CONFIG = bucket_config  # type: ignore[attr-defined]

    space_direct = getattr(core, "SPACEX_DIRECT", None)
    if not isinstance(space_direct, list):
        space_direct = []
    core.SPACEX_DIRECT = _extend_unique(space_direct, [DIRECT_TICKER])  # type: ignore[attr-defined]

    space_stocks = getattr(core, "SPACE_STOCKS", None)
    if not isinstance(space_stocks, list):
        space_stocks = []
    core.SPACE_STOCKS = _extend_unique(space_stocks, [DIRECT_TICKER])  # type: ignore[attr-defined]

    after = list(getattr(core, "UNIVERSE", [])) if isinstance(getattr(core, "UNIVERSE", []), list) else []
    added = DIRECT_TICKER in after and DIRECT_TICKER not in before

    return {
        "status": "ok",
        "overall": "pass",
        "type": "spacex_direct_overlay_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "ticker": DIRECT_TICKER,
        "bucket_name": BUCKET_NAME,
        "sector": sector_map.get(DIRECT_TICKER),
        "added_this_apply": added,
        "price_data_required_before_entry": True,
        "paper_only_metadata_overlay": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "does_not_force_entries": True,
        "does_not_bypass_risk_controls": True,
    }


def register_routes(flask_app: Any, core: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/spacex-direct-overlay-status" not in existing:
        flask_app.add_url_rule(
            "/paper/spacex-direct-overlay-status",
            "spacex_direct_overlay_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
