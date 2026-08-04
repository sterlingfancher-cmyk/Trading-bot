"""Guarded Python startup loader for the Railway web process.

Python imports ``sitecustomize`` before Gunicorn and the WSGI application. This
shim establishes the advisory-research boundary, loads the existing legacy
startup registrations once, and suppresses only the legacy 0.1-second watchdog
thread that repeatedly reapplies the complete patch stack.

The legacy module remains the source of route and patch behavior. This shim does
not change trading logic, thresholds, risk, sizing, state, orders, live
 authority, or ML authority.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import threading
from pathlib import Path
from typing import Any

VERSION = "guarded-sitecustomize-bootstrap-2026-08-03-v1"


def _isolate_heavy_research() -> bool:
    allow = os.environ.get("WEB_WORKER_ALLOW_HEAVY_RESEARCH", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow:
        return False
    os.environ["PERFORMANCE_AUDIT_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED"] = "false"
    os.environ["PERFORMANCE_AUDIT_V2_ENABLED"] = "false"
    return True


RESEARCH_ISOLATED = _isolate_heavy_research()
_ROOT = Path(__file__).resolve().parents[1]
_LEGACY_PATH = _ROOT / "sitecustomize.py"
_LEGACY_MODULE_NAME = "_trading_bot_legacy_sitecustomize"
_REAL_THREAD = threading.Thread
_SUPPRESSED_WATCHDOGS = 0


class _SuppressedThread:
    """Minimal no-op thread returned only for the legacy busy watchdog."""

    daemon = True
    name = "suppressed-legacy-startup-watchdog"

    def start(self) -> None:
        return None

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        return None


def _guarded_thread(*args: Any, **kwargs: Any) -> Any:
    global _SUPPRESSED_WATCHDOGS
    target = kwargs.get("target")
    if target is None and len(args) >= 2:
        target = args[1]
    if (
        getattr(target, "__name__", "") == "_watchdog"
        and getattr(target, "__module__", "") == _LEGACY_MODULE_NAME
    ):
        _SUPPRESSED_WATCHDOGS += 1
        return _SuppressedThread()
    return _REAL_THREAD(*args, **kwargs)


def _load_legacy() -> Any:
    if not _LEGACY_PATH.is_file():
        raise RuntimeError(f"legacy sitecustomize missing: {_LEGACY_PATH}")
    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to create legacy sitecustomize spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module

    original_thread = threading.Thread
    threading.Thread = _guarded_thread  # type: ignore[assignment]
    try:
        spec.loader.exec_module(module)
    finally:
        threading.Thread = original_thread  # type: ignore[assignment]
    return module


LEGACY_MODULE = _load_legacy()

# Preserve compatibility for explicit ``import sitecustomize`` calls in the
# WSGI bootstrap. Public and private registration helpers remain available.
for _name, _value in vars(LEGACY_MODULE).items():
    if _name.startswith("__"):
        continue
    globals().setdefault(_name, _value)

GUARDED_BOOTSTRAP_STATUS = {
    "version": VERSION,
    "research_isolated": RESEARCH_ISOLATED,
    "legacy_loaded": True,
    "legacy_version": getattr(LEGACY_MODULE, "VERSION", None),
    "suppressed_legacy_watchdogs": _SUPPRESSED_WATCHDOGS,
    "changes_trading_authority": False,
}
