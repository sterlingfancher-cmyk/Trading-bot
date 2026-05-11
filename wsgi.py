"""WSGI entry point that directly registers all auxiliary endpoints.

This startup path runs the state recovery guard before importing app.py, installs
persistent trade journaling, applies execution-only journal truth reporting,
applies runtime risk controls, patches slow price fetches with timeout/cache
fallbacks, and registers one-link self-check routes.
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
    import runner_safety
    if hasattr(runner_safety, "install"):
        runner_safety.install(core)
    if hasattr(runner_safety, "register_routes"):
        runner_safety.register_routes(app, core)
except Exception:
    pass

try:
    import trade_journal
    if hasattr(trade_journal, "install"):
        trade_journal.install(core)
    if hasattr(trade_journal, "register_routes"):
        trade_journal.register_routes(app, core)
except Exception:
    pass

try:
    import journal_truth
    import trade_journal as _trade_journal_module
    if hasattr(journal_truth, "patch_trade_journal"):
        journal_truth.patch_trade_journal(_trade_journal_module)
    if hasattr(journal_truth, "register_routes"):
        journal_truth.register_routes(app, core)
except Exception:
    pass

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

try:
    import self_check
    try:
        import one_link_check
        if hasattr(one_link_check, "apply"):
            one_link_check.apply(self_check)
    except Exception:
        pass
    if hasattr(self_check, "register_routes"):
        self_check.register_routes(app, core)
except Exception:
    pass
