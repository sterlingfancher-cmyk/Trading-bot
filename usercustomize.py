"""Auxiliary startup fallback for monitoring and advisory guard routes."""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-space-stock-basket-2026-06-16-v4"
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


def _patch_self_check_endpoints() -> None:
    try:
        import one_link_check
        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/breakout-participation-status", "category": "governance", "required": False, "after": "/paper/market-participation-accelerator-status"},
            {"path": "/paper/breakout-leaders", "category": "governance", "required": False, "after": "/paper/breakout-participation-status"},
            {"path": "/paper/fmp-limited-access-guard-status", "category": "governance", "required": False, "after": "/paper/analyst-valuation-risk-status"},
            {"path": "/paper/fmp-cached-profile-label-guard-status", "category": "governance", "required": False, "after": "/paper/fmp-limited-access-guard-status"},
            {"path": "/paper/profit-maturity-rotation-status", "category": "governance", "required": False, "after": "/paper/fmp-cached-profile-label-guard-status"},
            {"path": "/paper/post-harvest-redeployment-status", "category": "governance", "required": False, "after": "/paper/profit-maturity-rotation-status"},
            {"path": "/paper/post-harvest-entry-fallback-status", "category": "governance", "required": False, "after": "/paper/post-harvest-redeployment-status"},
            {"path": "/paper/post-harvest-opportunity-governor-status", "category": "governance", "required": False, "after": "/paper/post-harvest-entry-fallback-status"},
            {"path": "/paper/space-stock-basket-status", "category": "governance", "required": False, "after": "/paper/post-harvest-opportunity-governor-status"},
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _register_module(flask_app: Any, m: Any | None, module_name: str, route_args: str = "app_and_module") -> None:
    try:
        module = __import__(module_name)
        core = _mod() or m
        for fn_name in ("install", "apply_runtime_overrides", "apply"):
            fn = getattr(module, fn_name, None)
            if callable(fn):
                try:
                    fn(core)
                except TypeError:
                    fn()
                break
        if flask_app is not None and hasattr(module, "register_routes"):
            try:
                if route_args == "app_only":
                    module.register_routes(flask_app)
                else:
                    module.register_routes(flask_app, core)
            except TypeError:
                module.register_routes(flask_app)
    except Exception:
        pass


def _register_breakout_participation(flask_app: Any, m: Any | None = None) -> None:
    _register_module(flask_app, m, "breakout_participation_layer", route_args="app_only")


def _register_auxiliary_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    _patch_self_check_endpoints()
    for module_name, route_args in (
        ("runner_safety", "app_and_module"),
        ("journal_truth", "app_and_module"),
        ("live_volatility", "app_and_module"),
        ("self_check", "app_and_module"),
        ("breakout_participation_layer", "app_only"),
        ("fmp_limited_access_guard", "app_and_module"),
        ("fmp_cached_profile_label_guard", "app_and_module"),
        ("profit_maturity_rotation_layer", "app_and_module"),
        ("post_harvest_redeployment_controller", "app_and_module"),
        ("post_harvest_entry_fallback", "app_and_module"),
        ("post_harvest_opportunity_governor", "app_and_module"),
        ("space_stock_basket", "app_and_module"),
    ):
        _register_module(flask_app, m, module_name, route_args=route_args)
    _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(1200):
        try:
            _patch_self_check_endpoints()
            m = _mod()
            flask_app = getattr(m, "app", None) if m is not None else None
            if flask_app is not None:
                _register_auxiliary_routes(flask_app, m)
                _register_module(flask_app, m, "post_harvest_redeployment_controller", route_args="app_and_module")
                _register_module(flask_app, m, "post_harvest_entry_fallback", route_args="app_and_module")
                _register_module(flask_app, m, "post_harvest_opportunity_governor", route_args="app_and_module")
                _register_module(flask_app, m, "space_stock_basket", route_args="app_and_module")
        except Exception:
            pass
        time.sleep(0.1)


try:
    from flask import Flask
    if not getattr(Flask.__init__, "_auxiliary_usercustomize_patched", False):
        _original_init = Flask.__init__
        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                _register_auxiliary_routes(self, _mod())
            except Exception:
                pass
        _patched_init._auxiliary_usercustomize_patched = True
        Flask.__init__ = _patched_init
except Exception:
    pass

try:
    threading.Thread(target=_watchdog, daemon=True).start()
except Exception:
    pass
