"""Unified startup bootstrap for trading-bot runtime route patches.

Imported automatically before app.py loads. Keeps Railway startup deterministic by
loading route/scanner/risk patches repeatedly while the Flask app initializes.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import sys
import urllib.parse
from typing import Any

VERSION = "unified-startup-loader-2026-05-29-fmp-stable-endpoints"
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


def _patch_one_link_check() -> None:
    """Keep the mobile-safe self-check light, but expose diagnostics as linked optional routes."""
    try:
        import one_link_check

        endpoints = getattr(one_link_check, "ONE_TEST_ENDPOINTS", None)
        if not isinstance(endpoints, list):
            return
        wanted = [
            {"path": "/paper/breakout-participation-status", "category": "governance", "required": False, "after": "/paper/market-participation-accelerator-status"},
            {"path": "/paper/breakout-leaders", "category": "governance", "required": False, "after": "/paper/breakout-participation-status"},
            {"path": "/paper/paper-exposure-status", "category": "governance", "required": False, "after": "/paper/breakout-leaders"},
            {"path": "/paper/paper-participation-status", "category": "governance", "required": False, "after": "/paper/paper-exposure-status"},
            {"path": "/paper/risk-on-concentration-policy", "category": "governance", "required": False, "after": "/paper/paper-participation-status"},
            {"path": "/paper/breakout-rotation-status", "category": "governance", "required": False, "after": "/paper/risk-on-concentration-policy"},
            {"path": "/paper/patch-stack-guard-status", "category": "governance", "required": False, "after": "/paper/breakout-rotation-status"},
            {"path": "/paper/research-advisory-status", "category": "governance", "required": False, "after": "/paper/news-risk-status"},
            {"path": "/paper/scanner-research-ranking", "category": "governance", "required": False, "after": "/paper/research-advisory-status"},
            {"path": "/paper/fundamental-score-status", "category": "governance", "required": False, "after": "/paper/scanner-research-ranking"},
            {"path": "/paper/fundamental-valuation-risk-status", "category": "governance", "required": False, "after": "/paper/fundamental-score-status"},
            {"path": "/paper/analyst-valuation-risk-status", "category": "governance", "required": False, "after": "/paper/fundamental-valuation-risk-status"},
        ]
        existing = {endpoint.get("path") for endpoint in endpoints if isinstance(endpoint, dict)}
        for endpoint in wanted:
            if endpoint["path"] not in existing:
                endpoints.append(endpoint)
                existing.add(endpoint["path"])
    except Exception:
        pass


def _import_usercustomize() -> None:
    try:
        import usercustomize
        if hasattr(usercustomize, "_patch_self_check_endpoints"):
            usercustomize._patch_self_check_endpoints()
    except Exception:
        pass


def _register_usercustomize_routes(flask_app: Any, m: Any | None) -> None:
    try:
        import usercustomize
        if hasattr(usercustomize, "_register_auxiliary_routes"):
            usercustomize._register_auxiliary_routes(flask_app, m)
        if hasattr(usercustomize, "_register_breakout_participation"):
            usercustomize._register_breakout_participation(flask_app, m)
    except Exception:
        pass


def _register_module(flask_app: Any, m: Any | None, module_name: str, apply_names: tuple[str, ...] = ("apply_runtime_overrides",), route_args: str = "app_only") -> None:
    try:
        module = __import__(module_name)
        for name in apply_names:
            fn = getattr(module, name, None)
            if callable(fn):
                try:
                    fn(m)
                except TypeError:
                    fn()
                break
        if flask_app is not None and hasattr(module, "register_routes"):
            try:
                if route_args == "app_and_module":
                    module.register_routes(flask_app, m)
                else:
                    module.register_routes(flask_app)
            except TypeError:
                module.register_routes(flask_app, m)
    except Exception:
        pass


def _register_patch_stack_guard(flask_app: Any, m: Any | None) -> None:
    try:
        import runtime_patch_stack_guard
        if hasattr(runtime_patch_stack_guard, "apply_runtime_overrides"):
            runtime_patch_stack_guard.apply_runtime_overrides(m)
        if flask_app is not None and hasattr(runtime_patch_stack_guard, "register_routes"):
            runtime_patch_stack_guard.register_routes(flask_app, m)
    except Exception:
        pass


def _register_risk_bootstrap(flask_app: Any, m: Any | None) -> None:
    try:
        import risk_bootstrap
        if hasattr(risk_bootstrap, "apply_runtime_overrides"):
            risk_bootstrap.apply_runtime_overrides(m)
        if flask_app is not None and hasattr(risk_bootstrap, "register_routes"):
            risk_bootstrap.register_routes(flask_app)
    except Exception:
        pass


def _register_eod_hybrid(flask_app: Any) -> None:
    try:
        import eod_hybrid
        if flask_app is not None and hasattr(eod_hybrid, "_register_routes"):
            eod_hybrid._register_routes(flask_app)
    except Exception:
        pass


def _register_research_advisory(flask_app: Any, m: Any | None) -> None:
    try:
        import research_advisory_engine
        if hasattr(research_advisory_engine, "apply"):
            research_advisory_engine.apply(m)
        if flask_app is not None and hasattr(research_advisory_engine, "register_routes"):
            research_advisory_engine.register_routes(flask_app, m)
    except Exception:
        pass


def _register_fundamental_valuation_risk(flask_app: Any, m: Any | None) -> None:
    try:
        import fundamental_valuation_risk_layer
        if hasattr(fundamental_valuation_risk_layer, "apply"):
            fundamental_valuation_risk_layer.apply(m)
        if flask_app is not None and hasattr(fundamental_valuation_risk_layer, "register_routes"):
            fundamental_valuation_risk_layer.register_routes(flask_app, m)
    except Exception:
        pass


def _stable_fmp_url(path: str, symbol: str, key: str) -> str:
    """Build current FMP /stable URLs without exposing the key in diagnostics."""
    path = str(path or "").strip().strip("/")
    path_map = {
        "profile": "profile",
        "quote": "quote",
        "ratios-ttm": "ratios-ttm",
        "key-metrics-ttm": "key-metrics-ttm",
        "rating": "ratings-snapshot",
        "ratings": "ratings-snapshot",
        "ratings-snapshot": "ratings-snapshot",
        "grades": "grades",
        "financial-scores": "financial-scores",
        "price-target-consensus": "price-target-consensus",
        "price-target-summary": "price-target-summary",
        "discounted-cash-flow": "discounted-cash-flow",
    }
    stable_path = path_map.get(path, path)
    query = urllib.parse.urlencode({"symbol": str(symbol).upper().strip(), "apikey": str(key).strip()})
    return f"https://financialmodelingprep.com/stable/{urllib.parse.quote(stable_path)}?{query}"


def _first_payload(module: Any, payload: Any) -> dict[str, Any]:
    for fn_name in ("_first", "_first_row"):
        fn = getattr(module, fn_name, None)
        if callable(fn):
            try:
                out = fn(payload)
                return out if isinstance(out, dict) else {}
            except Exception:
                pass
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}


def _call_module_fetch_json(module: Any, url: str, timeout: float | None = None) -> Any:
    fn = getattr(module, "_fetch_json", None)
    if not callable(fn):
        raise RuntimeError("module_fetch_json_missing")
    try:
        if timeout is None:
            return fn(url)
        return fn(url, timeout)
    except TypeError:
        return fn(url)


def _fetch_stable_first(module: Any, path: str, symbol: str, key: str, timeout: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    endpoint = f"stable/{path}"
    try:
        payload = _call_module_fetch_json(module, _stable_fmp_url(path, symbol, key), timeout=timeout)
        row = _first_payload(module, payload)
        return row, {"endpoint": endpoint, "ok": bool(row)}
    except Exception as exc:
        return {}, {"endpoint": endpoint, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:140]}"}


def _fetch_stable_first_any(module: Any, paths: tuple[str, ...], symbol: str, key: str, timeout: float | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    statuses: list[dict[str, Any]] = []
    for path in paths:
        row, status = _fetch_stable_first(module, path, symbol, key, timeout=timeout)
        statuses.append(status)
        if row:
            return row, statuses
    return {}, statuses


def _patch_fundamental_valuation_module(module: Any) -> bool:
    if getattr(module, "_fmp_stable_endpoint_patch_applied", False):
        return False

    module._fmp_url = _stable_fmp_url  # type: ignore[attr-defined]
    original_fetch_profile = getattr(module, "_fetch_profile", None)

    def patched_fetch_profile(core: Any, symbol: str, fetch: bool = True) -> dict[str, Any]:
        symbol = str(symbol or "").upper().strip()
        neutral = getattr(module, "_neutral_profile")
        if not getattr(module, "ENABLED", True):
            return neutral(core, symbol, "disabled", "fundamental_valuation_disabled")
        if not fetch:
            stored_fn = getattr(module, "_stored_profiles", None)
            stored = stored_fn(core).get(symbol) if callable(stored_fn) else None
            return dict(stored) if stored else neutral(core, symbol, "cache_miss", "no_cached_fundamental_profile")

        key_fn = getattr(module, "_fmp_key", None)
        key = key_fn() if callable(key_fn) else ""
        if not key:
            return neutral(core, symbol, "missing_api_key", "missing_FMP_API_KEY")

        try:
            endpoint_status: dict[str, Any] = {}
            profile, profile_status = _fetch_stable_first(module, "profile", symbol, key)
            endpoint_status["profile"] = profile_status

            ratios, ratios_status = _fetch_stable_first(module, "ratios-ttm", symbol, key)
            endpoint_status["ratios-ttm"] = ratios_status

            rating, rating_statuses = _fetch_stable_first_any(
                module,
                ("ratings-snapshot", "grades", "financial-scores"),
                symbol,
                key,
            )
            endpoint_status["rating_candidates"] = rating_statuses

            target, target_statuses = _fetch_stable_first_any(
                module,
                ("price-target-consensus", "price-target-summary"),
                symbol,
                key,
            )
            endpoint_status["target_candidates"] = target_statuses

            if not (profile or ratios or rating or target):
                row = neutral(core, symbol, "provider_empty", "stable_provider_returned_no_data")
            else:
                score_fn = getattr(module, "_score_profile")
                row = score_fn(core, symbol, profile, ratios, rating, target)

            row["provider_endpoint_family"] = "stable"
            row["provider_legacy_endpoint_disabled"] = True
            row["provider_endpoint_status"] = endpoint_status
            return row
        except Exception as exc:
            row = neutral(core, symbol, "provider_error", f"stable_provider_error: {type(exc).__name__}: {str(exc)[:120]}")
            row["provider_endpoint_family"] = "stable"
            row["provider_legacy_endpoint_disabled"] = True
            return row

    patched_fetch_profile._fmp_stable_endpoint_patch = True  # type: ignore[attr-defined]
    patched_fetch_profile._original_fetch_profile = original_fetch_profile  # type: ignore[attr-defined]
    module._fetch_profile = patched_fetch_profile  # type: ignore[attr-defined]
    module._fmp_stable_endpoint_patch_applied = True  # type: ignore[attr-defined]
    return True


def _patch_research_advisory_module(module: Any) -> bool:
    if getattr(module, "_fmp_stable_endpoint_patch_applied", False):
        return False

    module._fmp_url = _stable_fmp_url  # type: ignore[attr-defined]
    original_fetch_fundamentals = getattr(module, "_fetch_fundamentals", None)

    def patched_fetch_fundamentals(symbols: list[str], force_refresh: bool = False):
        selected = module._unique(symbols)[: max(1, int(getattr(module, "RESEARCH_FUNDAMENTAL_MAX_SYMBOLS", 8)))]
        key = module._fmp_key()
        cache_key = ",".join(selected)
        now = time.time()
        diagnostics: dict[str, Any] = {
            "enabled": bool(getattr(module, "RESEARCH_FUNDAMENTALS_ENABLED", True)),
            "provider": getattr(module, "RESEARCH_FUNDAMENTAL_PROVIDER", "fmp"),
            "provider_configured": bool(key),
            "provider_endpoint_family": "stable",
            "legacy_endpoint_disabled": True,
            "symbols_requested": selected,
            "symbols_loaded": 0,
            "cache_hit": False,
            "errors": [],
        }

        if not getattr(module, "RESEARCH_FUNDAMENTALS_ENABLED", True):
            diagnostics["status_detail"] = "disabled_by_env"
            return {}, diagnostics
        if getattr(module, "RESEARCH_FUNDAMENTAL_PROVIDER", "fmp") != "fmp":
            diagnostics["status_detail"] = "unsupported_provider"
            return {}, diagnostics
        if not key:
            diagnostics["status_detail"] = "missing_api_key"
            diagnostics["recommended_env_keys"] = ["FMP_API_KEY", "FINANCIALMODELINGPREP_API_KEY"]
            return {}, diagnostics

        cache = getattr(module, "_FUND_CACHE", {})
        ttl = int(getattr(module, "RESEARCH_FUNDAMENTAL_CACHE_TTL_SECONDS", 3600))
        if (
            not force_refresh
            and isinstance(cache, dict)
            and cache.get("payload") is not None
            and cache.get("key") == cache_key
            and now - float(cache.get("ts") or 0.0) < ttl
        ):
            diagnostics["cache_hit"] = True
            diagnostics["status_detail"] = "ok_cached"
            payload = module._safe_dict(cache.get("payload"))
            diagnostics["symbols_loaded"] = len(payload)
            return payload, diagnostics

        out: dict[str, dict[str, Any]] = {}
        timeout = float(getattr(module, "RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS", 3.0))

        for symbol in selected:
            endpoint_status: dict[str, Any] = {}
            profile, profile_status = _fetch_stable_first(module, "profile", symbol, key, timeout=timeout)
            ratios, ratios_status = _fetch_stable_first(module, "ratios-ttm", symbol, key, timeout=timeout)
            endpoint_status["profile"] = profile_status
            endpoint_status["ratios-ttm"] = ratios_status

            if not (profile or ratios):
                diagnostics["errors"].append({
                    "symbol": symbol,
                    "error": "stable_provider_returned_no_profile_or_ratios",
                    "endpoint_status": endpoint_status,
                })

            try:
                quality, valuation, reasons, metrics = module._score_fundamentals(profile, ratios)
            except Exception as exc:
                quality, valuation, reasons, metrics = 0.0, 0.0, [f"fundamental_score_error: {type(exc).__name__}"], {}
                diagnostics["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})

            out[symbol] = {
                "symbol": symbol,
                "provider": "fmp",
                "provider_endpoint_family": "stable",
                "legacy_endpoint_disabled": True,
                "endpoint_status": endpoint_status,
                "loaded": bool(profile or ratios),
                "fundamental_quality_raw": quality,
                "valuation_context_raw": valuation,
                "fundamental_reasons": reasons,
                "metrics": metrics,
                "company_name": profile.get("companyName") or profile.get("company_name"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
            }

        diagnostics["symbols_loaded"] = sum(1 for row in out.values() if row.get("loaded"))
        diagnostics["status_detail"] = "ok" if diagnostics["symbols_loaded"] else "provider_returned_no_fundamentals"
        if isinstance(cache, dict):
            cache.update({"ts": now, "key": cache_key, "payload": out})
        return out, diagnostics

    patched_fetch_fundamentals._fmp_stable_endpoint_patch = True  # type: ignore[attr-defined]
    patched_fetch_fundamentals._original_fetch_fundamentals = original_fetch_fundamentals  # type: ignore[attr-defined]
    module._fetch_fundamentals = patched_fetch_fundamentals  # type: ignore[attr-defined]
    module._fmp_stable_endpoint_patch_applied = True  # type: ignore[attr-defined]
    return True


def _patch_fmp_stable_endpoints() -> None:
    """Convert FMP integrations from retired /api/v3 URLs to current /stable URLs."""
    try:
        import research_advisory_engine
        _patch_research_advisory_module(research_advisory_engine)
    except Exception:
        pass
    try:
        import fundamental_valuation_risk_layer
        _patch_fundamental_valuation_module(fundamental_valuation_risk_layer)
    except Exception:
        pass


def _status_payload() -> dict[str, Any]:
    m = _mod()
    flask_app = getattr(m, "app", None) if m is not None else None
    rules = sorted(_existing_rules(flask_app)) if flask_app is not None else []
    fmp_patch = {}
    try:
        import research_advisory_engine
        fmp_patch["research_advisory_stable_endpoint_patch"] = bool(getattr(research_advisory_engine, "_fmp_stable_endpoint_patch_applied", False))
    except Exception:
        fmp_patch["research_advisory_stable_endpoint_patch"] = False
    try:
        import fundamental_valuation_risk_layer
        fmp_patch["fundamental_valuation_stable_endpoint_patch"] = bool(getattr(fundamental_valuation_risk_layer, "_fmp_stable_endpoint_patch_applied", False))
    except Exception:
        fmp_patch["fundamental_valuation_stable_endpoint_patch"] = False
    return {
        "status": "ok",
        "type": "startup_loader_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "module_found": bool(m is not None),
        "flask_app_found": bool(flask_app is not None),
        "breakout_status_route_registered": "/paper/breakout-participation-status" in rules,
        "breakout_leaders_route_registered": "/paper/breakout-leaders" in rules,
        "paper_exposure_route_registered": "/paper/paper-exposure-status" in rules,
        "paper_participation_route_registered": "/paper/paper-participation-status" in rules,
        "risk_on_concentration_policy_route_registered": "/paper/risk-on-concentration-policy" in rules,
        "breakout_rotation_route_registered": "/paper/breakout-rotation-status" in rules,
        "patch_stack_guard_route_registered": "/paper/patch-stack-guard-status" in rules,
        "research_advisory_route_registered": "/paper/research-advisory-status" in rules,
        "scanner_research_ranking_route_registered": "/paper/scanner-research-ranking" in rules,
        "fundamental_score_route_registered": "/paper/fundamental-score-status" in rules,
        "fundamental_valuation_risk_route_registered": "/paper/fundamental-valuation-risk-status" in rules,
        "analyst_valuation_risk_route_registered": "/paper/analyst-valuation-risk-status" in rules,
        "fmp_stable_endpoint_patch": fmp_patch,
        "routes_count": len(rules),
    }


def _register_startup_status(flask_app: Any) -> None:
    if flask_app is None or "/paper/startup-loader-status" in _existing_rules(flask_app):
        return
    try:
        from flask import jsonify

        def startup_loader_status():
            return jsonify(_status_payload())

        flask_app.add_url_rule("/paper/startup-loader-status", "startup_loader_status", startup_loader_status)
    except Exception:
        pass


def _register_all(flask_app: Any | None = None, m: Any | None = None) -> None:
    _import_usercustomize()
    _patch_one_link_check()
    m = m or _mod()
    flask_app = flask_app or (getattr(m, "app", None) if m is not None else None)

    if flask_app is not None:
        _register_usercustomize_routes(flask_app, m)
        _register_startup_status(flask_app)

    _register_risk_bootstrap(flask_app, m)
    _register_eod_hybrid(flask_app)
    _register_patch_stack_guard(flask_app, m)
    _register_module(flask_app, m, "breakout_participation_layer")
    _register_module(flask_app, m, "paper_exposure_rotation")
    _register_module(flask_app, m, "paper_participation_allocator")
    _register_module(flask_app, m, "paper_risk_on_concentration_policy", route_args="app_and_module")
    _register_patch_stack_guard(flask_app, m)
    _register_research_advisory(flask_app, m)
    _register_fundamental_valuation_risk(flask_app, m)
    _patch_fmp_stable_endpoints()

    if flask_app is not None:
        _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog() -> None:
    for _ in range(1800):
        try:
            _register_all()
        except Exception:
            pass
        time.sleep(0.1)


try:
    from flask import Flask

    if not getattr(Flask.__init__, "_unified_startup_loader_patched", False):
        _original_init = Flask.__init__

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            try:
                _register_all(self, _mod())
            except Exception:
                pass

        _patched_init._unified_startup_loader_patched = True
        Flask.__init__ = _patched_init
except Exception:
    pass


_register_all()
threading.Thread(target=_watchdog, daemon=True).start()
