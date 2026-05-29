"""Startup fallback for monitoring and advisory guard routes."""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from typing import Any

VERSION = "usercustomize-fmp-cached-profile-labels-2026-05-29-v2"
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


def _patch_self_check_endpoints() -> None:
    try:
        import one_link_check

        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/breakout-participation-status", "category": "governance", "required": False, "after": "/paper/market-participation-accelerator-status"},
            {"path": "/paper/breakout-leaders", "category": "governance", "required": False, "after": "/paper/breakout-participation-status"},
            {"path": "/paper/fmp-limited-access-guard-status", "category": "governance", "required": False, "after": "/paper/analyst-valuation-risk-status"},
            {"path": "/paper/fmp-cached-profile-label-guard-status", "category": "governance", "required": False, "after": "/paper/fmp-limited-access-guard-status"},
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _register_breakout_participation(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    try:
        import breakout_participation_layer

        module = _mod() or m
        if hasattr(breakout_participation_layer, "apply_runtime_overrides"):
            breakout_participation_layer.apply_runtime_overrides(module)
        if hasattr(breakout_participation_layer, "register_routes"):
            breakout_participation_layer.register_routes(flask_app)
    except Exception:
        pass


def _register_runner_safety(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    try:
        import runner_safety
        module = _mod() or m
        if hasattr(runner_safety, "install"):
            runner_safety.install(module)
        if hasattr(runner_safety, "register_routes"):
            runner_safety.register_routes(flask_app, module)
            return
    except Exception:
        pass
    try:
        from flask import jsonify
        existing = _existing_rules(flask_app)
        module = _mod() or m

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
                    return jsonify(runner_safety.freshness(_mod() or module))
                except Exception as exc:
                    return jsonify({"status": "error", "type": "runner_freshness", "version": VERSION, "error": str(exc)}), 500
            flask_app.add_url_rule("/paper/runner-freshness", "runner_freshness_usercustomize", runner_freshness_fallback)

        existing = _existing_rules(flask_app)
        if "/paper/price-health" not in existing:
            def price_health_fallback():
                try:
                    import runner_safety
                    return jsonify(runner_safety.price_health(_mod() or module))
                except Exception as exc:
                    return jsonify({"status": "error", "type": "price_health", "version": VERSION, "error": str(exc)}), 500
            flask_app.add_url_rule("/paper/price-health", "price_health_usercustomize", price_health_fallback)
    except Exception:
        pass


def _register_journal_truth(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    try:
        import journal_truth
        try:
            import trade_journal as trade_journal_module
            if hasattr(journal_truth, "patch_trade_journal"):
                journal_truth.patch_trade_journal(trade_journal_module)
        except Exception:
            pass
        if hasattr(journal_truth, "register_routes"):
            journal_truth.register_routes(flask_app, m)
            return
    except Exception:
        pass
    try:
        from flask import jsonify
        if "/paper/journal-truth-status" not in _existing_rules(flask_app):
            def journal_truth_status_fallback():
                try:
                    import journal_truth
                    return jsonify(journal_truth.status_payload())
                except Exception as exc:
                    return jsonify({"status": "error", "type": "journal_truth_status", "version": VERSION, "error": str(exc)}), 500
            flask_app.add_url_rule("/paper/journal-truth-status", "journal_truth_status_usercustomize", journal_truth_status_fallback)
    except Exception:
        pass


def _register_live_volatility(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
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
    try:
        import self_check
        if hasattr(self_check, "register_routes"):
            self_check.register_routes(flask_app, m)
            return
    except Exception:
        pass
    try:
        from flask import jsonify
        existing = _existing_rules(flask_app)
        if "/paper/self-check" not in existing:
            def self_check_fallback():
                try:
                    import self_check
                    if hasattr(self_check, "run_self_check"):
                        return jsonify(self_check.run_self_check(flask_app))
                    return jsonify({"status": "error", "type": "self_check", "version": VERSION, "reason": "missing run_self_check"}), 500
                except Exception as exc:
                    return jsonify({"status": "error", "type": "self_check", "version": VERSION, "error": str(exc)}), 500
            flask_app.add_url_rule("/paper/self-check", "paper_self_check_usercustomize", self_check_fallback)
        existing = _existing_rules(flask_app)
        if "/paper/test-links" not in existing:
            def test_links_fallback():
                try:
                    import self_check
                    return jsonify(self_check.test_links_payload())
                except Exception as exc:
                    return jsonify({"status": "error", "type": "test_links", "version": VERSION, "error": str(exc)}), 500
            flask_app.add_url_rule("/paper/test-links", "paper_test_links_usercustomize", test_links_fallback)
    except Exception:
        pass


def _register_fmp_limited_access_guard(flask_app: Any, m: Any | None = None) -> None:
    try:
        import fmp_limited_access_guard

        module = _mod() or m
        if hasattr(fmp_limited_access_guard, "apply_runtime_overrides"):
            fmp_limited_access_guard.apply_runtime_overrides(module)
        if flask_app is not None and hasattr(fmp_limited_access_guard, "register_routes"):
            fmp_limited_access_guard.register_routes(flask_app, module)
    except Exception:
        pass


def _register_fmp_cached_profile_label_guard(flask_app: Any, m: Any | None = None) -> None:
    try:
        import fmp_cached_profile_label_guard

        if hasattr(fmp_cached_profile_label_guard, "apply_runtime_overrides"):
            fmp_cached_profile_label_guard.apply_runtime_overrides(_mod() or m)
        if flask_app is None or "/paper/fmp-cached-profile-label-guard-status" in _existing_rules(flask_app):
            return
        from flask import jsonify

        def fmp_cached_profile_label_guard_status():
            try:
                return jsonify(fmp_cached_profile_label_guard.status_payload())
            except Exception as exc:
                return jsonify({"status": "error", "type": "fmp_cached_profile_label_guard_status", "version": VERSION, "error": str(exc)}), 500

        flask_app.add_url_rule(
            "/paper/fmp-cached-profile-label-guard-status",
            "fmp_cached_profile_label_guard_status",
            fmp_cached_profile_label_guard_status,
        )
    except Exception:
        pass


def _register_auxiliary_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    _patch_self_check_endpoints()
    _register_runner_safety(flask_app, m)
    _register_journal_truth(flask_app, m)
    _register_live_volatility(flask_app, m)
    _register_self_check(flask_app, m)
    _register_breakout_participation(flask_app, m)
    _register_fmp_limited_access_guard(flask_app, m)
    _register_fmp_cached_profile_label_guard(flask_app, m)
    _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(1200):
        try:
            _patch_self_check_endpoints()
            m = _mod()
            flask_app = getattr(m, "app", None) if m is not None else None
            if flask_app is not None:
                _register_auxiliary_routes(flask_app, m)
                _register_breakout_participation(flask_app, m)
                _register_fmp_limited_access_guard(flask_app, m)
                _register_fmp_cached_profile_label_guard(flask_app, m)
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

try:
    threading.Thread(target=_watchdog, daemon=True).start()
except Exception:
    pass
