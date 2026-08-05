"""Paper-only broad-market momentum discovery with bounded scanner ownership.

This module discovers liquid U.S. momentum leaders from market-wide Yahoo/yfinance
screens, installs a bounded working universe, and leaves all trade decisions to
the existing rules engine. Version 2 adds scanner-boundary enforcement, source
attribution integrity, non-blocking sector enrichment, and ownership telemetry.
"""
from __future__ import annotations

import datetime as dt
import functools
import math
import os
import sys
import threading
import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VERSION = "broad-momentum-discovery-2026-08-05-v2-integrity"
ENABLED = os.environ.get("BROAD_MOMENTUM_DISCOVERY_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
PAPER_ONLY = os.environ.get("BROAD_MOMENTUM_DISCOVERY_PAPER_ONLY", "true").lower() not in {
    "0", "false", "no", "off"
}
CACHE_TTL_SECONDS = int(os.environ.get("BROAD_MOMENTUM_CACHE_TTL_SECONDS", "900"))
REFRESH_WAIT_SECONDS = float(os.environ.get("BROAD_MOMENTUM_REFRESH_WAIT_SECONDS", "7"))
MAX_DISCOVERY_SYMBOLS = int(os.environ.get("BROAD_MOMENTUM_MAX_DISCOVERY_SYMBOLS", "160"))
MAX_FINAL_UNIVERSE = int(os.environ.get("BROAD_MOMENTUM_MAX_FINAL_UNIVERSE", "110"))
MAX_BROAD_SLOTS = int(os.environ.get("BROAD_MOMENTUM_MAX_BROAD_SLOTS", "80"))
MAX_BASE_SLOTS = int(os.environ.get("BROAD_MOMENTUM_MAX_BASE_SLOTS", "25"))
MIN_PRICE = float(os.environ.get("BROAD_MOMENTUM_MIN_PRICE", "3.00"))
MIN_DAY_VOLUME = float(os.environ.get("BROAD_MOMENTUM_MIN_DAY_VOLUME", "350000"))
MIN_DOLLAR_VOLUME = float(os.environ.get("BROAD_MOMENTUM_MIN_DOLLAR_VOLUME", "10000000"))
MIN_MARKET_CAP = float(os.environ.get("BROAD_MOMENTUM_MIN_MARKET_CAP", "100000000"))
CUSTOM_SCREEN_SIZE = int(os.environ.get("BROAD_MOMENTUM_CUSTOM_SCREEN_SIZE", "250"))
PREDEFINED_SCREEN_COUNT = int(os.environ.get("BROAD_MOMENTUM_PREDEFINED_COUNT", "100"))
WATCHDOG_SECONDS = int(os.environ.get("BROAD_MOMENTUM_WATCHDOG_SECONDS", "10"))
SECTOR_ENRICH_PER_REFRESH = int(os.environ.get("BROAD_MOMENTUM_SECTOR_ENRICH_PER_REFRESH", "12"))
SECTOR_CACHE_TTL_SECONDS = int(
    os.environ.get("BROAD_MOMENTUM_SECTOR_CACHE_TTL_SECONDS", str(7 * 24 * 3600))
)

BENCHMARK_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
SECTOR_ETF = {
    "basic materials": "XLB",
    "materials": "XLB",
    "communication services": "XLC",
    "consumer cyclical": "XLY",
    "consumer discretionary": "XLY",
    "consumer defensive": "XLP",
    "consumer staples": "XLP",
    "energy": "XLE",
    "financial services": "XLF",
    "financial": "XLF",
    "healthcare": "XLV",
    "health care": "XLV",
    "industrials": "XLI",
    "real estate": "XLRE",
    "technology": "XLK",
    "utilities": "XLU",
}
DYNAMIC_BUCKET = "dynamic_momentum"
DYNAMIC_BUCKET_CONFIG = {"alloc_factor": 0.40, "max_exposure_pct": 0.20, "max_positions": 3}

_LOCK = threading.RLock()
_REFRESH_EVENT = threading.Event()
_REFRESH_THREAD: threading.Thread | None = None
_SECTOR_THREAD: threading.Thread | None = None
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_SECTOR_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST: Dict[str, Any] = {}
_BASE_UNIVERSE: Dict[int, List[str]] = {}
_REGISTERED_APP_IDS: set[int] = set()
_WATCHDOG_CORE_IDS: set[int] = set()

_OWNER_MODULE_HINTS = (
    "neutral_momentum_starter_extension",
    "opening_surge_participation",
    "dynamic_universe_builder",
    "scanner_v2_shadow_universe",
    "space_stock_basket",
    "spacex_direct_overlay",
    "breakout_participation_layer",
)
_OWNER_ATTR_HINTS = (
    "_EXTRA_SYMBOLS",
    "EXTRA",
    "EXTRA_SYMBOLS",
    "PREFERRED_SYMBOLS",
    "UNIVERSE",
    "THEME_SYMBOLS",
    "SYMBOLS",
)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, dict) and "raw" in value:
            value = value.get("raw")
        if hasattr(value, "item"):
            value = value.item()
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _symbol(value: Any) -> str:
    raw = str(value or "").upper().strip().lstrip("$")
    clean = raw.replace(".", "").replace("-", "")
    return raw if raw and len(raw) <= 10 and clean.isalnum() else ""


