"""Fail-closed quote-integrity guard for paper exits.

A paper position should never jump from the normal stop regime to a catastrophic
single-tick exit without quote-integrity review. This module wraps the core full
and partial exit boundaries and blocks only extreme adverse prices that are far
outside the position's entry/peak context.

Paper-only safety control. It does not change signals, sizing, normal stops,
profit taking, live authority, or ML authority.
"""
from __future__ import annotations

import functools
import math
import os
from typing import Any, Dict

VERSION = "paper-exit-price-integrity-2026-08-12-v1"
LONG_MIN_PRICE_RATIO = 0.40
SHORT_MAX_PRICE_RATIO = 2.50
_APPLIED_CORE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _position(core: Any, symbol: str) -> Dict[str, Any]:
    return _d(_d(_portfolio(core).get("positions")).get(str(symbol or "").upper().strip()))


def _entry_anchor(pos: Dict[str, Any]) -> float:
    return _f(pos.get("entry", pos.get("entry_price")), 0.0)


def anomaly(pos: Dict[str, Any], px: Any) -> Dict[str, Any] | None:
    price = _f(px, 0.0)
    entry = _entry_anchor(pos)
    side = str(pos.get("side") or "long").lower().strip()
    if price <= 0.0:
        return {"reason": "nonpositive_or_nonfinite_exit_price", "price": price, "entry": entry, "side": side}
    if entry <= 0.0:
        return None

    ratio = price / entry
    if side == "short":
        if ratio >= SHORT_MAX_PRICE_RATIO:
            return {
                "reason": "catastrophic_short_exit_price_outlier",
                "price": price,
                "entry": entry,
                "price_to_entry_ratio": ratio,
                "side": side,
            }
        return None

    if ratio <= LONG_MIN_PRICE_RATIO:
        return {
            "reason": "catastrophic_long_exit_price_outlier",
            "price": price,
            "entry": entry,
            "price_to_entry_ratio": ratio,
            "side": "long",
        }
    return None


def _mark(core: Any, symbol: str, row: Dict[str, Any], boundary: str) -> None:
    pf = _portfolio(core)
    risk = _d(pf.setdefault("risk_controls", {}))
    diagnostic = {
        **row,
        "symbol": str(symbol or "").upper().strip(),
        "boundary": boundary,
        "version": VERSION,
    }
    risk["paper_exit_price_integrity_block"] = diagnostic
    risk["paper_exit_price_integrity_active"] = True
    if not bool(risk.get("halted", False)):
        risk["halted"] = True
        risk["halt_reason"] = "paper exit quote integrity halt"
    risk["self_defense_active"] = True
    existing = str(risk.get("self_defense_reason") or "").strip()
    marker = "paper exit quote integrity halt"
    if marker not in existing.lower():
        risk["self_defense_reason"] = f"{existing}; {marker}".strip("; ") if existing else marker
    pf["risk_controls"] = risk
    save = getattr(core, "save_state", None)
    if callable(save):
        try:
            save(pf)
        except TypeError:
            save()
        except Exception:
            pass


def _wrap_boundary(core: Any, name: str) -> bool:
    current = getattr(core, name, None)
    if not callable(current):
        return False
    marker = f"_{name}_paper_exit_price_integrity_version"
    if getattr(current, marker, None) == VERSION:
        return True
    prior = getattr(current, f"_{name}_paper_exit_price_integrity_prior", current)

    @functools.wraps(prior)
    def wrapped(symbol, px, *args, **kwargs):
        pos = _position(core, symbol)
        issue = anomaly(pos, px) if pos else None
        if issue is not None:
            _mark(core, symbol, issue, name)
            return None
        return prior(symbol, px, *args, **kwargs)

    setattr(wrapped, marker, VERSION)
    setattr(wrapped, f"_{name}_paper_exit_price_integrity_prior", prior)
    setattr(core, name, wrapped)
    return True


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "skipped", "overall": "pass", "version": VERSION, "reason": "paper_only"}

    full = _wrap_boundary(core, "exit_position")
    partial = _wrap_boundary(core, "reduce_position")
    if full or partial:
        _APPLIED_CORE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core) if core is not None else {}
    risk = _d(pf.get("risk_controls"))
    return {
        "status": "ok" if core is not None and id(core) in _APPLIED_CORE_IDS else "pending",
        "overall": "pass" if core is not None and id(core) in _APPLIED_CORE_IDS else "warn",
        "type": "paper_exit_price_integrity_guard_status",
        "version": VERSION,
        "paper_only": True,
        "long_min_price_ratio": LONG_MIN_PRICE_RATIO,
        "short_max_price_ratio": SHORT_MAX_PRICE_RATIO,
        "active_block": risk.get("paper_exit_price_integrity_block"),
        "authority": {
            "fail_closed_quote_integrity_only": True,
            "changes_normal_stop_thresholds": False,
            "changes_strategy": False,
            "changes_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/exit-price-integrity-status"
        if path not in existing:
            flask_app.add_url_rule(path, "paper_exit_price_integrity_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
