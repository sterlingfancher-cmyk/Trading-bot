"""WSGI entry point that directly registers all auxiliary endpoints.

This startup path now runs the state recovery guard before importing app.py, so
Railway deploy/startup cycles do not continue with a suspiciously small
/data/state.json when a larger valid backup exists.
"""
from __future__ import annotations

try:
    import state_guard
    if hasattr(state_guard, "preflight_recover"):
        state_guard.preflight_recover()
except Exception:
    pass

import app as core
from app import app

try:
    import sitecustomize as ml_shadow
    if hasattr(ml_shadow, "_register_routes"):
        ml_shadow._register_routes(app)
except Exception:
    pass

try:
    import state_guard
    if hasattr(state_guard, "register_routes"):
        state_guard.register_routes(app)
except Exception:
    pass

try:
    import eod_hybrid
    if hasattr(eod_hybrid, "_register_routes"):
        eod_hybrid._register_routes(app)
except Exception:
    pass

try:
    import risk_bootstrap
    if hasattr(risk_bootstrap, "apply_runtime_overrides"):
        risk_bootstrap.apply_runtime_overrides(core)
    if hasattr(risk_bootstrap, "register_routes"):
        risk_bootstrap.register_routes(app)
except Exception:
    pass

try:
    import live_volatility
    if hasattr(live_volatility, "apply"):
        live_volatility.apply(core)
    if hasattr(live_volatility, "register_routes"):
        live_volatility.register_routes(app, core)
except Exception:
    pass

try:
    import risk_improvements
    if hasattr(risk_improvements, "_register_routes"):
        risk_improvements._register_routes(app)
except Exception:
    pass
