"""Unified startup bootstrap for trading-bot runtime route patches.

This file is imported automatically by Python before app.py is loaded. It keeps
Railway startup deterministic by importing the fallback usercustomize loader and
then repeatedly applying state-safe route/scan patches while the Flask app and
trading module finish initializing.

Live trade/risk authority remains in app.py. Imported modules may register
advisory/status routes or patch scanner logic only when their own guards allow it.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading
import time
from typing import Any

VERSION = "unified-startup-loader-2026-05-21-paper-exposure-rotation"
_REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    """Find the trading module whether Railway started it as app or __main__."""
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    return None


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _existing_rules(flask_app: Any) -> set[str]:
    try:
        return {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        return set()


def _patch_one_link_check() -> None:
    """Make the one-link self-check include breakout and paper-exposure diagnostics."""
    try:
        import one_link_check

        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {
                "path": "/paper/breakout-participation-status",
                "category": "governance",
                "required": False,
                "after": "/paper/market-participation-accelerator-status",
            },
            {
                "path": "/paper/breakout-leaders",
                "category": "governance",
                "required": False,
                "after": "/paper/breakout-participation-status",
            },
            {
                "path": "/paper/paper-exposure-status",
                "category": "governance",
                "required": False,
                "after": "/paper/breakout-leaders",
            },
            {
                "path": "/paper/breakout-rotation-status",
                "category": "governance",
                "required": False,
                "after": "/paper/paper-exposure-status",
            },
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _import_usercustomize() -> None:
    """Force-load the secondary fallback loader even on platforms that skip it."""
    try:
        import usercustomize
        if hasattr(usercustomize, "_patch_self_check_endpoints"):
            usercustomize._patch_self_check_endpoints()
    except Exception:
        pass


def _register_usercustomize_routes(flask_app: Any, m: Any | None) -> None:
    try:
        import usercustomize
        if hasattr(usercustomize, "_register_auxiliary_routes"):
            usercustomize._register_auxiliary_routes(flask_app, m)
        if hasattr(usercustomize, "_register_breakout_participation"):
            usercustomize._register_breakout_participation(flask_app, m)
    except Exception:
        pass


def _register_risk_bootstrap(flask_app: Any, m: Any | None) -> None:
    try:
        import risk_bootstrap
        if hasattr(risk_bootstrap, "apply_runtime_overrides"):
            risk_bootstrap.apply_runtime_overrides(m)
        if flask_app is not None and hasattr(risk_bootstrap, "register_routes"):
            risk_bootstrap.register_routes(flask_app)
    except Exception:
        pass


def _register_eod_hybrid(flask_app: Any) -> None:
    try:
        import eod_hybrid
        if flask_app is not None and hasattr(eod_hybrid, "_register_routes"):
            eod_hybrid._register_routes(flask_app)
    except Exception:
        pass


def _register_breakout_participation(flask_app: Any, m: Any | None) -> None:
    try:
        import breakout_participation_layer
        if hasattr(breakout_participation_layer, "apply_runtime_overrides"):
            breakout_participation_layer.apply_runtime_overrides(m)
        if flask_app is not None and hasattr(breakout_participation_layer, "register_routes"):
            breakout_participation_layer.register_routes(flask_app)
    except Exception:
        pass


def _register_paper_exposure_rotation(flask_app: Any, m: Any | None) -> None:
    try:
        import paper_exposure_rotation
        if hasattr(paper_exposure_rotation, "apply_runtime_overrides"):
            paper_exposure_rotation.apply_runtime_overrides(m)
        if flask_app is not None and hasattr(paper_exposure_rotation, "register_routes"):
            paper_exposure_rotation.register_routes(flask_app)
    except Exception:
        pass


def _status_payload() -> dict[str, Any]:
    m = _mod()
    flask_app = getattr(m, "app", None) if m is not None else None
    rules = sorted(_existing_rules(flask_app)) if flask_app is not None else []
    return {
        "status": "ok",
        "type": "startup_loader_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "module_found": bool(m is not None),
        "flask_app_found": bool(flask_app is not None),
        "breakout_status_route_registered": "/paper/breakout-participation-status" in rules,
        "breakout_leaders_route_registered": "/paper/breakout-leaders" in rules,
        "paper_exposure_route_registered": "/paper/paper-exposure-status" in rules,
        "breakout_rotation_route_registered": "/paper/breakout-rotation-status" in rules,
        "routes_count": len(rules),
    }


def _register_startup_status(flask_app: Any) -> None:
    if flask_app is None:
        return
    existing = _existing_rules(flask_app)
    if "/paper/startup-loader-status" in existing:
        return
    try:
        from flask import jsonify

        def startup_loader_status():
            return jsonify(_status_payload())

        flask_app.add_url_rule("/paper/startup-loader-status", "startup_loader_status", startup_loader_status)
    except Exception:
        pass


def _register_all(flask_app: Any | None = None, m: Any | None = None) -> None:
    _import_usercustomize()
    _patch_one_link_check()
    m = m or _mod()
    flask_app = flask_app or (getattr(m, "app", None) if m is not None else None)

    if flask_app is not None:
        _register_usercustomize_routes(flask_app, m)
        _register_startup_status(flask_app)

    _register_risk_bootstrap(flask_app, m)
    _register_eod_hybrid(flask_app)
    _register_breakout_participation(flask_app, m)
    _register_paper_exposure_rotation(flask_app, m)

    if flask_app is not None:
        _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(1800):
        try:
            _register_all()
        except Exception:
            pass
        time.sleep(0.1)


try:
    from flask import Flask

    if not getattr(Flask.__init__, "_unified_startup_loader_patched", False):
        _original_init = Flask.__init__

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                _register_all(self, _mod())
            except Exception:
                pass

        _patched_init._unified_startup_loader_patched = True
        Flask.__init__ = _patched_init
except Exception:
    pass

_register_all()
threading.Thread(target=_watchdog, daemon=True).start()
