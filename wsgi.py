"""WSGI entry point that directly registers all auxiliary endpoints.

Railway previously executed app.py through an inline python -c command. That
kept the core bot alive, but auxiliary routes could be missed depending on
startup timing. This WSGI path imports app.py as a normal module, then registers
ML, EOD hybrid, risk-improvement, and live-volatility routes deterministically
before Gunicorn serves traffic.
"""
from __future__ import annotations

import app as core
from app import app

try:
    import sitecustomize as ml_shadow
    if hasattr(ml_shadow, "_register_routes"):
        ml_shadow._register_routes(app)
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
