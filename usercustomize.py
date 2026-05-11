"""Startup fallback for auxiliary monitoring routes.

Python imports usercustomize after sitecustomize. This gives the bot a second,
independent registration path for routes that have previously been sensitive to
Railway startup differences.

Fallback routes covered:
- /paper/live-volatility-status
- /paper/self-check
- /paper/smoke-test
- /paper/test-links
- /paper/runner-safety-status
- /paper/runner-freshness
- /paper/price-health
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-runner-safety-fallback-2026-05-11"
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


def _existing_rules(flask_app: Any) -> set[str]:
    try:
        return {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        return set()


def _register_runner_safety(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    existing = _existing_rules(flask_app)
    module = _mod() or m

    try:
        import runner_safety
        if hasattr(runner_safety, "install"):
            runner_safety.install(module)
        if hasattr(runner_safety, "register_routes"):
            runner_safety.register_routes(flask_app, module)
            existing = _existing_rules(flask_app)
    except Exception:
        pass

    if "/paper/runner-safety-status" not in existing:
        def runner_safety_status_fallback():
            try:
                import runner_safety
                module2 = _mod() or module
                if hasattr(runner_safety, "install"):
                    runner_safety.install(module2)
                return jsonify(runner_safety.status(module2))
            except Exception as exc:
                return jsonify({"status": "error", "type": "runner_safety_status", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/runner-safety-status", "runner_safety_status_usercustomize", runner_safety_status_fallback)

    existing = _existing_rules(flask_app)
    if "/paper/runner-freshness" not in existing:
        def runner_freshness_fallback():
            try:
                import runner_safety
                module2 = _mod() or module
                return jsonify(runner_safety.freshness(module2))
            except Exception as exc:
                return jsonify({"status": "error", "type": "runner_freshness", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/runner-freshness", "runner_freshness_usercustomize", runner_freshness_fallback)

    existing = _existing_rules(flask_app)
    if "/paper/price-health" not in existing:
        def price_health_fallback():
            try:
                import runner_safety
                module2 = _mod() or module
                return jsonify(runner_safety.price_health(module2))
            except Exception as exc:
                return jsonify({"status": "error", "type": "price_health", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/price-health", "price_health_usercustomize", price_health_fallback)


def _register_live_volatility(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return

    from flask import jsonify
    existing = _existing_rules(flask_app)

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


def _register_self_check(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return

    from flask import jsonify
    existing = _existing_rules(flask_app)

    try:
        import self_check
        if hasattr(self_check, "register_routes"):
            self_check.register_routes(flask_app, m)
            existing = _existing_rules(flask_app)
    except Exception:
        pass

    if "/paper/self-check" not in existing:
        def self_check_fallback():
            try:
                import self_check
                if hasattr(self_check, "run_self_check"):
                    return jsonify(self_check.run_self_check(flask_app))
                return jsonify({
                    "status": "error",
                    "type": "self_check",
                    "version": VERSION,
                    "generated_local": _now_text(),
                    "reason": "self_check module imported but has no run_self_check function",
                }), 500
            except Exception as exc:
                return jsonify({
                    "status": "error",
                    "type": "self_check",
                    "version": VERSION,
                    "generated_local": _now_text(),
                    "reason": "self_check import/run failed",
                    "error": str(exc),
                    "expected_file": "self_check.py",
                }), 500
        flask_app.add_url_rule("/paper/self-check", "paper_self_check_usercustomize", self_check_fallback)

    existing = _existing_rules(flask_app)
    if "/paper/smoke-test" not in existing:
        def smoke_test_fallback():
            try:
                import self_check
                return jsonify(self_check.run_self_check(flask_app))
            except Exception as exc:
                return jsonify({"status": "error", "type": "smoke_test", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/smoke-test", "paper_smoke_test_usercustomize", smoke_test_fallback)

    existing = _existing_rules(flask_app)
    if "/paper/full-self-check" not in existing:
        def full_self_check_fallback():
            try:
                import self_check
                return jsonify(self_check.run_self_check(flask_app, mode="full"))
            except Exception as exc:
                return jsonify({"status": "error", "type": "full_self_check", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/full-self-check", "paper_full_self_check_usercustomize", full_self_check_fallback)

    existing = _existing_rules(flask_app)
    if "/paper/test-links" not in existing:
        def test_links_fallback():
            try:
                import self_check
                return jsonify(self_check.test_links_payload())
            except Exception as exc:
                return jsonify({"status": "error", "type": "test_links", "version": VERSION, "error": str(exc)}), 500
        flask_app.add_url_rule("/paper/test-links", "paper_test_links_usercustomize", test_links_fallback)


def _register_auxiliary_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    _register_runner_safety(flask_app, m)
    _register_live_volatility(flask_app, m)
    _register_self_check(flask_app, m)
    _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(1200):
        try:
            m = _mod()
            flask_app = getattr(m, "app", None) if m is not None else None
            if flask_app is not None:
                _register_auxiliary_routes(flask_app, m)
        except Exception:
            pass
        time.sleep(0.1)


try:
    from flask import Flask

    if not getattr(Flask.__init__, "_auxiliary_usercustomize_patched", False):
        _original_init = Flask.__init__

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                _register_auxiliary_routes(self, _mod())
            except Exception:
                pass

        _patched_init._auxiliary_usercustomize_patched = True
        Flask.__init__ = _patched_init
except Exception:
    pass

threading.Thread(target=_watchdog, daemon=True).start()
