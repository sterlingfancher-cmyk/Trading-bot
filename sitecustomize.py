"""Unified startup bootstrap for trading-bot runtime route patches.

Imported automatically before app.py loads. Keeps Railway startup deterministic by
loading route/scanner/risk patches repeatedly while the Flask app initializes.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import sys
from typing import Any

VERSION = "unified-startup-loader-2026-05-22-risk-on-concentration"
_REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
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
    """Keep the mobile-safe self-check light, but expose diagnostics as linked optional routes."""
    try:
        import one_link_check

        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/breakout-participation-status", "category": "governance", "required": False, "after": "/paper/market-participation-accelerator-status"},
            {"path": "/paper/breakout-leaders", "category": "governance", "required": False, "after": "/paper/breakout-participation-status"},
            {"path": "/paper/paper-exposure-status", "category": "governance", "required": False, "after": "/paper/breakout-leaders"},
            {"path": "/paper/paper-participation-status", "category": "governance", "required": False, "after": "/paper/paper-exposure-status"},
            {"path": "/paper/risk-on-concentration-policy", "category": "governance", "required": False, "after": "/paper/paper-participation-status"},
            {"path": "/paper/breakout-rotation-status", "category": "governance", "required": False, "after": "/paper/risk-on-concentration-policy"},
            {"path": "/paper/research-advisory-status", "category": "governance", "required": False, "after": "/paper/news-risk-status"},
            {"path": "/paper/scanner-research-ranking", "category": "governance", "required": False, "after": "/paper/research-advisory-status"},
            {"path": "/paper/fundamental-score-status", "category": "governance", "required": False, "after": "/paper/scanner-research-ranking"},
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _import_usercustomize() -> None:
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


def _register_module(flask_app: Any, m: Any | None, module_name: str, apply_names: tuple[str, ...] = ("apply_runtime_overrides",), route_args: str = "app_only") -> None:
    try:
        module = __import__(module_name)
        for name in apply_names:
            fn = getattr(module, name, None)
            if callable(fn):
                try:
                    fn(m)
                except TypeError:
                    fn()
                break
        if flask_app is not None and hasattr(module, "register_routes"):
            try:
                if route_args == "app_and_module":
                    module.register_routes(flask_app, m)
                else:
                    module.register_routes(flask_app)
            except TypeError:
                module.register_routes(flask_app, m)
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


def _register_research_advisory(flask_app: Any, m: Any | None) -> None:
    try:
        import research_advisory_engine
        if hasattr(research_advisory_engine, "apply"):
            research_advisory_engine.apply(m)
        if flask_app is not None and hasattr(research_advisory_engine, "register_routes"):
            research_advisory_engine.register_routes(flask_app, m)
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
        "paper_participation_route_registered": "/paper/paper-participation-status" in rules,
        "risk_on_concentration_policy_route_registered": "/paper/risk-on-concentration-policy" in rules,
        "breakout_rotation_route_registered": "/paper/breakout-rotation-status" in rules,
        "research_advisory_route_registered": "/paper/research-advisory-status" in rules,
        "scanner_research_ranking_route_registered": "/paper/scanner-research-ranking" in rules,
        "fundamental_score_route_registered": "/paper/fundamental-score-status" in rules,
        "routes_count": len(rules),
    }


def _register_startup_status(flask_app: Any) -> None:
    if flask_app is None or "/paper/startup-loader-status" in _existing_rules(flask_app):
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
    _register_module(flask_app, m, "breakout_participation_layer")
    _register_module(flask_app, m, "paper_exposure_rotation")
    _register_module(flask_app, m, "paper_participation_allocator")
    _register_module(flask_app, m, "paper_risk_on_concentration_policy", route_args="app_and_module")
    _register_research_advisory(flask_app, m)

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
