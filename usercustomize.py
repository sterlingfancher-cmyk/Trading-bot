from __future__ import annotations

import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-entry-pipeline-composition-2026-07-21-v34-shadow-composite-score"
_REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _patch_self_check_endpoints() -> None:
    try:
        import one_link_check
        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/symbol-hygiene-guard-status", "category": "governance", "required": False},
            {"path": "/paper/blocked-entry-reason-audit-status", "category": "governance", "required": False},
            {"path": "/paper/blocked-entry-reason-selfcheck-overlay-status", "category": "governance", "required": False},
            {"path": "/paper/dynamic-universe-builder-status", "category": "governance", "required": False},
            {"path": "/paper/scanner-v2-shadow-universe-status", "category": "governance", "required": False},
            {"path": "/paper/missed-opportunity-post-close-audit-status", "category": "governance", "required": False},
            {"path": "/paper/scanner-v2-shadow-quality-trace-status", "category": "governance", "required": False},
            {"path": "/paper/scanner-v2-shadow-composite-score-status", "category": "governance", "required": False},
            {"path": "/paper/regime-flip-entry-guard-status", "category": "governance", "required": False},
            {"path": "/paper/core-entry-pipeline-status", "category": "governance", "required": False},
            {"path": "/paper/extended-leader-starter-valve-status", "category": "governance", "required": False},
            {"path": "/paper/risk-on-starter-participation-status", "category": "governance", "required": False},
            {"path": "/paper/entry-pipeline-composition-status", "category": "governance", "required": False},
            {"path": "/paper/starter-valve-reason-sanitizer-status", "category": "governance", "required": False},
            {"path": "/paper/entry-pipeline-xray-status", "category": "governance", "required": False},
            {"path": "/paper/entry-pipeline-ownership-status", "category": "governance", "required": False},
            {"path": "/paper/state-transaction-status", "category": "state", "required": False},
            {"path": "/paper/runtime-reliability-status", "category": "governance", "required": False},
            {"path": "/paper/daily-self-check-compactor-status", "category": "governance", "required": False},
            {"path": "/paper/controlled-redeployment-starter-sleeve-status", "category": "governance", "required": False},
            {"path": "/paper/quality-blocker-diagnostics-status", "category": "governance", "required": False},
            {"path": "/paper/ml-pre3a-shadow-status", "category": "governance", "required": False},
            {"path": "/paper/ml3a-early-paper-status", "category": "governance", "required": False},
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _register_module(flask_app: Any, module_hint: Any | None, module_name: str, route_args: str = "app_and_module") -> None:
    try:
        module = __import__(module_name)
        core = _mod() or module_hint
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
    ("state_transaction_manager", "app_and_module"),
    ("breakout_participation_layer", "app_only"),
    ("fmp_limited_access_guard", "app_and_module"),
    ("fmp_cached_profile_label_guard", "app_and_module"),
    ("space_stock_basket", "app_and_module"),
    ("spacex_direct_overlay", "app_and_module"),
    ("symbol_hygiene_guard", "app_and_module"),
    ("blocked_entry_reason_audit", "app_and_module"),
    ("blocked_entry_reason_selfcheck_overlay", "app_and_module"),
    ("dynamic_universe_builder", "app_and_module"),
    ("scanner_v2_shadow_universe", "app_and_module"),
    ("missed_opportunity_post_close_audit", "app_and_module"),
    ("scanner_v2_shadow_quality_trace", "app_and_module"),
    ("scanner_v2_shadow_composite_score", "app_and_module"),
    ("regime_flip_entry_guard", "app_and_module"),
    ("core_entry_pipeline", "app_and_module"),
    ("extended_leader_starter_valve", "app_and_module"),
    ("risk_on_starter_participation_valve", "app_and_module"),
    ("entry_pipeline_composition_guard", "app_and_module"),
    ("starter_valve_reason_sanitizer", "app_and_module"),
    ("entry_pipeline_xray", "app_and_module"),
    ("entry_pipeline_ownership_guard", "app_and_module"),
    ("controlled_redeployment_starter_sleeve", "app_and_module"),
    ("quality_blocker_diagnostics", "app_and_module"),
    ("ml_pre3a_shadow_validation", "app_and_module"),
    ("ml_phase3a_early_paper_gate", "app_and_module"),
    ("ml_vs_rules_shadow_log", "app_and_module"),
    ("daily_self_check_compactor", "app_and_module"),
    ("runtime_reliability_overlay", "app_and_module"),
)


def _register_auxiliary_routes(flask_app: Any, module_hint: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    _patch_self_check_endpoints()
    for module_name, route_args in MODULES:
        _register_module(flask_app, module_hint, module_name, route_args=route_args)
    _REGISTERED_APP_IDS.add(id(flask_app))


def _repair_entry_stack(flask_app: Any, core: Any) -> None:
    _register_module(flask_app, core, "extended_leader_starter_valve", route_args="app_and_module")
    _register_module(flask_app, core, "entry_pipeline_composition_guard", route_args="app_and_module")
    _register_module(flask_app, core, "starter_valve_reason_sanitizer", route_args="app_and_module")
    _register_module(flask_app, core, "entry_pipeline_xray", route_args="app_and_module")
    _register_module(flask_app, core, "entry_pipeline_ownership_guard", route_args="app_and_module")


def _watchdog() -> None:
    # Fast startup convergence, then low-frequency drift checks. Healthy ownership
    # checks are read/no-op and do not write state.
    for iteration in range(1200):
        try:
            _patch_self_check_endpoints()
            core = _mod()
            flask_app = getattr(core, "app", None) if core is not None else None
            if flask_app is not None:
                _register_auxiliary_routes(flask_app, core)
                _register_module(flask_app, core, "state_transaction_manager", route_args="app_and_module")
                _register_module(flask_app, core, "symbol_hygiene_guard", route_args="app_and_module")
                _register_module(flask_app, core, "scanner_v2_shadow_universe", route_args="app_and_module")
                _register_module(flask_app, core, "missed_opportunity_post_close_audit", route_args="app_and_module")
                _register_module(flask_app, core, "scanner_v2_shadow_quality_trace", route_args="app_and_module")
                _register_module(flask_app, core, "scanner_v2_shadow_composite_score", route_args="app_and_module")
                _repair_entry_stack(flask_app, core)
                _register_module(flask_app, core, "controlled_redeployment_starter_sleeve", route_args="app_and_module")
                _register_module(flask_app, core, "quality_blocker_diagnostics", route_args="app_and_module")
                _register_module(flask_app, core, "ml_pre3a_shadow_validation", route_args="app_and_module")
                _register_module(flask_app, core, "ml_phase3a_early_paper_gate", route_args="app_and_module")
                _register_module(flask_app, core, "ml_vs_rules_shadow_log", route_args="app_and_module")
                _register_module(flask_app, core, "entry_pipeline_ownership_guard", route_args="app_and_module")
                _register_module(flask_app, core, "daily_self_check_compactor", route_args="app_and_module")
                _register_module(flask_app, core, "runtime_reliability_overlay", route_args="app_and_module")
        except Exception:
            pass
        time.sleep(0.5 if iteration < 60 else 30.0)


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
