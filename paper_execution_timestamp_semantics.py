"""Normalize execution timestamp and side semantics for Stable Paper accounting.

Canonical ``record_trade`` rows store ``time`` as epoch seconds, while historical
rows may carry ISO/local timestamp strings.  The bidirectional reconciler needs a
calendar-day string so realized P&L for the current session is reconstructed
correctly.  This compatibility shim also refuses to silently coerce an unknown
canonical side to ``long``.

The pre-bridge market-surge paper path wrote verified entry rows directly to
``state.trades`` using ``entry`` for the fill price, ``side=buy``, and explicit
``source/type`` markers.  Those narrowly identified rows are accepted so the
clean epoch can reconcile them without fabricating executions.  Future surge
entries are routed through the canonical ``record_trade`` boundary by the surge
canonical-execution bridge.

Paper-accounting compatibility only.  No strategy, threshold, sizing, order,
risk-limit, live-authority, or ML-authority behavior is changed.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Tuple

VERSION = "paper-execution-timestamp-semantics-2026-08-11-v2-surge-entry"
_APPLIED = False


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _timestamp_text(row: Dict[str, Any]) -> str:
    raw = row.get("timestamp")
    if raw in (None, ""):
        raw = row.get("time")
    if raw in (None, ""):
        raw = row.get("ts_local")
    if raw in (None, ""):
        raw = row.get("created_at")
    if raw in (None, ""):
        return ""

    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return dt.datetime.fromtimestamp(float(raw), tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(raw)

    text = str(raw).strip()
    if text:
        try:
            numeric = float(text)
            if 946684800 <= numeric <= 4102444800:
                return dt.datetime.fromtimestamp(numeric, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            pass
    return text


def _verified_legacy_surge_entry(row: Dict[str, Any]) -> bool:
    source = str(row.get("source") or "").strip().lower()
    row_type = str(row.get("type") or "").strip().lower()
    side = str(row.get("side") or "").strip().lower()
    return (
        source == "market_surge_deployment_mode"
        and row_type == "paper_market_surge_deployment"
        and side in {"buy", "b", "long"}
        and _f(row.get("entry"), 0.0) > 0.0
        and _f(row.get("shares", row.get("qty", row.get("quantity"))), 0.0) > 0.0
        and bool(str(row.get("symbol") or row.get("ticker") or "").strip())
    )


def normalized_event_fields(row: Dict[str, Any]) -> Tuple[str, str, str, float, float, str]:
    symbol = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
    action = str(row.get("action") or "").lower().strip()
    raw_side = str(row.get("side") or row.get("direction") or "").lower().strip()
    qty = _f(row.get("qty", row.get("shares", row.get("quantity"))), 0.0)
    price = _f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0)
    timestamp = _timestamp_text(row)

    legacy_surge_entry = _verified_legacy_surge_entry(row)
    if price <= 0.0 and legacy_surge_entry:
        price = _f(row.get("entry"), 0.0)

    long_aliases = {"long", "buy", "b", "open_long", "close_long", "sell", "s"}
    short_aliases = {"short", "open_short", "close_short", "cover"}

    if raw_side in short_aliases:
        side = "short"
    elif raw_side in long_aliases:
        side = "long"
    elif action in {"open_short", "close_short", "cover"}:
        side = "short"
    elif action in {"open_long", "close_long"}:
        side = "long"
    else:
        side = ""

    if action in {"entry", "buy", "open", "open_long", "open_short"}:
        event = "entry"
    elif action in {"exit", "partial_exit", "sell", "close", "close_long", "close_short", "cover"}:
        event = "exit"
    elif legacy_surge_entry:
        event, side = "entry", "long"
    elif raw_side in {"buy", "b"}:
        event, side = "entry", "long"
    elif raw_side in {"sell", "s"}:
        event, side = "exit", "long"
    else:
        event = action

    return symbol, event, side, qty, price, timestamp


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import paper_bidirectional_accounting_guard as bidirectional
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    bidirectional._event_fields = normalized_event_fields
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "paper_execution_timestamp_semantics_status",
        "version": VERSION,
        "applied": _APPLIED,
        "epoch_seconds_normalized": True,
        "unknown_side_fails_coverage": True,
        "verified_legacy_surge_entry_supported": True,
        "authority": {
            "paper_accounting_compatibility_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)


try:
    apply(None)
except Exception:
    pass
