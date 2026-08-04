"""Guarded Python startup loader for the Railway web process.

Python imports ``sitecustomize`` before Gunicorn and the WSGI application. This
shim establishes the advisory-research boundary and loads the legacy startup
helpers without executing their eager pre-app registration or 0.1-second retry
thread. The legacy Flask constructor hook remains intact, so registration occurs
once when the application is created.

No trading logic, thresholds, risk, sizing, state, orders, live authority, or ML
authority are changed.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

VERSION = "guarded-sitecustomize-bootstrap-2026-08-03-v2-deferred-registration"


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
_LEGACY_STARTUP_TAIL = """_register_all()
threading.Thread(target=_watchdog, daemon=True).start()
"""


def _load_legacy() -> Any:
    if not _LEGACY_PATH.is_file():
        raise RuntimeError(f"legacy sitecustomize missing: {_LEGACY_PATH}")

    source = _LEGACY_PATH.read_text(encoding="utf-8")
    if _LEGACY_STARTUP_TAIL not in source:
        raise RuntimeError("legacy sitecustomize startup tail not found")
    source = source.replace(
        _LEGACY_STARTUP_TAIL,
        "# Eager registration and the busy watchdog are suppressed by the guarded bootstrap.\n",
        1,
    )

    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_PATH)
    if spec is None:
        raise RuntimeError("unable to create legacy sitecustomize spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    exec(compile(source, str(_LEGACY_PATH), "exec"), module.__dict__)
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
    "eager_registration_suppressed": True,
    "legacy_watchdog_suppressed": True,
    "flask_constructor_registration_preserved": True,
    "changes_trading_authority": False,
}
