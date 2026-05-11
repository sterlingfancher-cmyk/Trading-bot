"""Runtime safety patch for price-fetch timeouts and runner freshness.

This module is intentionally additive: it monkey-patches app.py at startup without
requiring a large app.py rewrite. It addresses the May 11 Gunicorn timeout where
/paper/run stalled inside yfinance.download while fetching 5-minute prices.

What it does:
- Replaces app.download_prices with a yfinance call that uses timeout=...
  and threads=False.
- Replaces app.latest_price with a cache-first safe latest-price lookup.
- Uses stale cached prices as a fallback instead of letting one slow quote kill
  the Gunicorn worker.
- Adds /paper/price-health and /paper/runner-freshness monitoring endpoints.
- Adds /paper/runner-safety-status as an install/status endpoint.
- Does not write state.json and does not place trades.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import time
import traceback
from typing import Any, Dict, List, Tuple

VERSION = "runner-safety-price-timeout-2026-05-11"

PRICE_CACHE_TTL_SECONDS = int(os.environ.get("PRICE_CACHE_TTL_SECONDS", "120"))
PRICE_STALE_FALLBACK_SECONDS = int(os.environ.get("PRICE_STALE_FALLBACK_SECONDS", "1800"))
YF_DOWNLOAD_TIMEOUT_SECONDS = float(os.environ.get("YF_DOWNLOAD_TIMEOUT_SECONDS", "8"))
PRICE_HEALTH_TEST_SYMBOLS = [s.strip().upper() for s in os.environ.get("PRICE_HEALTH_TEST_SYMBOLS", "SPY,QQQ").split(",") if s.strip()]
RUNNER_FRESHNESS_MULTIPLIER = float(os.environ.get("RUNNER_FRESHNESS_MULTIPLIER", "2.5"))

REGISTERED_APP_IDS: set[int] = set()
_INSTALLED_MODULE_IDS: set[int] = set()
_ORIGINALS: Dict[str, Any] = {}

_PRICE_DF_CACHE: Dict[str, Dict[str, Any]] = {}
_LATEST_PRICE_CACHE: Dict[str, Dict[str, Any]] = {}
_HEALTH: Dict[str, Any] = {
    "version": VERSION,
    "installed": False,
    "download_wrapper_active": False,
    "latest_price_wrapper_active": False,
    "downloads_attempted": 0,
    "downloads_ok": 0,
    "downloads_failed": 0,
    "cache_hits": 0,
    "latest_cache_hits": 0,
    "fallback_price_hits": 0,
    "last_error": None,
    "last_error_symbol": None,
    "last_error_local": None,
    "last_success_symbol": None,
    "last_success_local": None,
}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_ts() -> float:
    return time.time()


def _safe_float(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None:
            return default
        val = float(x)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def _cache_key(symbol: str, period: str = "1d", interval: str = "5m") -> Tuple[str, str, str]:
    return (str(symbol or "").upper(), str(period or ""), str(interval or ""))


def _is_fresh(ts: float | int | None, ttl: float) -> bool:
    try:
        return bool(ts and (_now_ts() - float(ts)) <= float(ttl))
    except Exception:
        return False


def _df_empty(df: Any) -> bool:
    try:
        return bool(df is None or getattr(df, "empty", True))
    except Exception:
        return True


def _extract_last_close(df: Any) -> float | None:
    """Return the latest close from a yfinance DataFrame safely."""
    try:
        if _df_empty(df):
            return None
        close = df["Close"]
        # yfinance can return a DataFrame for multi-index columns. If so, use the
        # first available column.
        try:
            if hasattr(close, "columns"):
                if len(close.columns) < 1:
                    return None
                close = close.iloc[:, 0]
        except Exception:
            pass
        close = close.dropna()
        if len(close) < 1:
            return None
        return _safe_float(close.iloc[-1])
    except Exception:
        return None


def _record_error(symbol: str, exc: BaseException) -> None:
    _HEALTH["downloads_failed"] = int(_HEALTH.get("downloads_failed", 0)) + 1
    _HEALTH["last_error"] = f"{type(exc).__name__}: {exc}"
    _HEALTH["last_error_symbol"] = str(symbol or "").upper()
    _HEALTH["last_error_local"] = _now_text()


def _record_success(symbol: str) -> None:
    _HEALTH["downloads_ok"] = int(_HEALTH.get("downloads_ok", 0)) + 1
    _HEALTH["last_success_symbol"] = str(symbol or "").upper()
    _HEALTH["last_success_local"] = _now_text()


def _safe_download_prices_factory(core: Any):
    def safe_download_prices(symbol: str, period: str = "1d", interval: str = "5m"):
        key = _cache_key(symbol, period, interval)
        cached = _PRICE_DF_CACHE.get("|".join(key))
        if cached and _is_fresh(cached.get("ts"), PRICE_CACHE_TTL_SECONDS):
            _HEALTH["cache_hits"] = int(_HEALTH.get("cache_hits", 0)) + 1
            return cached.get("df")

        _HEALTH["downloads_attempted"] = int(_HEALTH.get("downloads_attempted", 0)) + 1
        try:
            yf = getattr(core, "yf", None)
            if yf is None:
                raise RuntimeError("core.yf is not available")

            # yfinance supports timeout in current releases. threads=False avoids
            # yfinance's internal multi-thread behavior for single-symbol calls.
            try:
                df = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                    timeout=YF_DOWNLOAD_TIMEOUT_SECONDS,
                )
            except TypeError:
                # Fallback for older yfinance versions that do not accept timeout.
                # Keep threads disabled and rely on requests/network defaults.
                df = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                )

            if not _df_empty(df):
                _PRICE_DF_CACHE["|".join(key)] = {"ts": _now_ts(), "df": df}
                px = _extract_last_close(df)
                if px is not None:
                    _LATEST_PRICE_CACHE[str(symbol).upper()] = {"ts": _now_ts(), "price": px, "source": "download"}
                _record_success(symbol)
                return df
            raise RuntimeError("empty price dataframe")
        except BaseException as exc:
            _record_error(symbol, exc)
            # Stale but recent DataFrame fallback protects calculate_equity and
            # scanner cycles from one quote failure.
            if cached and _is_fresh(cached.get("ts"), PRICE_STALE_FALLBACK_SECONDS):
                _HEALTH["cache_hits"] = int(_HEALTH.get("cache_hits", 0)) + 1
                _HEALTH["fallback_price_hits"] = int(_HEALTH.get("fallback_price_hits", 0)) + 1
                return cached.get("df")
            # Last-resort original fallback is disabled by default because the
            # original path is exactly where the worker timeout occurred. Enable
            # only if explicitly needed.
            if os.environ.get("ALLOW_ORIGINAL_DOWNLOAD_FALLBACK", "false").lower() in {"1", "true", "yes", "on"}:
                original = _ORIGINALS.get("download_prices")
                if callable(original):
                    return original(symbol, period=period, interval=interval)
            return None

    safe_download_prices._runner_safety_wrapped = True  # type: ignore[attr-defined]
    return safe_download_prices


def _safe_latest_price_factory(core: Any):
    def safe_latest_price(symbol: str):
        sym = str(symbol or "").upper()
        cached = _LATEST_PRICE_CACHE.get(sym)
        if cached and _is_fresh(cached.get("ts"), PRICE_CACHE_TTL_SECONDS):
            _HEALTH["latest_cache_hits"] = int(_HEALTH.get("latest_cache_hits", 0)) + 1
            return cached.get("price")

        try:
            df = core.download_prices(sym, period="1d", interval="5m")
            px = _extract_last_close(df)
            if px is not None:
                _LATEST_PRICE_CACHE[sym] = {"ts": _now_ts(), "price": px, "source": "latest_download"}
                return px
        except BaseException as exc:
            _record_error(sym, exc)

        # Stale price fallback. This is safer than killing the worker mid-cycle.
        cached = _LATEST_PRICE_CACHE.get(sym)
        if cached and _is_fresh(cached.get("ts"), PRICE_STALE_FALLBACK_SECONDS):
            _HEALTH["fallback_price_hits"] = int(_HEALTH.get("fallback_price_hits", 0)) + 1
            return cached.get("price")
        return None

    safe_latest_price._runner_safety_wrapped = True  # type: ignore[attr-defined]
    return safe_latest_price


def install(core: Any) -> Dict[str, Any]:
    """Patch app.py price functions in-place."""
    if core is None:
        return {"status": "error", "version": VERSION, "reason": "core module missing"}
    if id(core) in _INSTALLED_MODULE_IDS:
        return status(core)

    try:
        if hasattr(core, "download_prices") and not getattr(core.download_prices, "_runner_safety_wrapped", False):
            _ORIGINALS["download_prices"] = core.download_prices
            core.download_prices = _safe_download_prices_factory(core)
            _HEALTH["download_wrapper_active"] = True
        if hasattr(core, "latest_price") and not getattr(core.latest_price, "_runner_safety_wrapped", False):
            _ORIGINALS["latest_price"] = core.latest_price
            core.latest_price = _safe_latest_price_factory(core)
            _HEALTH["latest_price_wrapper_active"] = True
        _INSTALLED_MODULE_IDS.add(id(core))
        _HEALTH["installed"] = True
        _HEALTH["installed_local"] = _now_text()
        return status(core)
    except BaseException as exc:
        _HEALTH["installed"] = False
        _HEALTH["last_error"] = f"install failed: {type(exc).__name__}: {exc}"
        _HEALTH["last_error_local"] = _now_text()
        return {"status": "error", "version": VERSION, "error": str(exc), "traceback": traceback.format_exc()[-2000:]}


def _market_clock(core: Any) -> Dict[str, Any]:
    try:
        if hasattr(core, "market_clock"):
            obj = core.market_clock()
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    try:
        if hasattr(core, "market_clock_snapshot"):
            obj = core.market_clock_snapshot()
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    try:
        now = core.now_local() if hasattr(core, "now_local") else dt.datetime.now()
        open_hour = int(getattr(core, "REGULAR_OPEN_HOUR", 8))
        open_minute = int(getattr(core, "REGULAR_OPEN_MINUTE", 30))
        close_hour = int(getattr(core, "REGULAR_CLOSE_HOUR", 15))
        close_minute = int(getattr(core, "REGULAR_CLOSE_MINUTE", 0))
        regular_open = now.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
        regular_close = now.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
        is_weekday = now.weekday() < 5
        is_open = bool(is_weekday and regular_open <= now <= regular_close)
        return {
            "is_open": is_open,
            "now_local": now.strftime("%Y-%m-%d %H:%M:%S %Z") if hasattr(now, "strftime") else str(now),
            "reason": "regular_session" if is_open else "outside_regular_session",
        }
    except Exception as exc:
        return {"is_open": None, "reason": "market_clock_unavailable", "error": str(exc)}


def _load_state(core: Any) -> Dict[str, Any]:
    try:
        if hasattr(core, "load_state"):
            state = core.load_state()
            return state if isinstance(state, dict) else {}
    except Exception:
        pass
    return {}


def freshness(core: Any) -> Dict[str, Any]:
    state = _load_state(core)
    auto = state.get("auto_runner", {}) if isinstance(state.get("auto_runner"), dict) else {}
    clock = _market_clock(core)
    interval = int(auto.get("interval_seconds") or getattr(core, "AUTO_RUN_INTERVAL_SECONDS", 300) or 300)
    now_ts = _now_ts()
    last_success_ts = auto.get("last_successful_run_ts") or auto.get("last_run_ts")
    last_attempt_ts = auto.get("last_attempt_ts") or auto.get("last_run_ts")

    seconds_since_success = None
    seconds_since_attempt = None
    try:
        if last_success_ts:
            seconds_since_success = round(now_ts - float(last_success_ts), 1)
    except Exception:
        pass
    try:
        if last_attempt_ts:
            seconds_since_attempt = round(now_ts - float(last_attempt_ts), 1)
    except Exception:
        pass

    market_open = bool(clock.get("is_open"))
    stale_threshold = int(max(interval * RUNNER_FRESHNESS_MULTIPLIER, interval + 60))
    stale_during_market = bool(market_open and (seconds_since_success is None or seconds_since_success > stale_threshold))
    status_value = "warn" if stale_during_market else "ok"
    notes: List[str] = []
    if stale_during_market:
        notes.append("market is open but last successful run is stale or missing")
    if auto.get("last_error"):
        notes.append("auto_runner has a last_error value")
    if auto.get("last_skip_reason"):
        notes.append(f"last skip: {auto.get('last_skip_reason')}")

    return {
        "status": status_value,
        "type": "runner_freshness",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_clock": clock,
        "auto_runner_enabled": auto.get("enabled"),
        "market_only": auto.get("market_only"),
        "interval_seconds": interval,
        "stale_threshold_seconds": stale_threshold,
        "last_attempt_ts": last_attempt_ts,
        "last_attempt_local": auto.get("last_attempt_local"),
        "last_run_ts": auto.get("last_run_ts"),
        "last_run_local": auto.get("last_run_local"),
        "last_successful_run_ts": last_success_ts,
        "last_successful_run_local": auto.get("last_successful_run_local"),
        "last_run_source": auto.get("last_run_source"),
        "last_skip_local": auto.get("last_skip_local"),
        "last_skip_reason": auto.get("last_skip_reason"),
        "last_error": auto.get("last_error"),
        "seconds_since_success": seconds_since_success,
        "seconds_since_attempt": seconds_since_attempt,
        "stale_during_market": stale_during_market,
        "notes": notes,
    }


def status(core: Any | None = None) -> Dict[str, Any]:
    out = dict(_HEALTH)
    out.update({
        "status": "ok" if out.get("installed") else "warn",
        "type": "runner_safety_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "price_cache_ttl_seconds": PRICE_CACHE_TTL_SECONDS,
        "price_stale_fallback_seconds": PRICE_STALE_FALLBACK_SECONDS,
        "yf_download_timeout_seconds": YF_DOWNLOAD_TIMEOUT_SECONDS,
        "cached_dataframes": len(_PRICE_DF_CACHE),
        "cached_latest_prices": len(_LATEST_PRICE_CACHE),
        "cached_symbols": sorted(_LATEST_PRICE_CACHE.keys())[:100],
        "original_download_fallback_allowed": os.environ.get("ALLOW_ORIGINAL_DOWNLOAD_FALLBACK", "false").lower() in {"1", "true", "yes", "on"},
    })
    if core is not None:
        out["runner_freshness"] = freshness(core)
    return out


def price_health(core: Any | None = None) -> Dict[str, Any]:
    payload = status(core)
    recent_prices = {}
    for sym, item in sorted(_LATEST_PRICE_CACHE.items()):
        recent_prices[sym] = {
            "price": item.get("price"),
            "age_seconds": round(_now_ts() - float(item.get("ts", _now_ts())), 1) if item.get("ts") else None,
            "source": item.get("source"),
        }
    payload.update({
        "type": "price_health",
        "recent_prices": recent_prices,
        "note": "This endpoint does not force a fresh yfinance download. It reports cache/fallback health only.",
    })
    return payload


def register_routes(flask_app: Any, core: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/runner-safety-status" not in existing:
        flask_app.add_url_rule("/paper/runner-safety-status", "runner_safety_status", lambda: jsonify(status(core)))
    if "/paper/price-health" not in existing:
        flask_app.add_url_rule("/paper/price-health", "paper_price_health", lambda: jsonify(price_health(core)))
    if "/paper/runner-freshness" not in existing:
        flask_app.add_url_rule("/paper/runner-freshness", "paper_runner_freshness", lambda: jsonify(freshness(core)))
    REGISTERED_APP_IDS.add(id(flask_app))
