"""Outermost cache-preservation guard for the regime-integrity market wrapper."""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict

VERSION = "regime-integrity-cache-guard-2026-07-29-v1"
_TARGET_VERSION_PREFIX = "regime-integrity-underdeployment-"
_LOCK = threading.RLock()
_WATCHDOG_STARTED: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def install(core: Any) -> Dict[str, Any]:
    global _LAST_INSTALL
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        current = getattr(core, "market_status", None)
        patched = False
        if callable(current) and not getattr(current, "_regime_integrity_cache_guard", False):
            def cached_market_status(force: bool = False, __prior=current):
                try:
                    cache = getattr(core, "_market_cache", None)
                    data = _d(cache.get("data")) if isinstance(cache, dict) else {}
                    integrity = _d(data.get("regime_integrity"))
                    ttl = int(getattr(core, "MARKET_CACHE_TTL", 300) or 300)
                    age = time.time() - _f(cache.get("ts")) if isinstance(cache, dict) else float("inf")
                    version = str(integrity.get("version") or "")
                    if (
                        not force
                        and version.startswith(_TARGET_VERSION_PREFIX)
                        and age >= 0
                        and age < ttl
                    ):
                        return data
                except Exception:
                    pass
                return __prior(force=force)

            cached_market_status._regime_integrity_cache_guard = True
            cached_market_status._regime_integrity_guard = bool(
                getattr(current, "_regime_integrity_guard", False)
            )
            cached_market_status._regime_integrity_version = getattr(
                current, "_regime_integrity_version", None
            )
            cached_market_status._regime_integrity_cache_version = VERSION
            cached_market_status._regime_integrity_prior = current
            core.market_status = cached_market_status
            patched = True

        active = getattr(core, "market_status", None)
        _LAST_INSTALL = {
            "status": "ok",
            "version": VERSION,
            "generated_local": _now(core),
            "patched_this_call": patched,
            "cache_guard_active": bool(
                getattr(active, "_regime_integrity_cache_guard", False)
            ),
            "regime_guard_visible": bool(
                getattr(active, "_regime_integrity_guard", False)
            ),
            "market_callable": getattr(active, "__qualname__", None),
            "market_cache_ttl_seconds": int(getattr(core, "MARKET_CACHE_TTL", 300) or 300),
        }
        return dict(_LAST_INSTALL)


def start_watchdog(core: Any) -> Dict[str, Any]:
    install(core)
    if core is None or id(core) in _WATCHDOG_STARTED:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": core is not None and id(core) in _WATCHDOG_STARTED,
        }

    _WATCHDOG_STARTED.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics
                    runtime_diagnostics.record_exception(
                        exc,
                        source="regime_integrity_cache_guard.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="regime-integrity-cache-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


def status_payload(core: Any) -> Dict[str, Any]:
    active = getattr(core, "market_status", None)
    return {
        "status": "ok" if getattr(active, "_regime_integrity_cache_guard", False) else "warn",
        "overall": "pass" if getattr(active, "_regime_integrity_cache_guard", False) else "warn",
        "type": "regime_integrity_cache_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "last_install": dict(_LAST_INSTALL),
    }
