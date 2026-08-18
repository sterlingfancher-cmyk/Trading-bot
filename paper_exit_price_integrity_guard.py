"""Fail-closed quote-integrity guard for paper valuation and exits.

A paper position should never jump from the normal stop regime to a catastrophic
single-tick valuation or exit without quote-integrity review. This module
protects three independent boundaries:

1. ``latest_price`` rejects a catastrophically implausible terminal 5-minute
   close relative to recent same-symbol bars before that value is cached or
   returned to position management.
2. ``calculate_equity`` refuses to reuse a catastrophically implausible stored
   ``last_price`` when no independently trusted fresh quote can be obtained.
3. Full and partial paper exits retain the existing entry-anchored fail-closed
   guard as a separate safety layer.

Paper-only safety control. It does not change signals, sizing, normal stops,
profit taking, live authority, or ML authority.
"""
from __future__ import annotations

import functools
import math
import os
import statistics
import time
from typing import Any, Dict

VERSION = "paper-exit-price-integrity-2026-08-13-v2-source-plausibility"
LONG_MIN_PRICE_RATIO = 0.40
SHORT_MAX_PRICE_RATIO = 2.50
SOURCE_MIN_PRIOR_BARS = 6
SOURCE_RECENT_PRIOR_BARS = 24
SOURCE_MIN_PRICE_RATIO = 0.40
SOURCE_MAX_PRICE_RATIO = 2.50
SOURCE_CACHE_TTL_SECONDS = 60
_APPLIED_CORE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_LAST_SOURCE_BLOCK: Dict[str, Any] = {}


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


def _source_issue(prices: Any) -> Dict[str, Any] | None:
    try:
        values = [float(value) for value in list(prices)]
    except Exception:
        return None
    values = [value for value in values if math.isfinite(value) and value > 0.0]
    if len(values) < SOURCE_MIN_PRIOR_BARS + 1:
        return None

    terminal = float(values[-1])
    prior = values[:-1][-SOURCE_RECENT_PRIOR_BARS:]
    if len(prior) < SOURCE_MIN_PRIOR_BARS:
        return None
    anchor = float(statistics.median(prior))
    if not math.isfinite(anchor) or anchor <= 0.0:
        return None

    ratio = terminal / anchor
    if ratio <= SOURCE_MIN_PRICE_RATIO or ratio >= SOURCE_MAX_PRICE_RATIO:
        return {
            "reason": "catastrophic_terminal_bar_outlier",
            "price": terminal,
            "recent_median_anchor": anchor,
            "price_to_recent_median_ratio": ratio,
            "prior_bars_used": len(prior),
        }
    return None


def _cached_source_issue(cached_price: float, prices: Any) -> Dict[str, Any] | None:
    try:
        values = [float(value) for value in list(prices)]
    except Exception:
        values = []
    values = [value for value in values if math.isfinite(value) and value > 0.0]
    prior = values[-SOURCE_RECENT_PRIOR_BARS:]
    if len(prior) < SOURCE_MIN_PRIOR_BARS:
        return {
            "reason": "cached_price_plausibility_unverified",
            "price": cached_price,
            "prior_bars_used": len(prior),
        }
    anchor = float(statistics.median(prior))
    if not math.isfinite(anchor) or anchor <= 0.0:
        return {
            "reason": "cached_price_plausibility_unverified",
            "price": cached_price,
            "prior_bars_used": len(prior),
        }
    ratio = cached_price / anchor
    if ratio <= SOURCE_MIN_PRICE_RATIO or ratio >= SOURCE_MAX_PRICE_RATIO:
        return {
            "reason": "catastrophic_cached_price_outlier",
            "price": cached_price,
            "recent_median_anchor": anchor,
            "price_to_recent_median_ratio": ratio,
            "prior_bars_used": len(prior),
        }
    return None


def _mark_source_block(symbol: str, issue: Dict[str, Any]) -> None:
    global _LAST_SOURCE_BLOCK
    _LAST_SOURCE_BLOCK = {
        **issue,
        "symbol": str(symbol or "").upper().strip(),
        "boundary": "latest_price",
        "version": VERSION,
        "blocked_at_epoch": time.time(),
    }


