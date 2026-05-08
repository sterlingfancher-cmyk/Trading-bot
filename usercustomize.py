"""Startup fallback for live-volatility runtime controls.

Python imports usercustomize after sitecustomize. This gives the bot a second,
independent registration path for /paper/live-volatility-status, which prevents
route-missing issues when Railway starts app.py differently than expected.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-live-volatility-2026-05-08"
_REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    return None


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _register_live_volatility(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return

    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def live_volatility_status_fallback():
        try:
            import live_volatility
            module = _mod() or m
            if hasattr(live_volatility, "apply"):
                live_volatility.apply(module)
            if hasattr(live_volatility, "_live_status"):
                return jsonify(live_volatility._live_status(module))
            return jsonify({
                "status": "error",
                "version": VERSION,
                "generated_local": _now_text(),
                "reason": "live_volatility module imported but has no _live_status function",
            }), 500
        except Exception as exc:
            return jsonify({
                "status": "error",
                "version": VERSION,
                "generated_local": _now_text(),
                "reason": "live_volatility import/apply failed",
                "error": str(exc),
                "expected_file": "live_volatility.py",
            }), 500

    if "/paper/live-volatility-status" not in existing:
        flask_app.add_url_rule(
            "/paper/live-volatility-status",
            "live_volatility_status_usercustomize",
            live_volatility_status_fallback,
        )

    try:
        import live_volatility
        module = _mod() or m
        if hasattr(live_volatility, "apply"):
            live_volatility.apply(module)
        if hasattr(live_volatility, "register_routes"):
            live_volatility.register_routes(flask_app, module)
    except Exception:
        pass

    _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(900):
        try:
            m = _mod()
            flask_app = getattr(m, "app", None) if m is not None else None
            if flask_app is not None:
                _register_live_volatility(flask_app, m)
        except Exception:
            pass
        time.sleep(0.1)


try:
    from flask import Flask

    if not getattr(Flask.__init__, "_live_volatility_usercustomize_patched", False):
        _original_init = Flask.__init__

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                _register_live_volatility(self, _mod())
            except Exception:
                pass

        _patched_init._live_volatility_usercustomize_patched = True
        Flask.__init__ = _patched_init
except Exception:
    pass

threading.Thread(target=_watchdog, daemon=True).start()
