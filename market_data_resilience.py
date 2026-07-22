"""Bounded market-data reliability guard for the paper runtime.

Wraps the core ``download_prices`` helper with a yfinance request timeout,
per-symbol timing, bounded telemetry, and a short provider circuit breaker.
It does not change signal rules, thresholds, sizing, risk controls, order logic,
or live/ML authority. Failed or empty downloads remain unavailable exactly as
before; they now fail quickly instead of consuming the Gunicorn worker budget.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading
import time
from typing import Any, Dict, List

VERSION = "market-data-resilience-2026-07-22-v1"
REQUEST_TIMEOUT_SECONDS = max(2.0, float(os.environ.get("MARKET_DATA_REQUEST_TIMEOUT_SECONDS", "8")))
FAILURE_THRESHOLD = max(1, int(os.environ.get("MARKET_DATA_FAILURE_THRESHOLD", "3")))
CIRCUIT_OPEN_SECONDS = max(5, int(os.environ.get("MARKET_DATA_CIRCUIT_OPEN_SECONDS", "60")))
MAX_EVENTS = max(20, int(os.environ.get("MARKET_DATA_MAX_EVENTS", "200")))

_LOCK = threading.RLock()
_PATCHED_MODULE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()
_EVENTS: List[Dict[str, Any]] = []
_TOTALS: Dict[str, int] = {"requests": 0, "successes": 0, "failures": 0, "timeouts": 0, "empty": 0, "circuit_skips": 0}
_CONSECUTIVE_FAILURES = 0
_CIRCUIT_OPEN_UNTIL = 0.0
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


def _record(symbol: str, period: str, interval: str, started: float, status: str, error: str = "") -> None:
    global _LAST_ERROR
    row = {
        "generated_local": _now(),
        "symbol": str(symbol),
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


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    current = getattr(core, "download_prices", None)
    if not callable(current):
        return {"status": "pending", "version": VERSION, "reason": "download_prices_missing"}
    if getattr(current, "_market_data_resilience_version", None) == VERSION:
        return status_payload(core)

    original = getattr(current, "_market_data_resilience_original", current)

    def guarded_download_prices(symbol: str, period: str = "5d", interval: str = "5m"):
        global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN_UNTIL
        started = time.monotonic()
        now = time.time()
        with _LOCK:
            _TOTALS["requests"] += 1
            if now < _CIRCUIT_OPEN_UNTIL:
                _TOTALS["circuit_skips"] += 1
                _record(symbol, period, interval, started, "circuit_open")
                return None

        try:
            # Call yfinance directly so the timeout is guaranteed even when the
            # legacy helper does not expose a timeout parameter.
            frame = core.yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                timeout=REQUEST_TIMEOUT_SECONDS,
                threads=False,
            )
            if _is_empty(frame):
                with _LOCK:
                    _TOTALS["empty"] += 1
                    _TOTALS["failures"] += 1
                    _CONSECUTIVE_FAILURES += 1
                    if _CONSECUTIVE_FAILURES >= FAILURE_THRESHOLD:
                        _CIRCUIT_OPEN_UNTIL = time.time() + CIRCUIT_OPEN_SECONDS
                _record(symbol, period, interval, started, "empty")
                return None
            with _LOCK:
                _TOTALS["successes"] += 1
                _CONSECUTIVE_FAILURES = 0
                _CIRCUIT_OPEN_UNTIL = 0.0
            _record(symbol, period, interval, started, "ok")
            return frame
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            timeout_like = "timeout" in text.lower() or "curl: (28)" in text.lower()
            with _LOCK:
                _TOTALS["failures"] += 1
                if timeout_like:
                    _TOTALS["timeouts"] += 1
                _CONSECUTIVE_FAILURES += 1
                if _CONSECUTIVE_FAILURES >= FAILURE_THRESHOLD:
                    _CIRCUIT_OPEN_UNTIL = time.time() + CIRCUIT_OPEN_SECONDS
            _record(symbol, period, interval, started, "timeout" if timeout_like else "error", text)
            return None

    guarded_download_prices._market_data_resilience_version = VERSION  # type: ignore[attr-defined]
    guarded_download_prices._market_data_resilience_original = original  # type: ignore[attr-defined]
    core.download_prices = guarded_download_prices
    _PATCHED_MODULE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    now = time.time()
    with _LOCK:
        recent = list(_EVENTS[-50:])
        totals = dict(_TOTALS)
        consecutive = int(_CONSECUTIVE_FAILURES)
        open_until = float(_CIRCUIT_OPEN_UNTIL)
        last_error = dict(_LAST_ERROR)
    durations = [float(row.get("duration_ms") or 0.0) for row in recent if row.get("status") == "ok"]
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "market_data_resilience_status",
        "version": VERSION,
        "installed": bool(core is not None and getattr(getattr(core, "download_prices", None), "_market_data_resilience_version", None) == VERSION),
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "failure_threshold": FAILURE_THRESHOLD,
        "circuit_open_seconds": CIRCUIT_OPEN_SECONDS,
        "circuit_open": bool(now < open_until),
        "circuit_seconds_remaining": max(0, round(open_until - now, 1)),
        "consecutive_failures": consecutive,
        "totals": totals,
        "average_success_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "last_error": last_error,
        "recent_events": recent,
        "authority": {
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_risk_or_sizing": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
        "logic_changed": False,
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
