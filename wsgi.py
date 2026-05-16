"""WSGI entry point for the trading bot auxiliary layers."""
from __future__ import annotations

try:
    import state_guard
    if hasattr(state_guard, "preflight_recover"):
        state_guard.preflight_recover()
except Exception:
    pass

import app as core
from app import app

state_io_hardening = None


def _patch_json_modules(*mods):
    try:
        if state_io_hardening is not None and hasattr(state_io_hardening, "patch_json_modules"):
            state_io_hardening.patch_json_modules(*mods)
    except Exception:
        pass


def _call(mod, name, *args):
    try:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn(*args)
    except Exception:
        return None
    return None


try:
    import state_io_hardening as _sio
    state_io_hardening = _sio
    _call(_sio, "install", core)
    _call(_sio, "register_routes", app, core)
except Exception:
    state_io_hardening = None

for _name in ("runner_safety",):
    try:
        _m = __import__(_name)
        _call(_m, "install", core)
        _call(_m, "register_routes", app, core)
    except Exception:
        pass

try:
    import trade_journal
    _patch_json_modules(trade_journal)
    _call(trade_journal, "install", core)
    _call(trade_journal, "register_routes", app, core)
except Exception:
    trade_journal = None  # type: ignore

try:
    import journal_truth
    if trade_journal is not None:
        _patch_json_modules(journal_truth, trade_journal)
        _call(journal_truth, "patch_trade_journal", trade_journal)
    _call(journal_truth, "register_routes", app, core)
except Exception:
    pass

try:
    import state_journal_guard
    _patch_json_modules(state_journal_guard)
    _call(state_journal_guard, "register_routes", app, core)
    for _patch in ("state_journal_persistence_patch", "state_journal_apply_guardrail"):
        try:
            _pm = __import__(_patch)
            _call(_pm, "apply", state_journal_guard, core)
        except Exception:
            pass
except Exception:
    pass

try:
    import reporting_cleanup
    _call(reporting_cleanup, "apply", app, core)
except Exception:
    pass

try:
    import sitecustomize as ml_shadow
    _call(ml_shadow, "_register_routes", app)
except Exception:
    pass

try:
    import ml_phase2_shadow
    _patch_json_modules(ml_phase2_shadow)
    _call(ml_phase2_shadow, "apply", core)
    _call(ml_phase2_shadow, "register_routes", app, core)
except Exception:
    pass

try:
    import ml_phase25_readiness
    _patch_json_modules(ml_phase25_readiness)
    _call(ml_phase25_readiness, "apply", core)
    _call(ml_phase25_readiness, "register_routes", app, core)
except Exception:
    pass

try:
    import trade_quality_telemetry
    _patch_json_modules(trade_quality_telemetry)
    _call(trade_quality_telemetry, "apply", core)
    _call(trade_quality_telemetry, "register_routes", app, core)
except Exception:
    pass

try:
    import market_extension_guard
    _patch_json_modules(market_extension_guard)
    _call(market_extension_guard, "apply", core)
    _call(market_extension_guard, "register_routes", app, core)
except Exception:
    pass

try:
    import risk_reward_structure
    _patch_json_modules(risk_reward_structure)
    _call(risk_reward_structure, "apply", core)
    _call(risk_reward_structure, "register_routes", app, core)
except Exception:
    pass

try:
    import state_guard
    _call(state_guard, "register_routes", app)
except Exception:
    pass

for _name, _functions in (
    ("eod_hybrid", (("_register_routes", (app,)),)),
    ("risk_bootstrap", (("apply_runtime_overrides", (core,)), ("register_routes", (app,)))),
    ("fvg_runtime", (("apply_runtime_wiring", (core,)),)),
    ("ml_phase25_readiness", (("apply", (core,)), ("register_routes", (app, core)))),
    ("trade_quality_telemetry", (("apply", (core,)), ("register_routes", (app, core)))),
    ("live_volatility", (("apply", (core,)), ("register_routes", (app, core)))),
    ("classic_signal_mode", (("apply", (core,)), ("register_routes", (app, core)))),
    ("intraday_timing", (("apply", (core,)), ("register_routes", (app, core)))),
    ("position_quality_governor", (("apply", (core,)), ("register_routes", (app, core)))),
    ("benchmark_participation", (("apply", (core,)), ("register_routes", (app, core)))),
    ("risk_on_entry_diagnostic", (("apply", (core,)), ("register_routes", (app, core)))),
    ("risk_on_recommendation_cleanup", (("apply", (core,)), ("register_routes", (app, core)))),
    ("risk_improvements", (("_register_routes", (app,)),)),
):
    try:
        _m = __import__(_name)
        _patch_json_modules(_m)
        for _fn, _args in _functions:
            _call(_m, _fn, *_args)
    except Exception:
        pass

try:
    import self_check
    try:
        import one_link_check
        _call(one_link_check, "apply", self_check)
    except Exception:
        pass
    try:
        light = getattr(self_check, "LIGHT_ENDPOINTS", None)
        if isinstance(light, list):
            for _path, _category, _required in (
                ("/paper/ml2-status", "ml", False),
                ("/paper/ml-readiness-status", "ml", False),
                ("/paper/ml-phase25-status", "ml", False),
                ("/paper/trade-quality-status", "ml", False),
                ("/paper/mae-mfe-status", "ml", False),
                ("/paper/market-extension-status", "risk", False),
                ("/paper/fibonacci-status", "risk", False),
                ("/paper/risk-reward-status", "risk", False),
                ("/paper/opening-range-fvg-status", "risk", False),
            ):
                if not any(isinstance(row, dict) and row.get("path") == _path for row in light):
                    light.append({"path": _path, "category": _category, "required": _required})
    except Exception:
        pass
    try:
        import reporting_cleanup
        _call(reporting_cleanup, "apply", app, core)
    except Exception:
        pass
    _call(self_check, "register_routes", app, core)
except Exception:
    pass
