"""Compatibility bootstrap for ML shadow routes.

This module is intentionally defensive. It works with both the older
sitecustomize.install() approach and the newer direct registrar. Any failure
must leave the trading bot untouched.
"""
from __future__ import annotations

import sys

try:
    from flask import Flask

    if not getattr(Flask.run, "_ml_shadow_bootstrap_patched", False):
        _original_run = Flask.run

        def _patched_run(self, *args, **kwargs):
            try:
                installed = False
                for mod in list(sys.modules.values()):
                    if getattr(mod, "app", None) is self:
                        try:
                            import sitecustomize as ml_shadow
                            if hasattr(ml_shadow, "install"):
                                ml_shadow.install(mod)
                                installed = True
                            elif hasattr(ml_shadow, "_register_routes"):
                                ml_shadow._register_routes(self)
                                if hasattr(ml_shadow, "_patch_save_state"):
                                    ml_shadow._patch_save_state(mod)
                                installed = True
                        except Exception:
                            pass
                        if not installed:
                            try:
                                import ml_direct
                                ml_direct.register(self, getattr(mod, "__dict__", {}))
                                installed = True
                            except Exception:
                                pass
                        break
            except Exception:
                pass
            return _original_run(self, *args, **kwargs)

        _patched_run._ml_shadow_bootstrap_patched = True
        Flask.run = _patched_run
except Exception:
    pass
