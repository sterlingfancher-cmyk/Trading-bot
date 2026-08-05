"""Runtime hygiene for yfinance requests used by the paper-trading service.

This module filters known invalid/no-data symbols before provider calls, applies
short per-symbol backoff for transient failures, caches identical downloads for
one scanner cycle, and suppresses one specific upstream pandas deprecation
warning. It never changes strategy logic, thresholds, sizing, risk, order paths,
live authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import threading
import time
import warnings
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VERSION = "yfinance-data-hygiene-2026-08-05-v1"
CACHE_TTL_SECONDS = max(0.0, float(os.getenv("YFINANCE_DOWNLOAD_CACHE_TTL_SECONDS", "45")))
EMPTY_BACKOFF_THRESHOLD = max(1, int(os.getenv("YFINANCE_EMPTY_BACKOFF_THRESHOLD", "2")))
EMPTY_BACKOFF_SECONDS = max(30, int(os.getenv("YFINANCE_EMPTY_BACKOFF_SECONDS", "600")))
TIMEOUT_BACKOFF_THRESHOLD = max(1, int(os.getenv("YFINANCE_TIMEOUT_BACKOFF_THRESHOLD", "2")))
TIMEOUT_BACKOFF_SECONDS = max(15, int(os.getenv("YFINANCE_TIMEOUT_BACKOFF_SECONDS", "90")))
NO_DATA_QUARANTINE_SECONDS = max(300, int(os.getenv("YFINANCE_NO_DATA_QUARANTINE_SECONDS", "86400")))
MAX_CACHE_ROWS = max(20, int(os.getenv("YFINANCE_DOWNLOAD_CACHE_MAX_ROWS", "256")))
MAX_EVENTS = max(20, int(os.getenv("YFINANCE_HYGIENE_MAX_EVENTS", "200")))

_DEFAULT_BLOCKED_SYMBOLS = {"RGIT", "CIFRW", "SATS"}
_SPLIT_RE = re.compile(r"[\s,]+")
_NO_DATA_MARKERS = (
    "yfpricesmissingerror",
    "possibly delisted",
    "no price data found",
    "symbol may be delisted",
)
_TIMEOUT_MARKERS = ("timeout", "timed out", "curl: (28)", "resolving timed out")

_LOCK = threading.RLock()
_ORIGINAL_DOWNLOAD: Any = None
_INSTALLED = False
_REGISTERED_APP_IDS: set[int] = set()
_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
_SYMBOL_STATE: Dict[str, Dict[str, Any]] = {}
_EVENTS: List[Dict[str, Any]] = []
_TOTALS: Dict[str, int] = {
    "requests": 0,
    "provider_calls": 0,
    "cache_hits": 0,
    "static_blocks": 0,
    "dynamic_blocks": 0,
    "no_data_quarantines": 0,
    "timeout_backoffs": 0,
    "empty_backoffs": 0,
    "successful_calls": 0,
}


def _now_text(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _csv_env(name: str, default: Iterable[str]) -> set[str]:
    raw = os.getenv(name)
    values = default if raw is None else raw.split(",")
    return {str(value).upper().strip() for value in values if str(value).strip()}


def static_blocked_symbols() -> set[str]:
    return _csv_env("YFINANCE_KNOWN_NO_DATA_SYMBOLS", _DEFAULT_BLOCKED_SYMBOLS)


def normalize_symbol(value: Any) -> str:
    try:
        return str(value or "").strip().upper().lstrip("$")
    except Exception:
        return ""


def _requested_symbols(tickers: Any) -> List[str]:
    if isinstance(tickers, str):
        values = [value for value in _SPLIT_RE.split(tickers.strip()) if value]
    elif isinstance(tickers, (list, tuple, set)):
        values = list(tickers)
    else:
        values = [tickers]
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _rebuild_tickers(original: Any, symbols: Sequence[str]) -> Any:
    if isinstance(original, str):
        return symbols[0] if len(symbols) == 1 else " ".join(symbols)
    if isinstance(original, tuple):
        return tuple(symbols)
    if isinstance(original, set):
        return set(symbols)
    return list(symbols)


def _active_state(symbol: str, now: float | None = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    with _LOCK:
        row = dict(_SYMBOL_STATE.get(symbol) or {})
    if float(row.get("blocked_until") or 0.0) > now:
        return row
    return {}


def is_blocked_symbol(symbol: Any) -> bool:
    normalized = normalize_symbol(symbol)
    return bool(normalized and (normalized in static_blocked_symbols() or _active_state(normalized)))


def blocked_reason(symbol: Any) -> str | None:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return "blank_symbol"
    if normalized in static_blocked_symbols():
        return "known_no_data_symbol"
    state = _active_state(normalized)
    return str(state.get("reason") or "") or None


def sanitize_tickers(tickers: Any) -> Tuple[Any, List[str], List[Dict[str, Any]]]:
    requested = _requested_symbols(tickers)
    allowed: List[str] = []
    blocked: List[Dict[str, Any]] = []
    now = time.time()
    static = static_blocked_symbols()
    for symbol in requested:
        if symbol in static:
            blocked.append({"symbol": symbol, "reason": "known_no_data_symbol"})
            continue
        state = _active_state(symbol, now)
        if state:
            blocked.append(
                {
                    "symbol": symbol,
                    "reason": str(state.get("reason") or "temporary_symbol_backoff"),
                    "blocked_until": float(state.get("blocked_until") or 0.0),
                }
            )
            continue
        allowed.append(symbol)
    return _rebuild_tickers(tickers, allowed), allowed, blocked


def _frame_empty(frame: Any) -> bool:
    return frame is None or bool(getattr(frame, "empty", True))


def _copy_frame(frame: Any) -> Any:
    try:
        return frame.copy(deep=True)
    except TypeError:
        try:
            return frame.copy()
        except Exception:
            return frame
    except Exception:
        return frame


def _empty_frame() -> Any:
    try:
        import pandas as pd  # type: ignore
        return pd.DataFrame()
    except Exception:
        return None


def _cache_key(symbols: Sequence[str], args: Sequence[Any], kwargs: Dict[str, Any]) -> Tuple[Any, ...]:
    relevant = (
        kwargs.get("period"),
        kwargs.get("interval"),
        kwargs.get("start"),
        kwargs.get("end"),
        kwargs.get("prepost"),
        kwargs.get("auto_adjust"),
        kwargs.get("actions"),
        kwargs.get("repair"),
        kwargs.get("group_by"),
    )
    return (tuple(symbols), tuple(repr(value) for value in args), tuple(repr(value) for value in relevant))


def _cache_get(key: Tuple[Any, ...]) -> Any:
    if CACHE_TTL_SECONDS <= 0:
        return None
    now = time.time()
    with _LOCK:
        row = _CACHE.get(key)
        if not row or now - float(row.get("ts") or 0.0) > CACHE_TTL_SECONDS:
            if row:
                _CACHE.pop(key, None)
            return None
        _TOTALS["cache_hits"] += 1
        return _copy_frame(row.get("frame"))


def _cache_put(key: Tuple[Any, ...], frame: Any) -> None:
    if CACHE_TTL_SECONDS <= 0 or _frame_empty(frame):
        return
    with _LOCK:
        _CACHE[key] = {"ts": time.time(), "frame": _copy_frame(frame)}
        if len(_CACHE) > MAX_CACHE_ROWS:
            oldest = sorted(_CACHE.items(), key=lambda item: float(item[1].get("ts") or 0.0))
            for stale_key, _ in oldest[: len(_CACHE) - MAX_CACHE_ROWS]:
                _CACHE.pop(stale_key, None)


def _record_event(status: str, symbols: Sequence[str], detail: str = "") -> None:
    row: Dict[str, Any] = {
        "generated_local": _now_text(),
        "status": status,
        "symbols": list(symbols),
    }
    if detail:
        row["detail"] = detail[:500]
    with _LOCK:
        _EVENTS.append(row)
        del _EVENTS[:-MAX_EVENTS]


def _provider_error_text(yf_module: Any, symbol: str) -> str:
    try:
        shared = getattr(yf_module, "shared", None)
        errors = getattr(shared, "_ERRORS", None)
        if isinstance(errors, dict) and symbol in errors:
            return str(errors.get(symbol) or "")
    except Exception:
        pass
    try:
        shared = sys.modules.get("yfinance.shared")
        errors = getattr(shared, "_ERRORS", None)
        if isinstance(errors, dict) and symbol in errors:
            return str(errors.get(symbol) or "")
    except Exception:
        pass
    return ""


def _classify_error(text: str) -> str:
    lowered = str(text or "").lower()
    if any(marker in lowered for marker in _NO_DATA_MARKERS):
        return "no_data"
    if any(marker in lowered for marker in _TIMEOUT_MARKERS):
        return "timeout"
    return "empty"


def _apply_failure(symbol: str, failure_type: str, detail: str = "") -> None:
    now = time.time()
    with _LOCK:
        row = dict(_SYMBOL_STATE.get(symbol) or {})
        if failure_type == "no_data":
            row.update(
                {
                    "reason": "provider_confirmed_no_data",
                    "blocked_until": now + NO_DATA_QUARANTINE_SECONDS,
                    "no_data_count": int(row.get("no_data_count") or 0) + 1,
                    "last_error": detail[:500],
                    "updated_ts": now,
                }
            )
            _TOTALS["no_data_quarantines"] += 1
        elif failure_type == "timeout":
            count = int(row.get("timeout_count") or 0) + 1
            row.update({"timeout_count": count, "last_error": detail[:500], "updated_ts": now})
            if count >= TIMEOUT_BACKOFF_THRESHOLD:
                row.update({"reason": "transient_timeout_backoff", "blocked_until": now + TIMEOUT_BACKOFF_SECONDS})
                _TOTALS["timeout_backoffs"] += 1
        else:
            count = int(row.get("empty_count") or 0) + 1
            row.update({"empty_count": count, "last_error": detail[:500], "updated_ts": now})
            if count >= EMPTY_BACKOFF_THRESHOLD:
                row.update({"reason": "repeated_empty_response_backoff", "blocked_until": now + EMPTY_BACKOFF_SECONDS})
                _TOTALS["empty_backoffs"] += 1
        _SYMBOL_STATE[symbol] = row


def _clear_success(symbols: Sequence[str]) -> None:
    with _LOCK:
        for symbol in symbols:
            row = dict(_SYMBOL_STATE.get(symbol) or {})
            if not row:
                continue
            if str(row.get("reason") or "") == "provider_confirmed_no_data":
                continue
            _SYMBOL_STATE.pop(symbol, None)


def _filter_warning() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r".*Timestamp\.utcnow is deprecated.*",
        category=Warning,
        module=r"yfinance\.scrapers\.quote",
    )


def _patch_runtime_sources(core: Any = None) -> None:
    static = static_blocked_symbols()
    if core is not None:
        try:
            universe = list(getattr(core, "UNIVERSE", []) or [])
            setattr(core, "UNIVERSE", [symbol for symbol in universe if normalize_symbol(symbol) not in static])
        except Exception:
            pass
    broad = sys.modules.get("broad_momentum_discovery")
    if broad is not None:
        current = getattr(broad, "_symbol", None)
        if callable(current) and getattr(current, "_yfinance_data_hygiene_version", None) != VERSION:
            prior = current

            def hygienic_symbol(value: Any) -> str:
                symbol = normalize_symbol(prior(value))
                return "" if is_blocked_symbol(symbol) else symbol

            hygienic_symbol._yfinance_data_hygiene_version = VERSION  # type: ignore[attr-defined]
            hygienic_symbol._yfinance_data_hygiene_prior = prior  # type: ignore[attr-defined]
            setattr(broad, "_symbol", hygienic_symbol)
            try:
                cache = getattr(broad, "_CACHE", None)
                if isinstance(cache, dict):
                    cache.clear()
                    cache.update({"ts": 0.0, "payload": None})
            except Exception:
                pass


def install(core: Any = None) -> Dict[str, Any]:
    global _ORIGINAL_DOWNLOAD, _INSTALLED
    _filter_warning()
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": f"yfinance_unavailable:{type(exc).__name__}",
        }

    current = getattr(yf, "download", None)
    if not callable(current):
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "yf_download_missing"}
    if getattr(current, "_yfinance_data_hygiene_version", None) == VERSION:
        _INSTALLED = True
        _patch_runtime_sources(core)
        return status_payload(core)

    original = getattr(current, "_yfinance_data_hygiene_original", current)
    _ORIGINAL_DOWNLOAD = original

    def guarded_download(tickers: Any, *args: Any, **kwargs: Any) -> Any:
        with _LOCK:
            _TOTALS["requests"] += 1
        cleaned, symbols, blocked = sanitize_tickers(tickers)
        if blocked:
            with _LOCK:
                _TOTALS["static_blocks"] += sum(1 for row in blocked if row.get("reason") == "known_no_data_symbol")
                _TOTALS["dynamic_blocks"] += sum(1 for row in blocked if row.get("reason") != "known_no_data_symbol")
            _record_event("blocked_before_provider", [str(row.get("symbol") or "") for row in blocked])
        if not symbols:
            return _empty_frame()

        key = _cache_key(symbols, args, kwargs)
        cached = _cache_get(key)
        if cached is not None:
            return cached

        with _LOCK:
            _TOTALS["provider_calls"] += 1
        try:
            frame = original(cleaned, *args, **kwargs)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failure_type = _classify_error(detail)
            for symbol in symbols:
                _apply_failure(symbol, failure_type, detail)
            _record_event(failure_type, symbols, detail)
            raise

        symbol_errors: Dict[str, str] = {}
        for symbol in symbols:
            text = _provider_error_text(yf, symbol)
            if text:
                symbol_errors[symbol] = text
                _apply_failure(symbol, _classify_error(text), text)

        if _frame_empty(frame):
            for symbol in symbols:
                if symbol not in symbol_errors:
                    _apply_failure(symbol, "empty", "empty yfinance response")
            _record_event("empty", symbols, "; ".join(symbol_errors.values()))
            return frame

        successful = [symbol for symbol in symbols if symbol not in symbol_errors]
        _clear_success(successful)
        with _LOCK:
            _TOTALS["successful_calls"] += 1
        _cache_put(key, frame)
        _record_event("ok", successful or symbols)
        return frame

    guarded_download._yfinance_data_hygiene_version = VERSION  # type: ignore[attr-defined]
    guarded_download._yfinance_data_hygiene_original = original  # type: ignore[attr-defined]
    yf.download = guarded_download
    try:
        if core is not None and getattr(core, "yf", None) is not None:
            core.yf.download = guarded_download
    except Exception:
        pass
    _INSTALLED = True
    _patch_runtime_sources(core)
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    now = time.time()
    with _LOCK:
        active = {
            symbol: {
                "reason": str(row.get("reason") or ""),
                "seconds_remaining": max(0.0, round(float(row.get("blocked_until") or 0.0) - now, 1)),
                "empty_count": int(row.get("empty_count") or 0),
                "timeout_count": int(row.get("timeout_count") or 0),
                "no_data_count": int(row.get("no_data_count") or 0),
                "last_error": str(row.get("last_error") or "")[:300],
            }
            for symbol, row in _SYMBOL_STATE.items()
            if float(row.get("blocked_until") or 0.0) > now
        }
        totals = dict(_TOTALS)
        events = list(_EVENTS[-30:])
        cache_rows = len(_CACHE)
    return {
        "status": "ok" if _INSTALLED else "pending",
        "overall": "pass" if _INSTALLED else "pending",
        "type": "yfinance_data_hygiene_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "installed": _INSTALLED,
        "warning_filter": "yfinance.scrapers.quote Timestamp.utcnow only",
        "known_no_data_symbols": sorted(static_blocked_symbols()),
        "active_symbol_backoffs": active,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cache_rows": cache_rows,
        "totals": totals,
        "recent_events": events,
        "authority": {
            "changes_entry_rules": False,
            "changes_hard_risk": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_sizing": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
        "execution_authority": "existing_rules_only",
        "ml_authority": "shadow_recommendation_only",
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return install(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    path = "/paper/yfinance-data-hygiene-status"
    if path not in existing:
        flask_app.add_url_rule(path, "yfinance_data_hygiene_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core)


try:
    _filter_warning()
    install(None)
except Exception:
    pass
