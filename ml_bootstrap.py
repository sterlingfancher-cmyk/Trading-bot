"""Compatibility bootstrap for auxiliary trading-bot routes.

This module is intentionally defensive. It works with both the older
sitecustomize.install() approach and the newer direct registrars. Any failure
must leave the trading bot untouched.
"""
from __future__ import annotations

import sys

try:
    from flask import Flask

    if not getattr(Flask.run, "_auxiliary_bootstrap_patched", False):
        _original_run = Flask.run

        def _patched_run(self, *args, **kwargs):
            try:
                for mod in list(sys.modules.values()):
                    if getattr(mod, "app", None) is self:
                        try:
                            import sitecustomize as ml_shadow
                            if hasattr(ml_shadow, "install"):
                                ml_shadow.install(mod)
                            elif hasattr(ml_shadow, "_register_routes"):
                                ml_shadow._register_routes(self)
                                if hasattr(ml_shadow, "_patch_save_state"):
                                    ml_shadow._patch_save_state(mod)
                        except Exception:
                            pass
                        try:
                            import eod_hybrid
                            if hasattr(eod_hybrid, "_register_routes"):
                                eod_hybrid._register_routes(self)
                        except Exception:
                            pass
                        try:
                            import risk_improvements
                            if hasattr(risk_improvements, "_register_routes"):
                                risk_improvements._register_routes(self)
                        except Exception:
                            pass
                        try:
                            import ml_direct
                            ml_direct.register(self, getattr(mod, "__dict__", {}))
                        except Exception:
                            pass
                        break
            except Exception:
                pass
            return _original_run(self, *args, **kwargs)

        _patched_run._auxiliary_bootstrap_patched = True
        _patched_run._ml_shadow_bootstrap_patched = True
        Flask.run = _patched_run
except Exception:
    pass
