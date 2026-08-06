"""Bounded market-data reliability guard for the paper runtime.

The canonical ``download_prices`` owner filters static/dynamically backed-off
symbols through ``yfinance_data_hygiene`` and isolates failures by symbol.
A provider-wide circuit opens only after several recent timeout/error failures
across several distinct symbols. Empty/no-data responses never open the global
circuit by themselves.

No signal rules, thresholds, sizing, risk controls, order logic, live authority,
or ML authority are changed.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Sequence

VERSION = "market-data-resilience-2026-08-06-v3-distinct-symbol-breaker"
REQUEST_TIMEOUT_SECONDS = max(2.0, float(os.environ.get("MARKET_DATA_REQUEST_TIMEOUT_SECONDS", "8")))
SYMBOL_FAILURE_THRESHOLD = max(2, int(os.environ.get("MARKET_DATA_SYMBOL_FAILURE_THRESHOLD", "3")))
SYMBOL_BACKOFF_SECONDS = max(15, int(os.environ.get("MARKET_DATA_SYMBOL_BACKOFF_SECONDS", "45")))
PROVIDER_WINDOW_SECONDS = max(10, int(os.environ.get("MARKET_DATA_PROVIDER_WINDOW_SECONDS", "30")))
PROVIDER_FAILURE_THRESHOLD = max(4, int(os.environ.get("MARKET_DATA_PROVIDER_FAILURE_THRESHOLD", "6")))
PROVIDER_DISTINCT_SYMBOL_THRESHOLD = max(3, int(os.environ.get("MARKET_DATA_PROVIDER_DISTINCT_SYMBOL_THRESHOLD", "4")))
PROVIDER_CIRCUIT_OPEN_SECONDS = max(10, int(os.environ.get("MARKET_DATA_PROVIDER_CIRCUIT_OPEN_SECONDS", "30")))
MAX_EVENTS = max(20, int(os.environ.get("MARKET_DATA_MAX_EVENTS", "200")))

_SPLIT_RE = re.compile(r"[\s,]+")
_LOCK = threading.RLock()
_PATCHED_MODULE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_EVENTS: List[Dict[str, Any]] = []
_TOTALS: Dict[str, int] = {
    "requests": 0,
    "successes": 0,
    "failures": 0,
    "timeouts": 0,
    "empty": 0,
    "symbol_backoff_skips": 0,
    "provider_circuit_skips": 0,
    "hygiene_blocked": 0,
}
_SYMBOL_STATE: Dict[str, Dict[str, Any]] = {}
_PROVIDER_FAILURES: List[Dict[str, Any]] = []
_PROVIDER_CIRCUIT_OPEN_UNTIL = 0.0
_LAST_ERROR: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "download_prices"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "download_prices"):
            return module
    return None


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize(value: Any) -> str:
    try:
        return str(value or "").strip().upper().lstrip("$")
    except Exception:
        return ""


def _symbols(value: Any) -> List[str]:
    if isinstance(value, str):
        values = [item for item in _SPLIT_RE.split(value.strip()) if item]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        symbol = _normalize(item)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _rebuild(original: Any, symbols: Sequence[str]) -> Any:
    if isinstance(original, str):
        return symbols[0] if len(symbols) == 1 else " ".join(symbols)
    if isinstance(original, tuple):
        return tuple(symbols)
    if isinstance(original, set):
        return set(symbols)
    return list(symbols)


def _record(symbols: Sequence[str], period: str, interval: str, started: float, status: str, error: str = "") -> None:
    global _LAST_ERROR
    row: Dict[str, Any] = {
        "generated_local": _now(),
        "symbols": list(symbols),
        "period": str(period),
        "interval": str(interval),
        "duration_ms": round((time.monotonic() - started) * 1000.0, 1),
        "status": status,
    }
    if error:
        row["error"] = error[:500]
        _LAST_ERROR = dict(row)
    with _LOCK:
        _EVENTS.append(row)
        del _EVENTS[:-MAX_EVENTS]


def _is_empty(frame: Any) -> bool:
    return frame is None or bool(getattr(frame, "empty", True))


def _sanitize(symbol: Any) -> tuple[Any, List[str], List[Dict[str, Any]]]:
    try:
        import yfinance_data_hygiene as hygiene
        return hygiene.sanitize_tickers(symbol)
    except Exception:
        requested = _symbols(symbol)
        return _rebuild(symbol, requested), requested, []


def _prune_provider_failures(now: float) -> None:
    cutoff = now - PROVIDER_WINDOW_SECONDS
    _PROVIDER_FAILURES[:] = [row for row in _PROVIDER_FAILURES if float(row.get("ts") or 0.0) >= cutoff]


def _symbol_allowed(symbol: str, now: float) -> bool:
    with _LOCK:
        return float((_SYMBOL_STATE.get(symbol) or {}).get("blocked_until") or 0.0) <= now


def _register_failure(symbols: Sequence[str], failure_type: str, error: str) -> None:
    global _PROVIDER_CIRCUIT_OPEN_UNTIL
    now = time.time()
    with _LOCK:
        _TOTALS["failures"] += 1
        if failure_type == "timeout":
            _TOTALS["timeouts"] += 1
        elif failure_type == "empty":
            _TOTALS["empty"] += 1
        for symbol in symbols:
            row = dict(_SYMBOL_STATE.get(symbol) or {})
            count = int(row.get("consecutive_failures") or 0) + 1
            row.update({
                "consecutive_failures": count,
                "last_failure_type": failure_type,
                "last_error": error[:500],
                "updated_ts": now,
            })
            if count >= SYMBOL_FAILURE_THRESHOLD:
                row["blocked_until"] = now + SYMBOL_BACKOFF_SECONDS
            _SYMBOL_STATE[symbol] = row
            if failure_type in {"timeout", "error"}:
                _PROVIDER_FAILURES.append({"ts": now, "symbol": symbol, "failure_type": failure_type})
        _prune_provider_failures(now)
        distinct = {str(row.get("symbol") or "") for row in _PROVIDER_FAILURES if row.get("symbol")}
        if len(_PROVIDER_FAILURES) >= PROVIDER_FAILURE_THRESHOLD and len(distinct) >= PROVIDER_DISTINCT_SYMBOL_THRESHOLD:
            _PROVIDER_CIRCUIT_OPEN_UNTIL = now + PROVIDER_CIRCUIT_OPEN_SECONDS


def _register_success(symbols: Sequence[str]) -> None:
    global _PROVIDER_CIRCUIT_OPEN_UNTIL
    now = time.time()
    with _LOCK:
        _TOTALS["successes"] += 1
        for symbol in symbols:
            _SYMBOL_STATE.pop(symbol, None)
        _prune_provider_failures(now)
        if not _PROVIDER_FAILURES:
            _PROVIDER_CIRCUIT_OPEN_UNTIL = 0.0


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    current = getattr(core, "download_prices", None)
    if not callable(current):
        return {"status": "pending", "version": VERSION, "reason": "download_prices_missing"}
    if getattr(current, "_market_data_resilience_version", None) == VERSION:
        _PATCHED_MODULE_IDS.add(id(core))
        return status_payload(core)

    original = getattr(current, "_market_data_resilience_original", current)

    def guarded_download_prices(symbol: Any, period: str = "5d", interval: str = "5m"):
        started = time.monotonic()
        now = time.time()
        cleaned, requested, hygiene_blocked = _sanitize(symbol)
        if hygiene_blocked:
            with _LOCK:
                _TOTALS["hygiene_blocked"] += len(hygiene_blocked)
            _record([str(row.get("symbol") or "") for row in hygiene_blocked], period, interval, started, "hygiene_blocked")
        if not requested:
            return None

        allowed = [item for item in requested if _symbol_allowed(item, now)]
        locally_blocked = [item for item in requested if item not in allowed]
        if locally_blocked:
            with _LOCK:
                _TOTALS["symbol_backoff_skips"] += len(locally_blocked)
            _record(locally_blocked, period, interval, started, "symbol_backoff")
        if not allowed:
            return None

        with _LOCK:
            _TOTALS["requests"] += 1
            provider_open = now < _PROVIDER_CIRCUIT_OPEN_UNTIL
        if provider_open:
            with _LOCK:
                _TOTALS["provider_circuit_skips"] += 1
            _record(allowed, period, interval, started, "provider_circuit_open")
            return None

        cleaned = _rebuild(cleaned, allowed)
        try:
            frame = core.yf.download(
                cleaned,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                timeout=REQUEST_TIMEOUT_SECONDS,
                threads=False,
            )
            if _is_empty(frame):
                _register_failure(allowed, "empty", "empty yfinance response")
                _record(allowed, period, interval, started, "empty")
                return None
            _register_success(allowed)
            _record(allowed, period, interval, started, "ok")
            return frame
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            timeout_like = "timeout" in text.lower() or "timed out" in text.lower() or "curl: (28)" in text.lower()
            failure_type = "timeout" if timeout_like else "error"
            _register_failure(allowed, failure_type, text)
            _record(allowed, period, interval, started, failure_type, text)
            return None

    guarded_download_prices._market_data_resilience_version = VERSION  # type: ignore[attr-defined]
    guarded_download_prices._market_data_resilience_original = original  # type: ignore[attr-defined]
    core.download_prices = guarded_download_prices
    _PATCHED_MODULE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    now = time.time()
    current = getattr(core, "download_prices", None) if core is not None else None
    direct_marker = bool(getattr(current, "_market_data_resilience_version", None) == VERSION)
    installed_in_process = bool(core is not None and id(core) in _PATCHED_MODULE_IDS)
    with _LOCK:
        _prune_provider_failures(now)
        recent = list(_EVENTS[-50:])
        totals = dict(_TOTALS)
        provider_open_until = float(_PROVIDER_CIRCUIT_OPEN_UNTIL)
        last_error = dict(_LAST_ERROR)
        failures = list(_PROVIDER_FAILURES)
        symbol_states = {
            symbol: {
                "consecutive_failures": int(row.get("consecutive_failures") or 0),
                "last_failure_type": str(row.get("last_failure_type") or ""),
                "seconds_remaining": max(0.0, round(float(row.get("blocked_until") or 0.0) - now, 1)),
                "last_error": str(row.get("last_error") or "")[:300],
            }
            for symbol, row in _SYMBOL_STATE.items()
            if int(row.get("consecutive_failures") or 0) > 0
        }
    durations = [float(row.get("duration_ms") or 0.0) for row in recent if row.get("status") == "ok"]
    installed = bool(direct_marker or installed_in_process)
    distinct = sorted({str(row.get("symbol") or "") for row in failures if row.get("symbol")})
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None and installed else "warn" if core is not None else "pending",
        "type": "market_data_resilience_status",
        "version": VERSION,
        "installed": installed,
        "installed_direct_marker": direct_marker,
        "installed_in_process_registry": installed_in_process,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "symbol_failure_threshold": SYMBOL_FAILURE_THRESHOLD,
        "symbol_backoff_seconds": SYMBOL_BACKOFF_SECONDS,
        "provider_window_seconds": PROVIDER_WINDOW_SECONDS,
        "provider_failure_threshold": PROVIDER_FAILURE_THRESHOLD,
        "provider_distinct_symbol_threshold": PROVIDER_DISTINCT_SYMBOL_THRESHOLD,
        "provider_circuit_open": bool(now < provider_open_until),
        "provider_circuit_seconds_remaining": max(0.0, round(provider_open_until - now, 1)),
        "provider_failure_rows_in_window": len(failures),
        "provider_distinct_symbols_in_window": distinct,
        "symbol_states": symbol_states,
        "totals": totals,
        "average_success_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "last_error": last_error,
        "recent_events": recent,
        "regression_guards": {
            "empty_or_missing_data_cannot_open_global_circuit": True,
            "global_circuit_requires_distinct_symbols": True,
            "symbol_failures_are_isolated": True,
        },
        "authority": {
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_risk_or_sizing": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
        "logic_changed": False,
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
    path = "/paper/provider-health-status"
    if path not in existing:
        flask_app.add_url_rule(path, "provider_health_status", lambda: jsonify(status_payload(core or _mod())))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
