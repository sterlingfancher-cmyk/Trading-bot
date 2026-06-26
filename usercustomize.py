from __future__ import annotations

import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-core-entry-ml-pre3a-compare-2026-06-26-v15"
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


def _patch_self_check_endpoints() -> None:
    try:
        import one_link_check
        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/blocked-entry-reason-audit-status", "category": "governance", "required": False},
            {"path": "/paper/blocked-entry-reason-selfcheck-overlay-status", "category": "governance", "required": False},
            {"path": "/paper/dynamic-universe-builder-status", "category": "governance", "required": False},
            {"path": "/paper/regime-flip-entry-guard-status", "category": "governance", "required": False},
            {"path": "/paper/core-entry-pipeline-status", "category": "governance", "required": False},
            {"path": "/paper/ml-pre3a-shadow-status", "category": "governance", "required": False},
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


MODULES = (
    ("runner_safety", "app_and_module"),
    ("journal_truth", "app_and_module"),
    ("live_volatility", "app_and_module"),
    ("self_check", "app_and_module"),
    ("breakout_participation_layer", "app_only"),
    ("fmp_limited_access_guard", "app_and_module"),
    ("fmp_cached_profile_label_guard", "app_and_module"),
    ("space_stock_basket", "app_and_module"),
    ("spacex_direct_overlay", "app_and_module"),
    ("blocked_entry_reason_audit", "app_and_module"),
    ("blocked_entry_reason_selfcheck_overlay", "app_and_module"),
    ("dynamic_universe_builder", "app_and_module"),
    ("regime_flip_entry_guard", "app_and_module"),
    ("core_entry_pipeline", "app_and_module"),
    ("ml_pre3a_shadow_validation", "app_and_module"),
    ("ml_vs_rules_shadow_log", "app_and_module"),
)


def _register_auxiliary_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    _patch_self_check_endpoints()
    for module_name, route_args in MODULES:
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
                _register_module(flask_app, m, "core_entry_pipeline", route_args="app_and_module")
                _register_module(flask_app, m, "ml_pre3a_shadow_validation", route_args="app_and_module")
                _register_module(flask_app, m, "ml_vs_rules_shadow_log", route_args="app_and_module")
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
