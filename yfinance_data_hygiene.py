"""Safe yfinance request hygiene for the paper-trading runtime.

Only a small explicit denylist is treated as permanently invalid. Provider
missing-data messages are treated as transient because Yahoo can emit them for
valid symbols and short intraday windows. Repeated failures receive a short,
per-symbol backoff; benchmark ETFs and open positions are never dynamically
blocked. Stale ``yfinance.shared._ERRORS`` entries are cleared before each call.

No trading rule, threshold, sizing, risk control, order path, live authority, or
ML authority is changed.
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

VERSION = "yfinance-data-hygiene-2026-08-06-v2-transient-safe"
CACHE_TTL_SECONDS = max(0.0, float(os.getenv("YFINANCE_DOWNLOAD_CACHE_TTL_SECONDS", "45")))
FAILURE_BACKOFF_THRESHOLD = max(2, int(os.getenv("YFINANCE_FAILURE_BACKOFF_THRESHOLD", "3")))
FAILURE_BACKOFF_SECONDS = max(15, int(os.getenv("YFINANCE_FAILURE_BACKOFF_SECONDS", "45")))
MAX_CACHE_ROWS = max(20, int(os.getenv("YFINANCE_DOWNLOAD_CACHE_MAX_ROWS", "256")))
MAX_EVENTS = max(20, int(os.getenv("YFINANCE_HYGIENE_MAX_EVENTS", "200")))

_DEFAULT_BLOCKED_SYMBOLS = {"RGIT", "CIFRW", "SATS"}
_DEFAULT_PROTECTED_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA"}
_SPLIT_RE = re.compile(r"[\s,]+")
_TIMEOUT_MARKERS = ("timeout", "timed out", "curl: (28)", "resolving timed out")

_LOCK = threading.RLock()
_ORIGINAL_DOWNLOAD: Any = None
_INSTALLED = False
_REGISTERED_APP_IDS: set[int] = set()
_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
_SYMBOL_STATE: Dict[str, Dict[str, Any]] = {}
_PROTECTED_SYMBOLS: set[str] = set(_DEFAULT_PROTECTED_SYMBOLS)
_EVENTS: List[Dict[str, Any]] = []
_TOTALS: Dict[str, int] = {
    "requests": 0,
    "provider_calls": 0,
    "cache_hits": 0,
    "static_blocks": 0,
    "dynamic_blocks": 0,
    "transient_failures": 0,
    "short_backoffs": 0,
    "protected_backoff_prevented": 0,
    "stale_provider_errors_cleared": 0,
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


def _refresh_protected_symbols(core: Any = None) -> set[str]:
    protected = set(_DEFAULT_PROTECTED_SYMBOLS)
    protected.update(_csv_env("YFINANCE_PROTECTED_SYMBOLS", ()))
    if core is not None:
        for source in (getattr(core, "portfolio", None),):
            try:
                positions = source.get("positions") if isinstance(source, dict) else None
                if isinstance(positions, dict):
                    protected.update(normalize_symbol(symbol) for symbol in positions)
            except Exception:
                pass
        try:
            state = core.load_state() if hasattr(core, "load_state") else {}
            positions = state.get("positions") if isinstance(state, dict) else None
            if isinstance(positions, dict):
                protected.update(normalize_symbol(symbol) for symbol in positions)
        except Exception:
            pass
    protected.discard("")
    with _LOCK:
        _PROTECTED_SYMBOLS.clear()
        _PROTECTED_SYMBOLS.update(protected)
        for symbol in list(_SYMBOL_STATE):
            if symbol in protected:
                if float((_SYMBOL_STATE.get(symbol) or {}).get("blocked_until") or 0.0) > time.time():
                    _TOTALS["protected_backoff_prevented"] += 1
                _SYMBOL_STATE.pop(symbol, None)
    return protected


def protected_symbols(core: Any = None) -> set[str]:
    if core is not None:
        return _refresh_protected_symbols(core)
    with _LOCK:
        return set(_PROTECTED_SYMBOLS)


def _active_state(symbol: str, now: float | None = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    with _LOCK:
        row = dict(_SYMBOL_STATE.get(symbol) or {})
    return row if float(row.get("blocked_until") or 0.0) > now else {}


def is_blocked_symbol(symbol: Any) -> bool:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return False
    if normalized in static_blocked_symbols():
        return True
    if normalized in protected_symbols():
        return False
    return bool(_active_state(normalized))


def blocked_reason(symbol: Any) -> str | None:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return "blank_symbol"
    if normalized in static_blocked_symbols():
        return "known_no_data_symbol"
    if normalized in protected_symbols():
        return None
    return str(_active_state(normalized).get("reason") or "") or None


def sanitize_tickers(tickers: Any) -> Tuple[Any, List[str], List[Dict[str, Any]]]:
    requested = _requested_symbols(tickers)
    allowed: List[str] = []
    blocked: List[Dict[str, Any]] = []
    static = static_blocked_symbols()
    protected = protected_symbols()
    now = time.time()
    for symbol in requested:
        if symbol in static:
            blocked.append({"symbol": symbol, "reason": "known_no_data_symbol"})
            continue
        state = _active_state(symbol, now)
        if state and symbol not in protected:
            blocked.append({"symbol": symbol, "reason": str(state.get("reason") or "short_retry_backoff"), "blocked_until": state.get("blocked_until")})
            continue
        allowed.append(symbol)
    return _rebuild_tickers(tickers, allowed), allowed, blocked


def _frame_empty(frame: Any) -> bool:
    return frame is None or bool(getattr(frame, "empty", True))


def _copy_frame(frame: Any) -> Any:
    try:
        return frame.copy(deep=True)
    except Exception:
        try:
            return frame.copy()
        except Exception:
            return frame


def _empty_frame() -> Any:
    try:
        import pandas as pd  # type: ignore
        return pd.DataFrame()
    except Exception:
        return None


def _cache_key(symbols: Sequence[str], args: Sequence[Any], kwargs: Dict[str, Any]) -> Tuple[Any, ...]:
    relevant = tuple(repr(kwargs.get(key)) for key in ("period", "interval", "start", "end", "prepost", "auto_adjust", "actions", "repair", "group_by"))
    return tuple(symbols), tuple(repr(value) for value in args), relevant


def _cache_get(key: Tuple[Any, ...]) -> Any:
    if CACHE_TTL_SECONDS <= 0:
        return None
    with _LOCK:
        row = _CACHE.get(key)
        if not row or time.time() - float(row.get("ts") or 0.0) > CACHE_TTL_SECONDS:
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
            oldest = sorted(_CACHE, key=lambda item: float((_CACHE.get(item) or {}).get("ts") or 0.0))
            for stale in oldest[: len(_CACHE) - MAX_CACHE_ROWS]:
                _CACHE.pop(stale, None)


def _record_event(status: str, symbols: Sequence[str], detail: str = "") -> None:
    row: Dict[str, Any] = {"generated_local": _now_text(), "status": status, "symbols": list(symbols)}
    if detail:
        row["detail"] = detail[:500]
    with _LOCK:
        _EVENTS.append(row)
        del _EVENTS[:-MAX_EVENTS]


def _shared_errors(yf_module: Any) -> Dict[str, Any] | None:
    try:
        shared = getattr(yf_module, "shared", None) or sys.modules.get("yfinance.shared")
        errors = getattr(shared, "_ERRORS", None)
        return errors if isinstance(errors, dict) else None
    except Exception:
        return None


def _clear_provider_errors(yf_module: Any, symbols: Sequence[str]) -> None:
    errors = _shared_errors(yf_module)
    if errors is None:
        return
    wanted = {normalize_symbol(symbol) for symbol in symbols}
    removed = 0
    for key in list(errors):
        if normalize_symbol(key) in wanted:
            errors.pop(key, None)
            removed += 1
    if removed:
        with _LOCK:
            _TOTALS["stale_provider_errors_cleared"] += removed


def _provider_errors(yf_module: Any, symbols: Sequence[str]) -> Dict[str, str]:
    errors = _shared_errors(yf_module) or {}
    wanted = {normalize_symbol(symbol) for symbol in symbols}
    return {normalize_symbol(key): str(value or "") for key, value in list(errors.items()) if normalize_symbol(key) in wanted}


def _failure_kind(detail: str) -> str:
    lowered = str(detail or "").lower()
    return "timeout" if any(marker in lowered for marker in _TIMEOUT_MARKERS) else "missing_or_empty"


def _apply_failure(symbol: str, failure_type: str, detail: str = "", *args: Any, **kwargs: Any) -> None:
    symbol = normalize_symbol(symbol)
    if not symbol:
        return
    protected = symbol in protected_symbols()
    with _LOCK:
        _TOTALS["transient_failures"] += 1
        row = dict(_SYMBOL_STATE.get(symbol) or {})
        count = int(row.get("failure_count") or 0) + 1
        row.update({"failure_count": count, "last_failure_type": failure_type, "last_error": detail[:500], "updated_ts": time.time()})
        if protected:
            row.pop("blocked_until", None)
            row.pop("reason", None)
            _TOTALS["protected_backoff_prevented"] += 1
        elif count >= FAILURE_BACKOFF_THRESHOLD:
            row.update({"reason": "short_retry_backoff", "blocked_until": time.time() + FAILURE_BACKOFF_SECONDS})
            _TOTALS["short_backoffs"] += 1
        _SYMBOL_STATE[symbol] = row


def _clear_success(symbols: Sequence[str]) -> None:
    with _LOCK:
        for symbol in symbols:
            _SYMBOL_STATE.pop(normalize_symbol(symbol), None)


def _symbol_has_data(frame: Any, symbol: str, symbols: Sequence[str]) -> bool:
    if _frame_empty(frame):
        return False
    if len(symbols) == 1:
        return True
    try:
        columns = getattr(frame, "columns", None)
        if int(getattr(columns, "nlevels", 1)) > 1:
            for level in range(int(columns.nlevels)):
                values = {normalize_symbol(value) for value in columns.get_level_values(level)}
                if symbol in values:
                    subset = frame.xs(symbol, axis=1, level=level, drop_level=False)
                    return not bool(subset.dropna(how="all").empty)
    except Exception:
        pass
    return True


def _filter_warning() -> None:
    warnings.filterwarnings("ignore", message=r".*Timestamp\.utcnow is deprecated.*", category=Warning, module=r"yfinance\.scrapers\.quote")


def _patch_runtime_sources(core: Any = None) -> None:
    _refresh_protected_symbols(core)
    static = static_blocked_symbols()
    if core is not None:
        try:
            universe = list(getattr(core, "UNIVERSE", []) or [])
            core.UNIVERSE = [symbol for symbol in universe if normalize_symbol(symbol) not in static]
        except Exception:
            pass
    broad = sys.modules.get("broad_momentum_discovery")
    if broad is not None:
        current = getattr(broad, "_symbol", None)
        if callable(current) and getattr(current, "_yfinance_data_hygiene_version", None) != VERSION:
            prior = getattr(current, "_yfinance_data_hygiene_prior", current)
            def hygienic_symbol(value: Any) -> str:
                symbol = normalize_symbol(prior(value))
                return "" if symbol in static_blocked_symbols() else symbol
            hygienic_symbol._yfinance_data_hygiene_version = VERSION  # type: ignore[attr-defined]
            hygienic_symbol._yfinance_data_hygiene_prior = prior  # type: ignore[attr-defined]
            broad._symbol = hygienic_symbol


def install(core: Any = None) -> Dict[str, Any]:
    global _ORIGINAL_DOWNLOAD, _INSTALLED
    _filter_warning()
    _refresh_protected_symbols(core)
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": f"yfinance_unavailable:{type(exc).__name__}"}
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
        _refresh_protected_symbols(core)
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
        _clear_provider_errors(yf, symbols)
        with _LOCK:
            _TOTALS["provider_calls"] += 1
        try:
            frame = original(cleaned, *args, **kwargs)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            for symbol in symbols:
                _apply_failure(symbol, _failure_kind(detail), detail)
            _record_event("provider_exception", symbols, detail)
            raise
        errors = _provider_errors(yf, symbols)
        successes = [symbol for symbol in symbols if _symbol_has_data(frame, symbol, symbols)]
        _clear_success(successes)
        failed = [symbol for symbol in symbols if symbol not in successes]
        for symbol in failed:
            detail = errors.get(symbol) or "empty yfinance response"
            _apply_failure(symbol, _failure_kind(detail), detail)
        if _frame_empty(frame):
            _record_event("empty", symbols, "; ".join(errors.values()))
            return frame
        with _LOCK:
            _TOTALS["successful_calls"] += 1
        _cache_put(key, frame)
        _record_event("ok" if not failed else "partial_ok", successes or symbols, "; ".join(errors.values()))
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
    protected = _refresh_protected_symbols(core)
    now = time.time()
    with _LOCK:
        active = {
            symbol: {
                "reason": str(row.get("reason") or ""),
                "seconds_remaining": max(0.0, round(float(row.get("blocked_until") or 0.0) - now, 1)),
                "failure_count": int(row.get("failure_count") or 0),
                "last_failure_type": row.get("last_failure_type"),
                "last_error": str(row.get("last_error") or "")[:300],
            }
            for symbol, row in _SYMBOL_STATE.items()
            if float(row.get("blocked_until") or 0.0) > now and symbol not in protected
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
        "known_no_data_symbols": sorted(static_blocked_symbols()),
        "protected_symbols": sorted(protected),
        "protected_symbol_blocks": [],
        "active_symbol_backoffs": active,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cache_rows": cache_rows,
        "totals": totals,
        "recent_events": events,
        "regression_guards": {
            "stale_shared_errors_cleared_before_each_call": True,
            "provider_missing_data_is_transient": True,
            "no_dynamic_hard_delisting_quarantine": True,
            "benchmarks_and_open_positions_never_dynamically_blocked": True,
            "success_clears_symbol_failure_state": True,
        },
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
    if "/paper/yfinance-data-hygiene-status" not in existing:
        flask_app.add_url_rule("/paper/yfinance-data-hygiene-status", "yfinance_data_hygiene_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core)


try:
    _filter_warning()
    install(None)
except Exception:
    pass
