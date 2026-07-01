"""Symbol hygiene guard for scanner/dynamic-universe inputs.

Prevents state words, action labels, dates, and known no-data instruments from
leaking into yfinance downloads or the active scanner universe. This is a
paper-safe diagnostic/runtime hygiene layer only: it does not place trades,
lower thresholds, bypass risk controls, or change ML/live authority.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from typing import Any, Dict, Iterable, List

VERSION = "symbol-hygiene-guard-2026-07-01-v1-invalid-token-filter"
REGISTERED_APP_IDS: set[int] = set()
_PATCHED_CORE_IDS: set[int] = set()
_PATCHED_DYNAMIC_IDS: set[int] = set()
_ORIGINALS: Dict[int, Dict[str, Any]] = {}
_LAST_STATUS: Dict[str, Any] = {}

# Words that can appear in logs/state/decision rows but are not ticker symbols.
DEFAULT_RESERVED_WORDS = {
    "LONG", "SHORT", "AUTO", "MANUAL", "BEARISH", "BULLISH", "CLEAR", "CLEAN", "RUN", "RUNNING",
    "PASS", "FAIL", "WARN", "ERROR", "OK", "OPEN", "CLOSE", "CLOSED", "ENTRY", "EXIT", "BUY", "SELL",
    "HOLD", "HELD", "CASH", "EQUITY", "POSITION", "POSITIONS", "TRADE", "TRADES", "SIGNAL", "SIGNALS",
    "BLOCKED", "REJECTED", "CANDIDATE", "CANDIDATES", "TODAY", "YESTERDAY", "TOMORROW", "DATE",
    "TRUE", "FALSE", "NONE", "NULL", "NAN", "INF", "LOSS", "WIN", "RISK", "QUALITY", "SCORE",
}

# Instruments from current Railway logs that Yahoo commonly reports as no-data
# in this deployment. Override with SYMBOL_HYGIENE_KNOWN_NO_DATA_SYMBOLS if needed.
DEFAULT_KNOWN_NO_DATA = {"CIFRW", "SATS"}

_ALLOWED_SPECIALS = {"^VIX", "^TNX", "ES=F", "NQ=F"}
_SYMBOL_RE = re.compile(r"^[A-Z]{1,6}([.-][A-Z])?$")
_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}$")
_NUMERIC_RE = re.compile(r"^\d+(\.\d+)?$")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _csv_env(name: str, default: Iterable[str]) -> set[str]:
    raw = os.environ.get(name)
    if raw is None:
        return {str(x).upper().strip() for x in default if str(x).strip()}
    return {str(x).upper().strip() for x in raw.split(",") if str(x).strip()}


def reserved_words() -> set[str]:
    return _csv_env("SYMBOL_HYGIENE_RESERVED_WORDS", DEFAULT_RESERVED_WORDS)


def known_no_data_symbols() -> set[str]:
    return _csv_env("SYMBOL_HYGIENE_KNOWN_NO_DATA_SYMBOLS", DEFAULT_KNOWN_NO_DATA)


def normalize_symbol(value: Any) -> str:
    try:
        symbol = str(value or "").strip().upper()
        if symbol.startswith("$"):
            symbol = symbol[1:]
        return symbol
    except Exception:
        return ""


def invalid_reason(value: Any) -> str | None:
    symbol = normalize_symbol(value)
    if not symbol:
        return "blank_symbol"
    if symbol in _ALLOWED_SPECIALS:
        return None
    if symbol in reserved_words():
        return "reserved_word_not_ticker"
    if symbol in known_no_data_symbols():
        return "known_yfinance_no_data_symbol"
    if _DATE_RE.match(symbol):
        return "date_token_not_ticker"
    if _NUMERIC_RE.match(symbol):
        return "numeric_token_not_ticker"
    if any(ch.isspace() for ch in symbol) or "," in symbol or ":" in symbol or "/" in symbol:
        return "contains_non_ticker_separator"
    if symbol.endswith("W") and len(symbol) >= 5:
        return "probable_warrant_symbol"
    if not _SYMBOL_RE.match(symbol):
        return "ticker_format_rejected"
    return None


def is_valid_symbol(value: Any) -> bool:
    return invalid_reason(value) is None


def filter_symbols(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        symbol = normalize_symbol(value)
        if symbol and symbol not in seen and is_valid_symbol(symbol):
            seen.add(symbol)
            out.append(symbol)
    return out


def rejected_symbols(values: Iterable[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for value in values or []:
        symbol = normalize_symbol(value)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        reason = invalid_reason(symbol)
        if reason:
            rows.append({"symbol": symbol, "reason": reason})
    return rows[:100]


def _patch_core(core: Any) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "reason": "core_not_ready"}
    core_id = id(core)
    original_bucket: Dict[str, Any] = _ORIGINALS.setdefault(core_id, {})

    original_universe = list(getattr(core, "UNIVERSE", []) or [])
    cleaned_universe = filter_symbols(original_universe)
    removed = rejected_symbols(original_universe)
    try:
        setattr(core, "UNIVERSE", cleaned_universe)
    except Exception:
        pass

    if core_id not in _PATCHED_CORE_IDS:
        download_prices = getattr(core, "download_prices", None)
        if callable(download_prices):
            original_bucket["download_prices"] = download_prices

            def safe_download_prices(symbol: Any, period: str = "5d", interval: str = "5m"):
                if isinstance(symbol, (list, tuple, set)):
                    clean_list = filter_symbols(symbol)
                    if not clean_list:
                        return None
                    return download_prices(clean_list, period=period, interval=interval)
                cleaned = normalize_symbol(symbol)
                if not is_valid_symbol(cleaned):
                    return None
                return download_prices(cleaned, period=period, interval=interval)

            safe_download_prices._symbol_hygiene_guard_version = VERSION  # type: ignore[attr-defined]
            setattr(core, "download_prices", safe_download_prices)

        fetch_intraday = getattr(core, "fetch_intraday", None)
        if callable(fetch_intraday):
            original_bucket["fetch_intraday"] = fetch_intraday

            def safe_fetch_intraday(symbol: Any):
                cleaned = normalize_symbol(symbol)
                if not is_valid_symbol(cleaned):
                    return None
                return fetch_intraday(cleaned)

            safe_fetch_intraday._symbol_hygiene_guard_version = VERSION  # type: ignore[attr-defined]
            setattr(core, "fetch_intraday", safe_fetch_intraday)

        latest_price = getattr(core, "latest_price", None)
        if callable(latest_price):
            original_bucket["latest_price"] = latest_price

            def safe_latest_price(symbol: Any):
                cleaned = normalize_symbol(symbol)
                if not is_valid_symbol(cleaned):
                    return None
                return latest_price(cleaned)

            safe_latest_price._symbol_hygiene_guard_version = VERSION  # type: ignore[attr-defined]
            setattr(core, "latest_price", safe_latest_price)

        _PATCHED_CORE_IDS.add(core_id)

    return {
        "status": "ok",
        "core_patched": core_id in _PATCHED_CORE_IDS,
        "universe_before": len(original_universe),
        "universe_after": len(cleaned_universe),
        "removed_from_core_universe": removed,
    }


def _patch_dynamic_builder(core: Any = None) -> Dict[str, Any]:
    try:
        import dynamic_universe_builder as dub
    except Exception as exc:
        return {"dynamic_builder_patched": False, "reason": f"dynamic_universe_builder_unavailable:{type(exc).__name__}"}

    module_id = id(dub)
    removed_by_bucket: Dict[str, List[Dict[str, Any]]] = {}
    try:
        baskets = getattr(dub, "THEME_BASKETS", {})
        if isinstance(baskets, dict):
            for bucket, members in list(baskets.items()):
                before = list(members or [])
                after = filter_symbols(before)
                removed = rejected_symbols(before)
                if removed:
                    removed_by_bucket[str(bucket)] = removed
                baskets[bucket] = after
    except Exception:
        pass

    if module_id not in _PATCHED_DYNAMIC_IDS:
        def safe_symbol(value: Any) -> str:
            symbol = normalize_symbol(value)
            return symbol if is_valid_symbol(symbol) else ""

        def safe_unique(seq: Iterable[Any]) -> List[str]:
            return filter_symbols(seq)

        dub._symbol = safe_symbol  # type: ignore[attr-defined]
        dub._unique = safe_unique  # type: ignore[attr-defined]

        original_download_daily = getattr(dub, "_download_daily", None)
        if callable(original_download_daily):
            def safe_download_daily(seeds: Iterable[Any]):
                clean_seeds = filter_symbols(seeds)
                if not clean_seeds:
                    return None, "no_valid_symbols_after_hygiene_filter"
                return original_download_daily(clean_seeds)
            safe_download_daily._symbol_hygiene_guard_version = VERSION  # type: ignore[attr-defined]
            dub._download_daily = safe_download_daily  # type: ignore[attr-defined]

        _PATCHED_DYNAMIC_IDS.add(module_id)

    # Clear cached dynamic-universe payload so the next run uses the cleaned seed list.
    try:
        cache = getattr(dub, "_CACHE", None)
        if isinstance(cache, dict):
            cache.clear()
            cache.update({"ts": 0.0, "payload": None})
    except Exception:
        pass

    return {
        "dynamic_builder_patched": module_id in _PATCHED_DYNAMIC_IDS,
        "removed_from_theme_baskets": removed_by_bucket,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST_STATUS
    core = core or _mod()
    core_status = _patch_core(core)
    dynamic_status = _patch_dynamic_builder(core)
    _LAST_STATUS = {
        "status": "ok",
        "overall": "pass",
        "type": "symbol_hygiene_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "does_not_place_trades": True,
        "does_not_lower_thresholds": True,
        "does_not_bypass_risk_controls": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "filters": {
            "reserved_words_count": len(reserved_words()),
            "known_no_data_symbols": sorted(known_no_data_symbols()),
            "allowed_special_symbols": sorted(_ALLOWED_SPECIALS),
        },
        **core_status,
        **dynamic_status,
    }
    return dict(_LAST_STATUS)


def status_payload(core: Any = None) -> Dict[str, Any]:
    if not _LAST_STATUS:
        return apply(core or _mod())
    payload = dict(_LAST_STATUS)
    payload["generated_local"] = _now(core or _mod())
    return payload


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/symbol-hygiene-guard-status" not in existing:
        flask_app.add_url_rule(
            "/paper/symbol-hygiene-guard-status",
            "symbol_hygiene_guard_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