def _unique(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        symbol = _symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def _unique_labels(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        label = str(value or "").strip()
        if label and label not in seen:
            seen.add(label)
            output.append(label)
    return output


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _module() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    return None


def _quote_value(quote: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in quote and quote.get(key) is not None:
            value = quote.get(key)
            return value.get("raw") if isinstance(value, dict) and "raw" in value else value
    return None


def _normalize_sector(value: Any) -> str:
    return str(value or "").strip()


def _sector_proxy(value: Any) -> str | None:
    return SECTOR_ETF.get(_normalize_sector(value).lower())


def _normalize_quote(quote: Dict[str, Any], source: str) -> Dict[str, Any] | None:
    if not isinstance(quote, dict):
        return None
    symbol = _symbol(_quote_value(quote, "symbol", "ticker"))
    if not symbol:
        return None
    price = _f(_quote_value(quote, "regularMarketPrice", "intradayprice", "regularMarketPreviousClose"))
    pct = _f(_quote_value(quote, "regularMarketChangePercent", "percentchange"))
    volume = _f(_quote_value(quote, "regularMarketVolume", "dayvolume", "eodvolume"))
    avg_volume = _f(_quote_value(quote, "averageDailyVolume3Month", "avgdailyvol3m", "averageDailyVolume10Day"))
    market_cap = _f(_quote_value(quote, "marketCap", "intradaymarketcap"))
    dollar_volume = max(0.0, price * volume)
    relative_volume = volume / avg_volume if avg_volume > 0 else 0.0
    sector = _normalize_sector(_quote_value(quote, "sector", "sectorName", "sectorDisp"))
    industry = str(_quote_value(quote, "industry", "industryName", "industryDisp") or "").strip()
    return {
        "symbol": symbol,
        "source": source,
        "sources": [source],
        "price": round(price, 4),
        "percent_change": round(pct, 4),
        "day_volume": int(volume) if volume > 0 else 0,
        "avg_volume_3m": int(avg_volume) if avg_volume > 0 else 0,
        "relative_volume": round(relative_volume, 4),
        "dollar_volume": round(dollar_volume, 2),
        "market_cap": round(market_cap, 2),
        "sector_name": sector,
        "industry_name": industry,
        "sector_proxy": _sector_proxy(sector),
        "classification_source": "screen_payload" if sector else None,
    }


def _eligible(row: Dict[str, Any]) -> Tuple[bool, str]:
    if _f(row.get("price")) < MIN_PRICE:
        return False, "price_below_floor"
    if _f(row.get("day_volume")) < MIN_DAY_VOLUME:
        return False, "day_volume_below_floor"
    if _f(row.get("dollar_volume")) < MIN_DOLLAR_VOLUME:
        return False, "dollar_volume_below_floor"
    market_cap = _f(row.get("market_cap"))
    if market_cap > 0 and market_cap < MIN_MARKET_CAP:
        return False, "market_cap_below_floor"
    return True, "liquid_market_wide_candidate"


def _discovery_score(row: Dict[str, Any]) -> float:
    pct = _f(row.get("percent_change"))
    relvol = _f(row.get("relative_volume"))
    dollar_volume = _f(row.get("dollar_volume"))
    market_cap = _f(row.get("market_cap"))
    score = 0.0
    score += max(-0.08, min(pct, 20.0) / 32.0)
    score += max(0.0, min(relvol - 1.0, 5.0)) / 10.0
    score += min(max(dollar_volume, 0.0), 500_000_000.0) / 2_500_000_000.0
    if market_cap >= 2_000_000_000:
        score += 0.035
    elif market_cap >= 500_000_000:
        score += 0.020
    return round(score, 6)


def _response_quotes(response: Any) -> List[Dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    candidates = response.get("quotes")
    if not isinstance(candidates, list):
        finance = response.get("finance")
        if isinstance(finance, dict):
            results = finance.get("result")
            if isinstance(results, list) and results:
                candidates = results[0].get("quotes") if isinstance(results[0], dict) else []
    return [row for row in candidates or [] if isinstance(row, dict)]


def _predefined_screen(yf: Any, name: str) -> Any:
    try:
        return yf.screen(name, count=PREDEFINED_SCREEN_COUNT)
    except TypeError:
        return yf.screen(name, size=PREDEFINED_SCREEN_COUNT)


def _screen_calls() -> List[Tuple[str, Any]]:
    import yfinance as yf  # type: ignore

    calls: List[Tuple[str, Any]] = []
    for name in ("day_gainers", "most_actives"):
        try:
            calls.append((name, _predefined_screen(yf, name)))
        except Exception as exc:
            calls.append((name, {"_error": f"{type(exc).__name__}: {exc}"}))
    try:
        EquityQuery = getattr(yf, "EquityQuery")
        query = EquityQuery(
            "and",
            [
                EquityQuery("eq", ["region", "us"]),
                EquityQuery("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
                EquityQuery("gte", ["intradayprice", MIN_PRICE]),
                EquityQuery("gte", ["dayvolume", MIN_DAY_VOLUME]),
                EquityQuery("gte", ["intradaymarketcap", MIN_MARKET_CAP]),
                EquityQuery("gte", ["percentchange", 0.50]),
            ],
        )
        calls.append(
            (
                "market_wide_momentum",
                yf.screen(query, size=CUSTOM_SCREEN_SIZE, sortField="percentchange", sortAsc=False),
            )
        )
    except Exception as exc:
        calls.append(("market_wide_momentum", {"_error": f"{type(exc).__name__}: {exc}"}))
    return calls


def _cached_classification(symbol: str) -> Dict[str, Any]:
    with _LOCK:
        row = dict(_SECTOR_CACHE.get(symbol) or {})
    age = time.time() - _f(row.get("ts")) if row else float("inf")
    return row if row and age <= SECTOR_CACHE_TTL_SECONDS else {}


def _merge_classification(row: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    if row.get("sector_proxy"):
        return row
    cached = _cached_classification(symbol)
    if cached:
        row["sector_name"] = cached.get("sector_name") or row.get("sector_name") or ""
        row["industry_name"] = cached.get("industry_name") or row.get("industry_name") or ""
        row["sector_proxy"] = cached.get("sector_proxy") or _sector_proxy(row.get("sector_name"))
        row["classification_source"] = cached.get("classification_source") or "yfinance_profile_cache"
        return row
    try:
        existing = (getattr(core, "SYMBOL_SECTOR", {}) or {}).get(symbol)
    except Exception:
        existing = None
    if existing:
        value = str(existing)
        if value.upper().startswith("XL"):
            row["sector_proxy"] = value.upper()
            row["classification_source"] = "existing_runtime_sector_map"
        else:
            row["sector_name"] = value
            row["sector_proxy"] = _sector_proxy(value)
            row["classification_source"] = "existing_runtime_sector_map"
    return row


def _build_payload(core: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    rows_by_symbol: Dict[str, Dict[str, Any]] = {}
    source_counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    try:
        calls = _screen_calls()
    except Exception as exc:
        calls = []
        errors["screen_bootstrap"] = f"{type(exc).__name__}: {exc}"

    for source, response in calls:
        if isinstance(response, dict) and response.get("_error"):
            errors[source] = str(response.get("_error"))
            continue
        quotes = _response_quotes(response)
        source_counts[source] = len(quotes)
        for quote in quotes:
            row = _normalize_quote(quote, source)
            if not row:
                continue
            ok, reason = _eligible(row)
            row["eligible"] = ok
            row["eligibility_reason"] = reason
            if not ok:
                continue
            symbol = str(row["symbol"])
            existing = rows_by_symbol.get(symbol)
            if existing is None:
                rows_by_symbol[symbol] = row
                continue
            sources = _unique_labels(list(existing.get("sources") or []) + list(row.get("sources") or []) + [source])
            keep_new = _f(row.get("day_volume")) >= _f(existing.get("day_volume"))
            winner = row if keep_new else existing
            loser = existing if keep_new else row
            winner["sources"] = sources
            winner["source"] = str(winner.get("source") or source)
            for key in ("sector_name", "industry_name", "sector_proxy", "classification_source"):
                if not winner.get(key) and loser.get(key):
                    winner[key] = loser.get(key)
            rows_by_symbol[symbol] = winner

    rows = [_merge_classification(dict(row), core) for row in rows_by_symbol.values()]
    for row in rows:
        source_confirmation = min(0.06, 0.02 * max(0, len(row.get("sources") or []) - 1))
        row["source_confirmation_bonus"] = round(source_confirmation, 6)
        row["discovery_score"] = round(_discovery_score(row) + source_confirmation, 6)
    rows.sort(
        key=lambda row: (
            _f(row.get("discovery_score")),
            _f(row.get("percent_change")),
            _f(row.get("relative_volume")),
            _f(row.get("dollar_volume")),
        ),
        reverse=True,
    )
    selected = rows[:MAX_DISCOVERY_SYMBOLS]
    classified = sum(1 for row in selected if row.get("sector_proxy"))
    return {
        "status": "ok" if selected else "warn",
        "overall": "pass" if selected else "warn",
        "type": "broad_momentum_discovery_status",
        "version": VERSION,
        "generated_local": _now(core),
        "duration_seconds": round(time.perf_counter() - started, 4),
        "mode": "paper_only_market_wide_prefilter",
        "source_counts": source_counts,
        "source_errors": errors,
        "eligible_unique_count": len(rows),
        "selected_count": len(selected),
        "selected_symbols": [row["symbol"] for row in selected],
        "candidates": selected,
        "top_candidates": selected[:50],
        "classification": {
            "classified_count": classified,
            "unclassified_count": max(0, len(selected) - classified),
            "coverage_pct": round(100.0 * classified / len(selected), 2) if selected else 0.0,
            "enrichment_non_blocking": True,
        },
        "policy": {
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "max_discovery_symbols": MAX_DISCOVERY_SYMBOLS,
            "max_final_universe": MAX_FINAL_UNIVERSE,
            "max_broad_slots": MAX_BROAD_SLOTS,
            "max_base_slots": MAX_BASE_SLOTS,
            "min_price": MIN_PRICE,
            "min_day_volume": MIN_DAY_VOLUME,
            "min_dollar_volume": MIN_DOLLAR_VOLUME,
            "min_market_cap": MIN_MARKET_CAP,
            "benchmark_symbols": list(BENCHMARK_SYMBOLS),
            "theme_baskets_are_fallback_and_classification": True,
            "scanner_boundary_enforced": True,
        },
        "authority": _authority(),
    }


def _authority() -> Dict[str, Any]:
    return {
        "places_orders": False,
        "changes_entry_rules": False,
        "changes_hard_risk": False,
        "changes_sizing": False,
        "changes_ml_authority": False,
        "changes_live_authority": False,
        "execution_authority": "existing_rules_only",
        "ml_authority": "shadow_recommendation_only",
    }


def _refresh_worker(core: Any = None) -> None:
    global _LAST
    try:
        payload = _build_payload(core)
    except Exception as exc:
        payload = {
            "status": "error",
            "overall": "warn",
            "type": "broad_momentum_discovery_status",
            "version": VERSION,
            "generated_local": _now(core),
            "error": f"{type(exc).__name__}: {exc}",
            "selected_symbols": [],
            "candidates": [],
            "top_candidates": [],
            "authority": _authority(),
        }
    with _LOCK:
        _CACHE.update({"ts": time.time(), "payload": payload})
        _LAST = dict(payload)
        _REFRESH_EVENT.set()


def discover(core: Any = None, force: bool = False, wait: bool = True) -> Dict[str, Any]:
    global _REFRESH_THREAD
    now = time.time()
    with _LOCK:
        cached = _CACHE.get("payload")
        age = now - float(_CACHE.get("ts", 0.0) or 0.0)
        if not force and isinstance(cached, dict) and age < CACHE_TTL_SECONDS:
            result = dict(cached)
            result["cache_hit"] = True
            result["cache_age_seconds"] = round(max(0.0, age), 2)
            return result
        if _REFRESH_THREAD is None or not _REFRESH_THREAD.is_alive():
            _REFRESH_EVENT.clear()
            _REFRESH_THREAD = threading.Thread(
                target=_refresh_worker,
                args=(core,),
                name="broad-momentum-discovery-refresh",
                daemon=True,
            )
            _REFRESH_THREAD.start()
        thread_alive = _REFRESH_THREAD.is_alive()

    completed = _REFRESH_EVENT.wait(max(0.0, REFRESH_WAIT_SECONDS)) if wait else False
    with _LOCK:
        cached = _CACHE.get("payload")
        age = time.time() - float(_CACHE.get("ts", 0.0) or 0.0)
        if isinstance(cached, dict):
            result = dict(cached)
            result["cache_hit"] = not completed
            result["cache_age_seconds"] = round(max(0.0, age), 2)
            result["refresh_in_progress"] = bool(_REFRESH_THREAD and _REFRESH_THREAD.is_alive())
            return result
    return {
        "status": "pending" if thread_alive else "warn",
        "overall": "pending" if thread_alive else "warn",
        "type": "broad_momentum_discovery_status",
        "version": VERSION,
        "generated_local": _now(core),
        "reason": "initial_refresh_in_progress" if thread_alive else "no_discovery_payload",
        "refresh_in_progress": thread_alive,
        "selected_symbols": [],
        "candidates": [],
        "top_candidates": [],
        "authority": _authority(),
    }


def _positions(core: Any) -> List[str]:
    try:
        return _unique((getattr(core, "portfolio", {}) or {}).get("positions", {}).keys())
    except Exception:
        return []


def _base_universe(core: Any) -> List[str]:
    key = id(core)
    if key not in _BASE_UNIVERSE:
        _BASE_UNIVERSE[key] = _unique(getattr(core, "UNIVERSE", []) or [])
    return list(_BASE_UNIVERSE[key])


def _compose_universe(
    positions: Sequence[str],
    base: Sequence[str],
    broad: Sequence[str],
    cap: int = MAX_FINAL_UNIVERSE,
    broad_cap: int = MAX_BROAD_SLOTS,
    base_cap: int = MAX_BASE_SLOTS,
) -> List[str]:
    protected = _unique(list(BENCHMARK_SYMBOLS) + list(positions))
    protected_set = set(protected)
    broad_slots = _unique([symbol for symbol in broad if _symbol(symbol) not in protected_set])[:broad_cap]
    used = set(protected + broad_slots)
    base_slots = _unique([symbol for symbol in base if _symbol(symbol) not in used])[:base_cap]
    return _unique(protected + broad_slots + base_slots)[:cap]


def _infer_append_owner(symbol: str, base: set[str], broad: set[str], protected: set[str]) -> str:
    if symbol in protected:
        return "protected_position_or_benchmark"
    if symbol in broad:
        return "broad_momentum_discovery"
    if symbol in base:
        return "base_or_legacy_overlay"
    for module_name in _OWNER_MODULE_HINTS:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr in _OWNER_ATTR_HINTS:
            try:
                values = getattr(module, attr, None)
                if isinstance(values, dict):
                    values = values.keys()
                if symbol in set(_unique(values or [])):
                    return module_name
            except Exception:
                continue
    return "unknown_runtime_overlay"


def _apply_classification(core: Any, candidates: Sequence[Dict[str, Any]], final_universe: Sequence[str]) -> None:
    sector_map = getattr(core, "SYMBOL_SECTOR", None)
    bucket_map = getattr(core, "SYMBOL_BUCKET", None)
    bucket_cfg = getattr(core, "BUCKET_CONFIG", None)
    by_symbol = {
        _symbol(row.get("symbol")): _merge_classification(dict(row), core)
        for row in candidates or []
        if isinstance(row, dict) and _symbol(row.get("symbol"))
    }
    if isinstance(bucket_cfg, dict):
        bucket_cfg.setdefault(DYNAMIC_BUCKET, dict(DYNAMIC_BUCKET_CONFIG))
    for symbol in final_universe:
        row = by_symbol.get(_symbol(symbol), {})
        if isinstance(bucket_map, dict):
            bucket_map.setdefault(symbol, DYNAMIC_BUCKET)
        if isinstance(sector_map, dict):
            sector_map[symbol] = str(row.get("sector_proxy") or sector_map.get(symbol) or "UNKNOWN")


def _sector_enrichment_worker(core: Any, candidates: Sequence[Dict[str, Any]]) -> None:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return
    processed = 0
    for row in candidates:
        if processed >= max(0, SECTOR_ENRICH_PER_REFRESH):
            break
        symbol = _symbol(row.get("symbol")) if isinstance(row, dict) else ""
        if not symbol or row.get("sector_proxy") or _cached_classification(symbol):
            continue
        processed += 1
        try:
            info = yf.Ticker(symbol).get_info()
            if not isinstance(info, dict):
                continue
            sector = _normalize_sector(info.get("sector") or info.get("sectorDisp"))
            industry = str(info.get("industry") or info.get("industryDisp") or "").strip()
            proxy = _sector_proxy(sector)
            with _LOCK:
                _SECTOR_CACHE[symbol] = {
                    "ts": time.time(),
                    "sector_name": sector,
                    "industry_name": industry,
                    "sector_proxy": proxy,
                    "classification_source": "yfinance_profile_cache",
                }
            if proxy:
                try:
                    getattr(core, "SYMBOL_SECTOR", {})[symbol] = proxy
                except Exception:
                    pass
        except Exception:
            continue


def _schedule_sector_enrichment(core: Any, candidates: Sequence[Dict[str, Any]]) -> None:
    global _SECTOR_THREAD
    with _LOCK:
        if _SECTOR_THREAD is not None and _SECTOR_THREAD.is_alive():
            return
        missing = [
            dict(row)
            for row in candidates
            if isinstance(row, dict)
            and _symbol(row.get("symbol"))
            and not row.get("sector_proxy")
            and not _cached_classification(_symbol(row.get("symbol")))
        ]
        if not missing:
            return
        _SECTOR_THREAD = threading.Thread(
            target=_sector_enrichment_worker,
            args=(core, missing),
            name="broad-momentum-sector-enrichment",
            daemon=True,
        )
        _SECTOR_THREAD.start()


def _record_boundary(
    core: Any,
    payload: Dict[str, Any],
    *,
    phase: str,
    pre_universe: Sequence[str],
    final_universe: Sequence[str],
) -> Dict[str, Any]:
    base = set(_base_universe(core))
    broad = set(_unique(payload.get("selected_symbols") or []))
    protected = set(_unique(list(BENCHMARK_SYMBOLS) + _positions(core)))
    intended = set(final_universe)
    extras = [symbol for symbol in _unique(pre_universe) if symbol not in intended]
    appended = [
        {"symbol": symbol, "owner_hint": _infer_append_owner(symbol, base, broad, protected)}
        for symbol in extras[:100]
    ]
    record = {
        "version": VERSION,
        "generated_local": _now(core),
        "phase": phase,
        "discovery_pool_count": len(_unique(payload.get("selected_symbols") or [])),
        "intended_working_universe_count": len(final_universe),
        "scanner_input_universe_count": len(final_universe) if phase == "pre_scan" else None,
        "pre_boundary_universe_count": len(_unique(pre_universe)),
        "post_boundary_universe_count": len(final_universe),
        "max_final_universe": MAX_FINAL_UNIVERSE,
        "within_policy_cap": len(final_universe) <= MAX_FINAL_UNIVERSE,
        "appended_after_discovery_count": len(extras),
        "appended_after_discovery": appended,
        "final_universe": list(final_universe),
        "execution_authority": "existing_rules_only",
        "ml_authority": "shadow_recommendation_only",
    }
    try:
        portfolio = getattr(core, "portfolio", {})
        if isinstance(portfolio, dict):
            state = portfolio.setdefault("broad_momentum_discovery", {})
            if isinstance(state, dict):
                state.update(record)
                history = state.setdefault("boundary_history", [])
                if isinstance(history, list):
                    history.append(dict(record))
                    del history[:-20]
    except Exception:
        pass
    return record


def apply_universe(core: Any, payload: Dict[str, Any], phase: str = "discovery") -> Dict[str, Any]:
    base = _base_universe(core)
    broad = list(payload.get("selected_symbols") or [])
    pre_universe = _unique(getattr(core, "UNIVERSE", []) or [])
    final_universe = _compose_universe(_positions(core), base, broad)
    if not broad:
        final_universe = _unique(list(BENCHMARK_SYMBOLS) + _positions(core) + base)[:MAX_FINAL_UNIVERSE]
    _apply_classification(core, list(payload.get("candidates") or []), final_universe)
    core.UNIVERSE = final_universe
    _schedule_sector_enrichment(core, list(payload.get("candidates") or [])[:MAX_BROAD_SLOTS])
    record = _record_boundary(
        core,
        payload,
        phase=phase,
        pre_universe=pre_universe,
        final_universe=final_universe,
    )
    record.update(
        {
            "status": payload.get("status"),
            "source_counts": payload.get("source_counts"),
            "source_errors": payload.get("source_errors"),
            "eligible_unique_count": payload.get("eligible_unique_count"),
            "protected_symbols": _unique(list(BENCHMARK_SYMBOLS) + _positions(core)),
            "broad_symbols_used": [s for s in broad if s in final_universe],
            "base_fallback_symbols": [s for s in final_universe if s in set(base) and s not in set(broad)],
            "theme_baskets_are_fallback_and_classification": True,
        }
    )
    try:
        state = (getattr(core, "portfolio", {}) or {}).get("broad_momentum_discovery")
        if isinstance(state, dict):
            state.update(record)
    except Exception:
        pass
    return record


def _linked_callable(current: Any, marker: str) -> bool:
    seen: set[int] = set()
    queue: List[Any] = [current]
    while queue and len(seen) < 80:
        fn = queue.pop(0)
        if not callable(fn) or id(fn) in seen:
            continue
        seen.add(id(fn))
        if getattr(fn, marker, None) == VERSION:
            return True
        for attr in (
            "__wrapped__",
            "_broad_momentum_original",
            "_broad_momentum_scan_original",
            "_dynamic_universe_builder_original",
            "_shared_cycle_identity_original",
            "_scanner_v2_lifecycle_trace_original",
        ):
            linked = getattr(fn, attr, None)
            if callable(linked):
                queue.append(linked)
    return False


def _patch_scan_signals(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current) or _linked_callable(current, "_broad_momentum_scan_version"):
        return False
    original = current

    @functools.wraps(original)
    def wrapped_scan_signals(*args, **kwargs):
        payload = discover(core, force=False, wait=True)
        apply_universe(core, payload, phase="pre_scan")
        result = original(*args, **kwargs)
        try:
            state = (getattr(core, "portfolio", {}) or {}).get("broad_momentum_discovery", {})
            if isinstance(state, dict):
                state["last_scan_completed_local"] = _now(core)
                state["last_scan_result_count"] = len(result) if isinstance(result, list) else None
                state["post_scan_universe_count"] = len(_unique(getattr(core, "UNIVERSE", []) or []))
        except Exception:
            pass
        return result

    wrapped_scan_signals._broad_momentum_scan_version = VERSION  # type: ignore[attr-defined]
    wrapped_scan_signals._broad_momentum_scan_original = original  # type: ignore[attr-defined]
    core.scan_signals = wrapped_scan_signals
    return True


def _patch_run_cycle(core: Any) -> bool:
    current = getattr(core, "run_cycle", None)
    if not callable(current) or _linked_callable(current, "_broad_momentum_discovery_version"):
        return False
    original = current

    @functools.wraps(original)
    def wrapped_run_cycle(*args, **kwargs):
        payload: Dict[str, Any] | None = None
        try:
            clock = core.market_clock() if callable(getattr(core, "market_clock", None)) else {}
            market_open = bool(clock.get("is_open", False)) if isinstance(clock, dict) else False
            if ENABLED and _paper_context() and market_open:
                payload = discover(core, force=False, wait=True)
                apply_universe(core, payload, phase="pre_cycle")
        except Exception as exc:
            try:
                portfolio = getattr(core, "portfolio", {})
                if isinstance(portfolio, dict):
                    portfolio["broad_momentum_discovery"] = {
                        "version": VERSION,
                        "generated_local": _now(core),
                        "status": "warn",
                        "error": f"{type(exc).__name__}: {exc}",
                        "fallback": "existing_universe_preserved",
                        "execution_authority": "existing_rules_only",
                    }
            except Exception:
                pass
        try:
            return original(*args, **kwargs)
        finally:
            if payload:
                try:
                    apply_universe(core, payload, phase="post_cycle")
                except Exception:
                    pass

    wrapped_run_cycle._broad_momentum_discovery_version = VERSION  # type: ignore[attr-defined]
    wrapped_run_cycle._broad_momentum_original = original  # type: ignore[attr-defined]
    core.run_cycle = wrapped_run_cycle
    return True


def _watchdog(core: Any) -> None:
    while True:
        try:
            _patch_run_cycle(core)
            _patch_scan_signals(core)
        except Exception:
            pass
        time.sleep(max(5, WATCHDOG_SECONDS))


def _start_watchdog(core: Any) -> None:
    if id(core) in _WATCHDOG_CORE_IDS:
        return
    _WATCHDOG_CORE_IDS.add(id(core))
    try:
        threading.Thread(
            target=_watchdog,
            args=(core,),
            name="broad-momentum-discovery-watchdog",
            daemon=True,
        ).start()
    except Exception:
        pass


def status_payload(core: Any = None, force: bool = False) -> Dict[str, Any]:
    core = core or _module()
    payload = discover(core, force=True, wait=True) if force else dict(_LAST or {})
    if not payload:
        payload = {
            "status": "pending",
            "overall": "pending",
            "type": "broad_momentum_discovery_status",
            "version": VERSION,
            "generated_local": _now(core),
            "reason": "awaiting_first_market_open_cycle",
            "selected_symbols": [],
            "candidates": [],
            "top_candidates": [],
        }
    payload = dict(payload)
    run_current = getattr(core, "run_cycle", None) if core is not None else None
    scan_current = getattr(core, "scan_signals", None) if core is not None else None
    current_universe = _unique(getattr(core, "UNIVERSE", []) or []) if core is not None else []
    boundary = {}
    if core is not None:
        try:
            boundary = dict((getattr(core, "portfolio", {}) or {}).get("broad_momentum_discovery") or {})
        except Exception:
            boundary = {}
    classified = sum(1 for row in payload.get("candidates") or [] if isinstance(row, dict) and row.get("sector_proxy"))
    selected_count = len(payload.get("selected_symbols") or [])
    payload.update(
        {
            "enabled": bool(ENABLED),
            "paper_context": bool(_paper_context()),
            "run_cycle_hook_active": _linked_callable(run_current, "_broad_momentum_discovery_version"),
            "scan_boundary_hook_active": _linked_callable(scan_current, "_broad_momentum_scan_version"),
            "current_universe_count": len(current_universe),
            "current_universe": current_universe[:MAX_FINAL_UNIVERSE],
            "current_universe_over_policy_cap": max(0, len(current_universe) - MAX_FINAL_UNIVERSE),
            "last_scanner_boundary": boundary,
            "classification": {
                "classified_count": classified,
                "unclassified_count": max(0, selected_count - classified),
                "coverage_pct": round(100.0 * classified / selected_count, 2) if selected_count else 0.0,
                "sector_cache_count": len(_SECTOR_CACHE),
                "enrichment_in_progress": bool(_SECTOR_THREAD and _SECTOR_THREAD.is_alive()),
                "enrichment_non_blocking": True,
            },
            "authority": _authority(),
        }
    )
    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_not_ready"}
    _base_universe(core)
    run_patched = _patch_run_cycle(core)
    scan_patched = _patch_scan_signals(core)
    _start_watchdog(core)
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "run_cycle_hook_active": _linked_callable(getattr(core, "run_cycle", None), "_broad_momentum_discovery_version"),
        "scan_boundary_hook_active": _linked_callable(getattr(core, "scan_signals", None), "_broad_momentum_scan_version"),
        "patched_run_cycle_this_call": bool(run_patched),
        "patched_scan_this_call": bool(scan_patched),
        "watchdog_started": id(core) in _WATCHDOG_CORE_IDS,
        "authority_changed": False,
        "execution_authority": "existing_rules_only",
        "ml_authority": "shadow_recommendation_only",
    }


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
        return jsonify(status_payload(core or _module(), force=force))

    def candidates_route():
        payload = status_payload(core or _module(), force=False)
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 200))
        except Exception:
            limit = 100
        candidates = list(payload.get("candidates") or payload.get("top_candidates") or [])
        return jsonify(
            {
                "status": payload.get("status"),
                "type": "broad_momentum_candidates",
                "version": VERSION,
                "generated_local": payload.get("generated_local") or _now(core),
                "selected_count": payload.get("selected_count", len(payload.get("selected_symbols") or [])),
                "candidates": candidates[:limit],
                "selected_symbols": list(payload.get("selected_symbols") or [])[:limit],
                "source_counts": payload.get("source_counts"),
                "source_errors": payload.get("source_errors"),
                "classification": payload.get("classification"),
                "last_scanner_boundary": payload.get("last_scanner_boundary"),
                "authority": payload.get("authority"),
            }
        )

    if "/paper/broad-momentum-discovery-status" not in existing:
        flask_app.add_url_rule(
            "/paper/broad-momentum-discovery-status",
            "broad_momentum_discovery_status",
            status_route,
        )
    else:
        endpoint = next(
            (
                getattr(rule, "endpoint", None)
                for rule in flask_app.url_map.iter_rules()
                if getattr(rule, "rule", "") == "/paper/broad-momentum-discovery-status"
            ),
            None,
        )
        if endpoint:
            flask_app.view_functions[endpoint] = status_route

    if "/paper/broad-momentum-candidates" not in existing:
        flask_app.add_url_rule(
            "/paper/broad-momentum-candidates",
            "broad_momentum_candidates",
            candidates_route,
        )
    else:
        endpoint = next(
            (
                getattr(rule, "endpoint", None)
                for rule in flask_app.url_map.iter_rules()
                if getattr(rule, "rule", "") == "/paper/broad-momentum-candidates"
            ),
            None,
        )
        if endpoint:
            flask_app.view_functions[endpoint] = candidates_route

    _REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _module())


try:
    apply(_module())
except Exception:
    pass
