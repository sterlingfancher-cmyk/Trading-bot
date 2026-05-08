from __future__ import annotations

import sys

try:
    from flask import Flask
    import risk_bootstrap

    if not getattr(Flask.run, "_risk_routes_patched", False):
        _original_run = Flask.run

        def _patched_run(self, *args, **kwargs):
            try:
                module = None
                for mod in list(sys.modules.values()):
                    if getattr(mod, "app", None) is self:
                        module = mod
                        break
                risk_bootstrap.apply_runtime_overrides(module)
                risk_bootstrap.register_routes(self)
            except Exception:
                pass
            return _original_run(self, *args, **kwargs)

        _patched_run._risk_routes_patched = True
        Flask.run = _patched_run
except Exception:
    pass
