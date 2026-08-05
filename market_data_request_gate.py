"""Pre-provider symbol gate for the canonical paper market-data helper.

The gate sits outside ``market_data_resilience`` and removes known no-data or
temporarily quarantined symbols before the underlying helper is called. This
prevents one malformed ticker from incrementing the provider-wide failure
counter. It does not alter valid market data, strategy logic, risk, sizing,
order placement, or ML/live authority.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
from typing import Any, Dict, List

VERSION = "market-data-request-gate-2026-08-05-v1"
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_TOTALS: Dict[str, int] = {"requests": 0, "blocked_symbols": 0, "forwarded_symbols": 0}
_LAST_BLOCKED: List[Dict[str, Any]] = []


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "download_prices"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "download_prices"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_not_ready"}
    current = getattr(core, "download_prices", None)
    if not callable(current):
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "download_prices_missing"}
    if getattr(current, "_market_data_request_gate_version", None) == VERSION:
        return status_payload(core)

    prior = current

    def gated_download_prices(symbol: Any, period: str = "5d", interval: str = "5m"):
        global _LAST_BLOCKED
        try:
            import yfinance_data_hygiene as hygiene
            cleaned, allowed, blocked = hygiene.sanitize_tickers(symbol)
        except Exception:
            cleaned, allowed, blocked = symbol, [str(symbol)], []
        with _LOCK:
            _TOTALS["requests"] += 1
            _TOTALS["blocked_symbols"] += len(blocked)
            _TOTALS["forwarded_symbols"] += len(allowed)
            if blocked:
                _LAST_BLOCKED = [dict(row) for row in blocked][-20:]
        if not allowed:
            return None
        return prior(cleaned, period=period, interval=interval)

    gated_download_prices._market_data_request_gate_version = VERSION  # type: ignore[attr-defined]
    gated_download_prices._market_data_request_gate_prior = prior  # type: ignore[attr-defined]
    core.download_prices = gated_download_prices
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    current = getattr(core, "download_prices", None) if core is not None else None
    with _LOCK:
        totals = dict(_TOTALS)
        blocked = [dict(row) for row in _LAST_BLOCKED]
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "market_data_request_gate_status",
        "version": VERSION,
        "generated_local": _now(core),
        "installed": bool(getattr(current, "_market_data_request_gate_version", None) == VERSION),
        "totals": totals,
        "last_blocked": blocked,
        "authority": {
            "changes_entry_rules": False,
            "changes_hard_risk": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_sizing": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
        "execution_authority": "existing_rules_only",
        "ml_authority": "shadow_recommendation_only",
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return install(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    path = "/paper/market-data-request-gate-status"
    if path not in existing:
        flask_app.add_url_rule(path, "market_data_request_gate_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core)


try:
    install(_mod())
except Exception:
    pass
