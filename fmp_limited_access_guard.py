"""Limited-access FMP guard for valuation/research advisory layers.

Adds explicit access tiers and skips stable endpoints that returned plan-denied
errors during the same UTC day. Advisory only: no entries, halts, stops, or max
position rules are overridden here.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
import urllib.parse
from typing import Any

VERSION = "fmp-limited-access-guard-2026-05-29-v1"
_DENIED: dict[str, dict[str, Any]] = {}


def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    return None


def _stable_path(path: str) -> str:
    path = str(path or "").strip().strip("/")
    return {
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
    }.get(path, path)


def _url(path: str, symbol: str, key: str) -> str:
    q = urllib.parse.urlencode({"symbol": str(symbol).upper().strip(), "apikey": str(key).strip()})
    return f"https://financialmodelingprep.com/stable/{urllib.parse.quote(_stable_path(path))}?{q}"


def _first(module: Any, payload: Any) -> dict[str, Any]:
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
    return payload if isinstance(payload, dict) else {}


def _fetch_json(module: Any, url: str, timeout: float | None = None) -> Any:
    fn = getattr(module, "_fetch_json", None)
    if not callable(fn):
        raise RuntimeError("module_fetch_json_missing")
    try:
        return fn(url, timeout) if timeout is not None else fn(url)
    except TypeError:
        return fn(url)


def _is_denied(text: str) -> bool:
    s = str(text or "").lower()
    return "402" in s or "payment required" in s or "valid subscriptions" in s or "legacy endpoint" in s


def _endpoint(path: str) -> str:
    return f"stable/{_stable_path(path)}"


def _cached(endpoint: str) -> dict[str, Any] | None:
    row = _DENIED.get(endpoint)
    if not isinstance(row, dict):
        return None
    if row.get("date") != _today():
        _DENIED.pop(endpoint, None)
        return None
    return row


def _fetch_first(module: Any, path: str, symbol: str, key: str, timeout: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    endpoint = _endpoint(path)
    cached = _cached(endpoint)
    if cached:
        return {}, {
            "endpoint": endpoint,
            "ok": False,
            "skipped": True,
            "skip_reason": "plan_denied_cached_for_today",
            "access_denial_cached": True,
            "cached_error": cached.get("error"),
        }
    try:
        row = _first(module, _fetch_json(module, _url(path, symbol, key), timeout=timeout))
        return row, {"endpoint": endpoint, "ok": bool(row)}
    except Exception as exc:
        err = f"{type(exc).__name__}: {str(exc)[:160]}"
        status = {"endpoint": endpoint, "ok": False, "error": err}
        if _is_denied(err):
            _DENIED[endpoint] = {"date": _today(), "error": err, "ts": time.time()}
            status["access_denial_cached"] = True
            status["skip_policy"] = "daily_endpoint_cache"
        return {}, status


def _fetch_any(module: Any, paths: tuple[str, ...], symbol: str, key: str, timeout: float | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    statuses: list[dict[str, Any]] = []
    for path in paths:
        row, status = _fetch_first(module, path, symbol, key, timeout=timeout)
        statuses.append(status)
        if row:
            return row, statuses
    return {}, statuses


def _statuses(endpoint_status: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in endpoint_status.values():
        if isinstance(value, list):
            out.extend([x for x in value if isinstance(x, dict)])
        elif isinstance(value, dict):
            out.append(value)
    return out


def _denied_endpoints(endpoint_status: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for status in _statuses(endpoint_status):
        if status.get("access_denial_cached") or status.get("skip_reason") == "plan_denied_cached_for_today":
            endpoint = status.get("endpoint")
            if endpoint and str(endpoint) not in out:
                out.append(str(endpoint))
    return out


def _tier(profile: dict[str, Any], ratios: dict[str, Any], rating: dict[str, Any] | None = None, target: dict[str, Any] | None = None) -> str:
    rating = rating or {}
    target = target or {}
    if profile and ratios and (rating or target):
        return "full_valuation_data"
    if profile and (ratios or rating or target):
        return "partial_data"
    if profile:
        return "profile_only"
    return "no_data"


def _tag(row: dict[str, Any], endpoint_status: dict[str, Any], tier: str) -> dict[str, Any]:
    denied = _denied_endpoints(endpoint_status)
    row["fmp_data_access_tier"] = tier
    row["fmp_plan_limited"] = bool(denied)
    row["fmp_plan_limited_endpoints"] = denied
    row["fmp_endpoint_skip_policy"] = "daily_endpoint_cache"
    row["provider_endpoint_family"] = "stable"
    row["provider_legacy_endpoint_disabled"] = True
    row["provider_endpoint_status"] = endpoint_status
    return row


def _patch_fundamental(module: Any) -> bool:
    if getattr(module, "_fmp_limited_access_guard_applied", False):
        return False
    module._fmp_url = _url  # type: ignore[attr-defined]
    original = getattr(module, "_fetch_profile", None)

    def patched_fetch_profile(core: Any, symbol: str, fetch: bool = True) -> dict[str, Any]:
        symbol = str(symbol or "").upper().strip()
        neutral = getattr(module, "_neutral_profile")
        if not getattr(module, "ENABLED", True):
            return _tag(neutral(core, symbol, "disabled", "fundamental_valuation_disabled"), {}, "no_data")
        if not fetch:
            stored_fn = getattr(module, "_stored_profiles", None)
            stored = stored_fn(core).get(symbol) if callable(stored_fn) else None
            return dict(stored) if stored else _tag(neutral(core, symbol, "cache_miss", "no_cached_fundamental_profile"), {}, "no_data")
        key_fn = getattr(module, "_fmp_key", None)
        key = key_fn() if callable(key_fn) else ""
        if not key:
            return _tag(neutral(core, symbol, "missing_api_key", "missing_FMP_API_KEY"), {}, "no_data")
        try:
            endpoint_status: dict[str, Any] = {}
            profile, endpoint_status["profile"] = _fetch_first(module, "profile", symbol, key)
            ratios, endpoint_status["ratios-ttm"] = _fetch_first(module, "ratios-ttm", symbol, key)
            rating, endpoint_status["rating_candidates"] = _fetch_any(module, ("ratings-snapshot", "grades", "financial-scores"), symbol, key)
            target, endpoint_status["target_candidates"] = _fetch_any(module, ("price-target-consensus", "price-target-summary"), symbol, key)
            access_tier = _tier(profile, ratios, rating, target)
            if not (profile or ratios or rating or target):
                row = neutral(core, symbol, "provider_empty", "stable_provider_returned_no_data")
            else:
                row = getattr(module, "_score_profile")(core, symbol, profile, ratios, rating, target)
            return _tag(row, endpoint_status, access_tier)
        except Exception as exc:
            return _tag(neutral(core, symbol, "provider_error", f"stable_provider_error: {type(exc).__name__}: {str(exc)[:120]}"), {}, "no_data")

    patched_fetch_profile._fmp_limited_access_guard = True  # type: ignore[attr-defined]
    patched_fetch_profile._original_fetch_profile = original  # type: ignore[attr-defined]
    module._fetch_profile = patched_fetch_profile  # type: ignore[attr-defined]
    module._fmp_limited_access_guard_applied = True  # type: ignore[attr-defined]
    return True


def _patch_research(module: Any) -> bool:
    if getattr(module, "_fmp_limited_access_guard_applied", False):
        return False
    module._fmp_url = _url  # type: ignore[attr-defined]
    original = getattr(module, "_fetch_fundamentals", None)

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
            "fmp_endpoint_skip_policy": "daily_endpoint_cache",
            "symbols_requested": selected,
            "symbols_loaded": 0,
            "symbols_profile_only": 0,
            "symbols_partial_data": 0,
            "symbols_full_valuation_data": 0,
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
        if (not force_refresh and isinstance(cache, dict) and cache.get("payload") is not None and cache.get("key") == cache_key and now - float(cache.get("ts") or 0.0) < ttl):
            payload = module._safe_dict(cache.get("payload"))
            diagnostics["cache_hit"] = True
            diagnostics["status_detail"] = "ok_cached"
            diagnostics["symbols_loaded"] = len(payload)
            diagnostics["symbols_profile_only"] = sum(1 for x in payload.values() if isinstance(x, dict) and x.get("fmp_data_access_tier") == "profile_only")
            diagnostics["symbols_partial_data"] = sum(1 for x in payload.values() if isinstance(x, dict) and x.get("fmp_data_access_tier") == "partial_data")
            diagnostics["symbols_full_valuation_data"] = sum(1 for x in payload.values() if isinstance(x, dict) and x.get("fmp_data_access_tier") == "full_valuation_data")
            return payload, diagnostics

        out: dict[str, dict[str, Any]] = {}
        timeout = float(getattr(module, "RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS", 3.0))
        for symbol in selected:
            endpoint_status: dict[str, Any] = {}
            profile, endpoint_status["profile"] = _fetch_first(module, "profile", symbol, key, timeout=timeout)
            ratios, endpoint_status["ratios-ttm"] = _fetch_first(module, "ratios-ttm", symbol, key, timeout=timeout)
            access_tier = _tier(profile, ratios)
            if not (profile or ratios):
                diagnostics["errors"].append({"symbol": symbol, "error": "stable_provider_returned_no_profile_or_ratios", "endpoint_status": endpoint_status})
            try:
                quality, valuation, reasons, metrics = module._score_fundamentals(profile, ratios)
            except Exception as exc:
                quality, valuation, reasons, metrics = 0.0, 0.0, [f"fundamental_score_error: {type(exc).__name__}"], {}
                diagnostics["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            denied = _denied_endpoints(endpoint_status)
            out[symbol] = {
                "symbol": symbol,
                "provider": "fmp",
                "provider_endpoint_family": "stable",
                "legacy_endpoint_disabled": True,
                "endpoint_status": endpoint_status,
                "fmp_data_access_tier": access_tier,
                "fmp_plan_limited": bool(denied),
                "fmp_plan_limited_endpoints": denied,
                "fmp_endpoint_skip_policy": "daily_endpoint_cache",
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
        diagnostics["symbols_profile_only"] = sum(1 for row in out.values() if row.get("fmp_data_access_tier") == "profile_only")
        diagnostics["symbols_partial_data"] = sum(1 for row in out.values() if row.get("fmp_data_access_tier") == "partial_data")
        diagnostics["symbols_full_valuation_data"] = sum(1 for row in out.values() if row.get("fmp_data_access_tier") == "full_valuation_data")
        diagnostics["status_detail"] = "ok" if diagnostics["symbols_loaded"] else "provider_returned_no_fundamentals"
        if isinstance(cache, dict):
            cache.update({"ts": now, "key": cache_key, "payload": out})
        return out, diagnostics

    patched_fetch_fundamentals._fmp_limited_access_guard = True  # type: ignore[attr-defined]
    patched_fetch_fundamentals._original_fetch_fundamentals = original  # type: ignore[attr-defined]
    module._fetch_fundamentals = patched_fetch_fundamentals  # type: ignore[attr-defined]
    module._fmp_limited_access_guard_applied = True  # type: ignore[attr-defined]
    return True


def apply_runtime_overrides(m: Any | None = None) -> dict[str, Any]:
    patched: list[str] = []
    errors: list[str] = []
    try:
        import research_advisory_engine
        if _patch_research(research_advisory_engine):
            patched.append("research_advisory_engine")
    except Exception as exc:
        errors.append(f"research_advisory_engine: {type(exc).__name__}: {str(exc)[:160]}")
    try:
        import fundamental_valuation_risk_layer
        if _patch_fundamental(fundamental_valuation_risk_layer):
            patched.append("fundamental_valuation_risk_layer")
    except Exception as exc:
        errors.append(f"fundamental_valuation_risk_layer: {type(exc).__name__}: {str(exc)[:160]}")
    return {"status": "ok" if not errors else "warn", "type": "fmp_limited_access_guard_apply", "version": VERSION, "patched": patched, "errors": errors}


def status_payload() -> dict[str, Any]:
    apply_runtime_overrides(_mod())
    return {
        "status": "ok",
        "type": "fmp_limited_access_guard_status",
        "version": VERSION,
        "generated_local": _now(),
        "denied_endpoint_cache": dict(_DENIED),
        "cache_policy": "plan-denied stable endpoints are skipped until the next UTC date",
        "access_tiers": ["no_data", "profile_only", "partial_data", "full_valuation_data"],
        "advisory_only": True,
        "does_not_force_entries": True,
        "does_not_bypass_halts": True,
        "does_not_bypass_stop_losses": True,
    }


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/fmp-limited-access-guard-status" in existing:
        return
    try:
        from flask import jsonify

        def fmp_limited_access_guard_status():
            return jsonify(status_payload())

        flask_app.add_url_rule("/paper/fmp-limited-access-guard-status", "fmp_limited_access_guard_status", fmp_limited_access_guard_status)
    except Exception:
        pass


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
