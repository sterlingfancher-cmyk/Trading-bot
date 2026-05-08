"""Bootstrap ML shadow routes before Flask starts.

Railway currently starts the app as a script through Procfile. The normal
sitecustomize watchdog can miss Flask route registration because Flask may
begin serving before the watchdog attaches routes. This bootstrap patches
Flask.run so the ML routes are installed synchronously right before the server
starts handling requests.
"""
from __future__ import annotations

import sys

try:
    from flask import Flask
    import sitecustomize as ml_shadow

    if not getattr(Flask.run, "_ml_shadow_bootstrap_patched", False):
        _original_run = Flask.run

        def _patched_run(self, *args, **kwargs):
            try:
                for mod in list(sys.modules.values()):
                    if getattr(mod, "app", None) is self:
                        ml_shadow.install(mod)
                        break
            except Exception:
                # Never block the trading bot from starting because of ML shadow mode.
                pass
            return _original_run(self, *args, **kwargs)

        _patched_run._ml_shadow_bootstrap_patched = True
        Flask.run = _patched_run
except Exception:
    # This file is safety-only. Any bootstrap failure should leave app.py behavior unchanged.
    pass
