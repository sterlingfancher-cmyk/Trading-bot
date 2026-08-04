"""Process-wide provider timeout contract for the paper web worker.

The contract wraps yfinance.download once and supplies a bounded timeout when a
caller did not provide one. It preserves the requested symbols, periods,
intervals, adjustment settings, and threading choices. It does not alter signal
logic, thresholds, sizing, risk, or order authority.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import threading
import time
from typing import Any, Dict

VERSION = "provider-timeout-contract-2026-08-04-v1"
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("YF_DOWNLOAD_TIMEOUT_SECONDS", "8"))
MAX_TIMEOUT_SECONDS = float(os.environ.get("YF_DOWNLOAD_MAX_TIMEOUT_SECONDS", "12"))
_LOCK = threading.RLock()
_ORIGINAL_DOWNLOAD: Any = None
_INSTALLED = False
_HEALTH: Dict[str, Any] = {
    "calls": 0,
    "completed": 0,
    "failed": 0,
    "active": 0,
    "last_started_local": None,
    "last_completed_local": None,
    "last_duration_seconds": None,
    "max_duration_seconds": 0.0,
    "last_error": None,
}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _timeout(value: Any = None) -> float:
    try:
        requested = float(DEFAULT_TIMEOUT_SECONDS if value is None else value)
    except (TypeError, ValueError):
        requested = DEFAULT_TIMEOUT_SECONDS
    return max(1.0, min(requested, MAX_TIMEOUT_SECONDS))


def apply(core: Any = None) -> Dict[str, Any]:
    global _ORIGINAL_DOWNLOAD, _INSTALLED
    with _LOCK:
        try:
            import yfinance as yf
        except Exception as exc:
            return {"status": "error", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

        current = getattr(yf, "download", None)
        if not callable(current):
            return {"status": "error", "version": VERSION, "error": "yfinance.download_missing"}
        if getattr(current, "_provider_timeout_contract", False):
            _INSTALLED = True
            return status_payload(core)

        _ORIGINAL_DOWNLOAD = current

        @functools.wraps(current)
        def bounded_download(*args, **kwargs):
            started = time.monotonic()
            with _LOCK:
                _HEALTH["calls"] = int(_HEALTH.get("calls", 0)) + 1
                _HEALTH["active"] = int(_HEALTH.get("active", 0)) + 1
                _HEALTH["last_started_local"] = _now()
            supplied_timeout = "timeout" in kwargs
            kwargs["timeout"] = _timeout(kwargs.get("timeout"))
            try:
                try:
                    result = current(*args, **kwargs)
                except TypeError as exc:
                    # Compatibility fallback for older yfinance versions whose
                    # download signature does not accept timeout.
                    if supplied_timeout or "timeout" not in str(exc).lower():
                        raise
                    retry_kwargs = dict(kwargs)
                    retry_kwargs.pop("timeout", None)
                    result = current(*args, **retry_kwargs)
                with _LOCK:
                    _HEALTH["completed"] = int(_HEALTH.get("completed", 0)) + 1
                    _HEALTH["last_error"] = None
                return result
            except BaseException as exc:
                with _LOCK:
                    _HEALTH["failed"] = int(_HEALTH.get("failed", 0)) + 1
                    _HEALTH["last_error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                duration = round(time.monotonic() - started, 4)
                with _LOCK:
                    _HEALTH["active"] = max(0, int(_HEALTH.get("active", 1)) - 1)
                    _HEALTH["last_completed_local"] = _now()
                    _HEALTH["last_duration_seconds"] = duration
                    _HEALTH["max_duration_seconds"] = max(float(_HEALTH.get("max_duration_seconds") or 0.0), duration)

        bounded_download._provider_timeout_contract = True  # type: ignore[attr-defined]
        bounded_download._provider_timeout_contract_version = VERSION  # type: ignore[attr-defined]
        yf.download = bounded_download
        if core is not None and getattr(core, "yf", None) is not None:
            try:
                core.yf.download = bounded_download
            except Exception:
                pass
        _INSTALLED = True
        return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _INSTALLED else "pending",
        "overall": "pass" if _INSTALLED else "warn",
        "type": "provider_timeout_contract",
        "version": VERSION,
        "installed": _INSTALLED,
        "default_timeout_seconds": _timeout(),
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
        "health": dict(_HEALTH),
        "authority": {
            "changes_market_data_values": False,
            "changes_symbols_or_universe": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/provider-timeout-contract-status" not in existing:
        flask_app.add_url_rule(
            "/paper/provider-timeout-contract-status",
            "provider_timeout_contract_status",
            lambda: jsonify(status_payload(core)),
        )
