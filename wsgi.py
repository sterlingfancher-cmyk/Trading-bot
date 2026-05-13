"""WSGI entry point that directly registers all auxiliary endpoints.

This startup path runs the state recovery guard before importing app.py, installs
state I/O hardening, persistent trade journaling, execution-only journal truth
reporting, runtime risk controls, slow price-fetch timeout/cache fallbacks,
classic signal mode, intraday timing/pullback guards, position-quality controls,
and one-link self-check routes.
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
    import state_io_hardening
    if hasattr(state_io_hardening, "install"):
        state_io_hardening.install(core)
    if hasattr(state_io_hardening, "register_routes"):
        state_io_hardening.register_routes(app, core)
except Exception:
    state_io_hardening = None  # type: ignore

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
    if 'state_io_hardening' in globals() and state_io_hardening is not None and hasattr(state_io_hardening, "patch_json_modules"):
        state_io_hardening.patch_json_modules(trade_journal)
    if hasattr(trade_journal, "install"):
        trade_journal.install(core)
    if hasattr(trade_journal, "register_routes"):
        trade_journal.register_routes(app, core)
except Exception:
    pass

try:
    import journal_truth
    import trade_journal as _trade_journal_module
    if 'state_io_hardening' in globals() and state_io_hardening is not None and hasattr(state_io_hardening, "patch_json_modules"):
        state_io_hardening.patch_json_modules(journal_truth, _trade_journal_module)
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
    if 'state_io_hardening' in globals() and state_io_hardening is not None and hasattr(state_io_hardening, "patch_json_modules"):
        state_io_hardening.patch_json_modules(risk_bootstrap)
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
    import classic_signal_mode
    if hasattr(classic_signal_mode, "apply"):
        classic_signal_mode.apply(core)
    if hasattr(classic_signal_mode, "register_routes"):
        classic_signal_mode.register_routes(app, core)
except Exception:
    pass

try:
    import intraday_timing
    if hasattr(intraday_timing, "apply"):
        intraday_timing.apply(core)
    if hasattr(intraday_timing, "register_routes"):
        intraday_timing.register_routes(app, core)
except Exception:
    pass

try:
    import position_quality_governor
    if hasattr(position_quality_governor, "apply"):
        position_quality_governor.apply(core)
    if hasattr(position_quality_governor, "register_routes"):
        position_quality_governor.register_routes(app, core)
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