def _wrap_latest_price(core: Any) -> bool:
    current = getattr(core, "latest_price", None)
    price_series = getattr(core, "price_series", None)
    cache = getattr(core, "_price_cache", None)
    if not callable(current) or not callable(price_series) or not isinstance(cache, dict):
        return False

    marker = "_latest_price_paper_exit_price_integrity_version"
    if getattr(current, marker, None) == VERSION:
        return True
    prior = getattr(current, "_latest_price_paper_exit_price_integrity_prior", current)

    @functools.wraps(prior)
    def wrapped(symbol):
        key = str(symbol or "").upper().strip()
        if not key:
            return None
        now = time.time()
        data = cache.setdefault("data", {})
        cached = data.get(key)
        if isinstance(cached, dict) and now - _f(cached.get("ts"), 0.0) < SOURCE_CACHE_TTL_SECONDS:
            cached_price = _f(cached.get("price"), 0.0)
            if cached_price > 0.0:
                validated_version = str(cached.get("source_plausibility_validated_version") or "")
                validated_price = _f(cached.get("source_plausibility_validated_price"), 0.0)
                if validated_version == VERSION and validated_price == cached_price:
                    return cached_price
                try:
                    download = getattr(core, "download_prices", None)
                    if not callable(download):
                        issue = {"reason": "cached_price_plausibility_unverified", "price": cached_price, "prior_bars_used": 0}
                    else:
                        frame = download(key, period="1d", interval="5m")
                        prices = price_series(frame, "Close")
                        issue = _cached_source_issue(cached_price, prices)
                except Exception:
                    issue = {"reason": "cached_price_plausibility_unverified", "price": cached_price, "prior_bars_used": 0}
                if issue is not None:
                    _mark_source_block(key, issue)
                    data.pop(key, None)
                    return None
                cached["source_plausibility_validated_version"] = VERSION
                cached["source_plausibility_validated_price"] = cached_price
                cached["source_plausibility_validated_at"] = now
                return cached_price

        try:
            download = getattr(core, "download_prices", None)
            if not callable(download):
                return None
            frame = download(key, period="1d", interval="5m")
            prices = price_series(frame, "Close")
            if len(prices) == 0:
                return None
            issue = _source_issue(prices)
            if issue is not None:
                _mark_source_block(key, issue)
                return None
            px = _f(prices[-1], 0.0)
            if px <= 0.0:
                return None
            data[key] = {
                "ts": now,
                "price": px,
                "source_plausibility_validated_version": VERSION,
                "source_plausibility_validated_price": px,
                "source_plausibility_validated_at": now,
            }
            return px
        except Exception:
            return None

    setattr(wrapped, marker, VERSION)
    setattr(wrapped, "_latest_price_paper_exit_price_integrity_prior", prior)
    setattr(core, "latest_price", wrapped)
    return True


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


def _wrap_calculate_equity(core: Any) -> bool:
    current = getattr(core, "calculate_equity", None)
    if not callable(current):
        return False

    marker = "_calculate_equity_paper_exit_price_integrity_version"
    if getattr(current, marker, None) == VERSION:
        return True
    prior = getattr(current, "_calculate_equity_paper_exit_price_integrity_prior", current)

    @functools.wraps(prior)
    def wrapped(*args, **kwargs):
        refresh_prices = kwargs.get("refresh_prices", args[0] if args else True)
        pf = _portfolio(core)
        positions = _d(pf.get("positions"))
        for symbol, pos in list(positions.items()):
            if not isinstance(pos, dict):
                continue
            stored_price = _f(pos.get("last_price", pos.get("entry", 0.0)), 0.0)
            stored_issue = anomaly(pos, stored_price)
            if stored_issue is None:
                continue

            if bool(refresh_prices):
                trusted_price = None
                latest = getattr(core, "latest_price", None)
                if callable(latest):
                    try:
                        trusted_price = latest(symbol)
                    except Exception:
                        trusted_price = None
                if trusted_price is not None and anomaly(pos, trusted_price) is None:
                    # The original calculate_equity will immediately call the same
                    # protected latest_price path again. The validated 60-second
                    # cache makes that second call provider-free and lets the normal
                    # owner update last_price/equity without this guard fabricating a
                    # replacement mark.
                    continue

            issue = {
                **stored_issue,
                "stored_mark_reason": stored_issue.get("reason"),
                "reason": "catastrophic_stored_mark_fallback_blocked",
                "stored_price": stored_price,
                "refresh_prices": bool(refresh_prices),
            }
            _mark(core, symbol, issue, "calculate_equity_fallback")
            # Fail closed without invoking the original valuation path. This
            # preserves the prior account snapshot until a trusted fresh quote is
            # available rather than reusing or inventing a catastrophic mark.
            return _f(pf.get("equity"), _f(pf.get("cash"), 0.0))

        return prior(*args, **kwargs)

    setattr(wrapped, marker, VERSION)
    setattr(wrapped, "_calculate_equity_paper_exit_price_integrity_prior", prior)
    setattr(core, "calculate_equity", wrapped)
    return True


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

    source = _wrap_latest_price(core)
    valuation = _wrap_calculate_equity(core)
    full = _wrap_boundary(core, "exit_position")
    partial = _wrap_boundary(core, "reduce_position")
    if source or valuation or full or partial:
        _APPLIED_CORE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core) if core is not None else {}
    risk = _d(pf.get("risk_controls"))
    current_latest = getattr(core, "latest_price", None) if core is not None else None
    current_equity = getattr(core, "calculate_equity", None) if core is not None else None
    source_installed = bool(getattr(current_latest, "_latest_price_paper_exit_price_integrity_version", None) == VERSION)
    valuation_installed = bool(getattr(current_equity, "_calculate_equity_paper_exit_price_integrity_version", None) == VERSION)
    return {
        "status": "ok" if core is not None and id(core) in _APPLIED_CORE_IDS else "pending",
        "overall": "pass" if core is not None and id(core) in _APPLIED_CORE_IDS else "warn",
        "type": "paper_exit_price_integrity_guard_status",
        "version": VERSION,
        "paper_only": True,
        "long_min_price_ratio": LONG_MIN_PRICE_RATIO,
        "short_max_price_ratio": SHORT_MAX_PRICE_RATIO,
        "source_plausibility": {
            "installed": source_installed,
            "min_prior_bars": SOURCE_MIN_PRIOR_BARS,
            "recent_prior_bars": SOURCE_RECENT_PRIOR_BARS,
            "min_price_ratio": SOURCE_MIN_PRICE_RATIO,
            "max_price_ratio": SOURCE_MAX_PRICE_RATIO,
            "last_block": dict(_LAST_SOURCE_BLOCK) if _LAST_SOURCE_BLOCK else None,
        },
        "valuation_fallback": {
            "installed": valuation_installed,
            "fail_closed_on_catastrophic_stored_mark": True,
        },
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