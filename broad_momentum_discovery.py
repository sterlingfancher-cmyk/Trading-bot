"""Paper-only broad-market momentum discovery with bounded scanner ownership.

Discovers liquid U.S. momentum leaders, composes a bounded working universe, and
leaves all trade decisions to the existing rules engine. Scanner callable
ownership remains with ``scanner_runtime_contract``; this module only supplies
and assigns the universe immediately before that canonical scanner runs.
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

VERSION = "broad-momentum-discovery-2026-08-05-v2.1-ownership-safe"
ENABLED = os.getenv("BROAD_MOMENTUM_DISCOVERY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.getenv("BROAD_MOMENTUM_DISCOVERY_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
CACHE_TTL_SECONDS = int(os.getenv("BROAD_MOMENTUM_CACHE_TTL_SECONDS", "900"))
REFRESH_WAIT_SECONDS = float(os.getenv("BROAD_MOMENTUM_REFRESH_WAIT_SECONDS", "7"))
MAX_DISCOVERY_SYMBOLS = int(os.getenv("BROAD_MOMENTUM_MAX_DISCOVERY_SYMBOLS", "160"))
MAX_FINAL_UNIVERSE = int(os.getenv("BROAD_MOMENTUM_MAX_FINAL_UNIVERSE", "110"))
MAX_BROAD_SLOTS = int(os.getenv("BROAD_MOMENTUM_MAX_BROAD_SLOTS", "80"))
MAX_BASE_SLOTS = int(os.getenv("BROAD_MOMENTUM_MAX_BASE_SLOTS", "25"))
MIN_PRICE = float(os.getenv("BROAD_MOMENTUM_MIN_PRICE", "3.00"))
MIN_DAY_VOLUME = float(os.getenv("BROAD_MOMENTUM_MIN_DAY_VOLUME", "350000"))
MIN_DOLLAR_VOLUME = float(os.getenv("BROAD_MOMENTUM_MIN_DOLLAR_VOLUME", "10000000"))
MIN_MARKET_CAP = float(os.getenv("BROAD_MOMENTUM_MIN_MARKET_CAP", "100000000"))
CUSTOM_SCREEN_SIZE = int(os.getenv("BROAD_MOMENTUM_CUSTOM_SCREEN_SIZE", "250"))
PREDEFINED_SCREEN_COUNT = int(os.getenv("BROAD_MOMENTUM_PREDEFINED_COUNT", "100"))
# Typed-configuration compatibility only. No broad-discovery watchdog loop is started.
WATCHDOG_SECONDS = int(os.getenv("BROAD_MOMENTUM_WATCHDOG_SECONDS", "10"))
SECTOR_ENRICH_PER_REFRESH = int(os.getenv("BROAD_MOMENTUM_SECTOR_ENRICH_PER_REFRESH", "12"))
SECTOR_CACHE_TTL_SECONDS = int(os.getenv("BROAD_MOMENTUM_SECTOR_CACHE_TTL_SECONDS", str(7 * 86400)))

BENCHMARK_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
SECTOR_ETF = {
    "basic materials": "XLB", "materials": "XLB",
    "communication services": "XLC",
    "consumer cyclical": "XLY", "consumer discretionary": "XLY",
    "consumer defensive": "XLP", "consumer staples": "XLP",
    "energy": "XLE", "financial services": "XLF", "financial": "XLF",
    "healthcare": "XLV", "health care": "XLV", "industrials": "XLI",
    "real estate": "XLRE", "technology": "XLK", "utilities": "XLU",
}
DYNAMIC_BUCKET = "dynamic_momentum"
DYNAMIC_BUCKET_CONFIG = {"alloc_factor": 0.40, "max_exposure_pct": 0.20, "max_positions": 3}

_LOCK = threading.RLock()
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_LAST: Dict[str, Any] = {}
_BASE_UNIVERSE: Dict[int, List[str]] = {}
_SECTOR_CACHE: Dict[str, Dict[str, Any]] = {}
_REFRESH_THREAD: threading.Thread | None = None
_REFRESH_EVENT = threading.Event()
_SECTOR_THREAD: threading.Thread | None = None
_REGISTERED_APPS: set[int] = set()

_OWNER_MODULE_HINTS = (
    "neutral_momentum_starter_extension", "opening_surge_participation",
    "dynamic_universe_builder", "scanner_v2_shadow_universe", "space_stock_basket",
    "spacex_direct_overlay", "breakout_participation_layer",
)
_OWNER_ATTR_HINTS = ("_EXTRA_SYMBOLS", "EXTRA", "EXTRA_SYMBOLS", "PREFERRED_SYMBOLS", "UNIVERSE", "THEME_SYMBOLS", "SYMBOLS")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, dict) and "raw" in value:
            value = value["raw"]
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
    out: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        symbol = _symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _unique_labels(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        label = str(value or "").strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.getenv("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.getenv("BROKER_MODE", "").lower() in {"live", "real", "production"}
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


def _value(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value.get("raw") if isinstance(value, dict) and "raw" in value else value
    return None


def _sector_proxy(value: Any) -> str | None:
    return SECTOR_ETF.get(str(value or "").strip().lower())


def _normalize_quote(quote: Dict[str, Any], source: str) -> Dict[str, Any] | None:
    if not isinstance(quote, dict):
        return None
    symbol = _symbol(_value(quote, "symbol", "ticker"))
    if not symbol:
        return None
    price = _f(_value(quote, "regularMarketPrice", "intradayprice", "regularMarketPreviousClose"))
    pct = _f(_value(quote, "regularMarketChangePercent", "percentchange"))
    volume = _f(_value(quote, "regularMarketVolume", "dayvolume", "eodvolume"))
    avg_volume = _f(_value(quote, "averageDailyVolume3Month", "avgdailyvol3m", "averageDailyVolume10Day"))
    market_cap = _f(_value(quote, "marketCap", "intradaymarketcap"))
    sector = str(_value(quote, "sector", "sectorName", "sectorDisp") or "").strip()
    industry = str(_value(quote, "industry", "industryName", "industryDisp") or "").strip()
    return {
        "symbol": symbol, "source": source, "sources": [source],
        "price": round(price, 4), "percent_change": round(pct, 4),
        "day_volume": int(volume) if volume > 0 else 0,
        "avg_volume_3m": int(avg_volume) if avg_volume > 0 else 0,
        "relative_volume": round(volume / avg_volume, 4) if avg_volume > 0 else 0.0,
        "dollar_volume": round(max(0.0, price * volume), 2),
        "market_cap": round(market_cap, 2), "sector_name": sector,
        "industry_name": industry, "sector_proxy": _sector_proxy(sector),
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
    pct, relvol = _f(row.get("percent_change")), _f(row.get("relative_volume"))
    dollar_volume, market_cap = _f(row.get("dollar_volume")), _f(row.get("market_cap"))
    score = max(-0.08, min(pct, 20.0) / 32.0)
    score += max(0.0, min(relvol - 1.0, 5.0)) / 10.0
    score += min(max(dollar_volume, 0.0), 500_000_000.0) / 2_500_000_000.0
    score += 0.035 if market_cap >= 2_000_000_000 else 0.020 if market_cap >= 500_000_000 else 0.0
    return round(score, 6)


def _quotes(response: Any) -> List[Dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    rows = response.get("quotes")
    if not isinstance(rows, list):
        results = (response.get("finance") or {}).get("result") if isinstance(response.get("finance"), dict) else None
        rows = results[0].get("quotes") if isinstance(results, list) and results and isinstance(results[0], dict) else []
    return [row for row in rows or [] if isinstance(row, dict)]


def _screen_calls() -> List[Tuple[str, Any]]:
    import yfinance as yf  # type: ignore
    calls: List[Tuple[str, Any]] = []
    for name in ("day_gainers", "most_actives"):
        try:
            try:
                response = yf.screen(name, count=PREDEFINED_SCREEN_COUNT)
            except TypeError:
                response = yf.screen(name, size=PREDEFINED_SCREEN_COUNT)
            calls.append((name, response))
        except Exception as exc:
            calls.append((name, {"_error": f"{type(exc).__name__}: {exc}"}))
    try:
        query = yf.EquityQuery("and", [
            yf.EquityQuery("eq", ["region", "us"]),
            yf.EquityQuery("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
            yf.EquityQuery("gte", ["intradayprice", MIN_PRICE]),
            yf.EquityQuery("gte", ["dayvolume", MIN_DAY_VOLUME]),
            yf.EquityQuery("gte", ["intradaymarketcap", MIN_MARKET_CAP]),
            yf.EquityQuery("gte", ["percentchange", 0.50]),
        ])
        calls.append(("market_wide_momentum", yf.screen(query, size=CUSTOM_SCREEN_SIZE, sortField="percentchange", sortAsc=False)))
    except Exception as exc:
        calls.append(("market_wide_momentum", {"_error": f"{type(exc).__name__}: {exc}"}))
    return calls


def _cached_classification(symbol: str) -> Dict[str, Any]:
    with _LOCK:
        row = dict(_SECTOR_CACHE.get(symbol) or {})
    return row if row and time.time() - _f(row.get("ts")) <= SECTOR_CACHE_TTL_SECONDS else {}


def _merge_classification(row: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    if row.get("sector_proxy"):
        return row
    symbol = _symbol(row.get("symbol"))
    cached = _cached_classification(symbol)
    if cached:
        row.update({key: cached.get(key) or row.get(key) for key in ("sector_name", "industry_name", "sector_proxy", "classification_source")})
        return row
    try:
        existing = (getattr(core, "SYMBOL_SECTOR", {}) or {}).get(symbol)
    except Exception:
        existing = None
    if existing:
        value = str(existing)
        row["sector_proxy"] = value.upper() if value.upper().startswith("XL") else _sector_proxy(value)
        row["sector_name"] = row.get("sector_name") or ("" if value.upper().startswith("XL") else value)
        row["classification_source"] = "existing_runtime_sector_map"
    return row


def _build_payload(core: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    by_symbol: Dict[str, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    try:
        calls = _screen_calls()
    except Exception as exc:
        calls, errors["screen_bootstrap"] = [], f"{type(exc).__name__}: {exc}"
    for source, response in calls:
        if isinstance(response, dict) and response.get("_error"):
            errors[source] = str(response["_error"])
            continue
        rows = _quotes(response)
        counts[source] = len(rows)
        for quote in rows:
            row = _normalize_quote(quote, source)
            if not row:
                continue
            ok, reason = _eligible(row)
            row.update({"eligible": ok, "eligibility_reason": reason})
            if not ok:
                continue
            existing = by_symbol.get(row["symbol"])
            if existing is None:
                by_symbol[row["symbol"]] = row
                continue
            sources = _unique_labels((existing.get("sources") or []) + (row.get("sources") or []))
            winner, loser = (row, existing) if _f(row.get("day_volume")) >= _f(existing.get("day_volume")) else (existing, row)
            winner["sources"] = sources
            for key in ("sector_name", "industry_name", "sector_proxy", "classification_source"):
                if not winner.get(key) and loser.get(key):
                    winner[key] = loser[key]
            by_symbol[winner["symbol"]] = winner
    rows = [_merge_classification(dict(row), core) for row in by_symbol.values()]
    for row in rows:
        bonus = min(0.06, 0.02 * max(0, len(row.get("sources") or []) - 1))
        row["source_confirmation_bonus"] = round(bonus, 6)
        row["discovery_score"] = round(_discovery_score(row) + bonus, 6)
    rows.sort(key=lambda row: (_f(row.get("discovery_score")), _f(row.get("percent_change")), _f(row.get("relative_volume")), _f(row.get("dollar_volume"))), reverse=True)
    selected = rows[:MAX_DISCOVERY_SYMBOLS]
    classified = sum(1 for row in selected if row.get("sector_proxy"))
    return {
        "status": "ok" if selected else "warn", "overall": "pass" if selected else "warn",
        "type": "broad_momentum_discovery_status", "version": VERSION,
        "generated_local": _now(core), "duration_seconds": round(time.perf_counter() - started, 4),
        "mode": "paper_only_market_wide_prefilter", "source_counts": counts, "source_errors": errors,
        "eligible_unique_count": len(rows), "selected_count": len(selected),
        "selected_symbols": [row["symbol"] for row in selected], "candidates": selected,
        "top_candidates": selected[:50],
        "classification": {"classified_count": classified, "unclassified_count": len(selected) - classified,
                           "coverage_pct": round(100.0 * classified / len(selected), 2) if selected else 0.0,
                           "enrichment_non_blocking": True},
        "policy": _policy(), "authority": _authority(),
    }


def _authority() -> Dict[str, Any]:
    return {"places_orders": False, "changes_entry_rules": False, "changes_hard_risk": False,
            "changes_sizing": False, "changes_ml_authority": False, "changes_live_authority": False,
            "execution_authority": "existing_rules_only", "ml_authority": "shadow_recommendation_only"}


def _policy() -> Dict[str, Any]:
    return {"cache_ttl_seconds": CACHE_TTL_SECONDS, "max_discovery_symbols": MAX_DISCOVERY_SYMBOLS,
            "max_final_universe": MAX_FINAL_UNIVERSE, "max_broad_slots": MAX_BROAD_SLOTS,
            "max_base_slots": MAX_BASE_SLOTS, "min_price": MIN_PRICE, "min_day_volume": MIN_DAY_VOLUME,
            "min_dollar_volume": MIN_DOLLAR_VOLUME, "min_market_cap": MIN_MARKET_CAP,
            "benchmark_symbols": list(BENCHMARK_SYMBOLS), "theme_baskets_are_fallback_and_classification": True,
            "scanner_boundary_enforced": True, "scanner_boundary_owner": "scanner_runtime_contract",
            "watchdog_loop_active": False, "watchdog_seconds_compatibility_only": WATCHDOG_SECONDS}


def _refresh_worker(core: Any = None) -> None:
    global _LAST
    try:
        payload = _build_payload(core)
    except Exception as exc:
        payload = {"status": "error", "overall": "warn", "type": "broad_momentum_discovery_status",
                   "version": VERSION, "generated_local": _now(core), "error": f"{type(exc).__name__}: {exc}",
                   "selected_symbols": [], "candidates": [], "top_candidates": [], "authority": _authority()}
    with _LOCK:
        _CACHE.update({"ts": time.time(), "payload": payload})
        _LAST = dict(payload)
        _REFRESH_EVENT.set()


def discover(core: Any = None, force: bool = False, wait: bool = True) -> Dict[str, Any]:
    global _REFRESH_THREAD
    with _LOCK:
        age = time.time() - _f(_CACHE.get("ts"))
        cached = _CACHE.get("payload")
        if not force and isinstance(cached, dict) and age < CACHE_TTL_SECONDS:
            return {**cached, "cache_hit": True, "cache_age_seconds": round(max(0.0, age), 2)}
        if _REFRESH_THREAD is None or not _REFRESH_THREAD.is_alive():
            _REFRESH_EVENT.clear()
            _REFRESH_THREAD = threading.Thread(target=_refresh_worker, args=(core,), daemon=True, name="broad-momentum-refresh")
            _REFRESH_THREAD.start()
    completed = _REFRESH_EVENT.wait(max(0.0, REFRESH_WAIT_SECONDS)) if wait else False
    with _LOCK:
        cached = _CACHE.get("payload")
        if isinstance(cached, dict):
            return {**cached, "cache_hit": not completed,
                    "cache_age_seconds": round(max(0.0, time.time() - _f(_CACHE.get("ts"))), 2),
                    "refresh_in_progress": bool(_REFRESH_THREAD and _REFRESH_THREAD.is_alive())}
    return {"status": "pending", "overall": "pending", "type": "broad_momentum_discovery_status",
            "version": VERSION, "generated_local": _now(core), "reason": "initial_refresh_in_progress",
            "refresh_in_progress": True, "selected_symbols": [], "candidates": [], "top_candidates": [],
            "authority": _authority()}


def _positions(core: Any) -> List[str]:
    try:
        return _unique((getattr(core, "portfolio", {}) or {}).get("positions", {}).keys())
    except Exception:
        return []


def _base_universe(core: Any) -> List[str]:
    if id(core) not in _BASE_UNIVERSE:
        _BASE_UNIVERSE[id(core)] = _unique(getattr(core, "UNIVERSE", []) or [])
    return list(_BASE_UNIVERSE[id(core)])


def _compose_universe(positions: Sequence[str], base: Sequence[str], broad: Sequence[str],
                      cap: int = MAX_FINAL_UNIVERSE, broad_cap: int = MAX_BROAD_SLOTS,
                      base_cap: int = MAX_BASE_SLOTS) -> List[str]:
    protected = _unique(list(BENCHMARK_SYMBOLS) + list(positions))
    broad_slots = _unique([s for s in broad if _symbol(s) not in set(protected)])[:broad_cap]
    used = set(protected + broad_slots)
    base_slots = _unique([s for s in base if _symbol(s) not in used])[:base_cap]
    return _unique(protected + broad_slots + base_slots)[:cap]


def _infer_owner(symbol: str, base: set[str], broad: set[str], protected: set[str]) -> str:
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
                pass
    return "unknown_runtime_overlay"


def _apply_classification(core: Any, candidates: Sequence[Dict[str, Any]], universe: Sequence[str]) -> None:
    sectors, buckets, configs = getattr(core, "SYMBOL_SECTOR", None), getattr(core, "SYMBOL_BUCKET", None), getattr(core, "BUCKET_CONFIG", None)
    by_symbol = {_symbol(row.get("symbol")): _merge_classification(dict(row), core) for row in candidates if isinstance(row, dict) and _symbol(row.get("symbol"))}
    if isinstance(configs, dict):
        configs.setdefault(DYNAMIC_BUCKET, dict(DYNAMIC_BUCKET_CONFIG))
    for symbol in universe:
        row = by_symbol.get(symbol, {})
        if isinstance(buckets, dict):
            buckets.setdefault(symbol, DYNAMIC_BUCKET)
        if isinstance(sectors, dict):
            sectors[symbol] = str(row.get("sector_proxy") or sectors.get(symbol) or "UNKNOWN")


def _enrich_worker(core: Any, candidates: Sequence[Dict[str, Any]]) -> None:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return
    processed = 0
    for row in candidates:
        symbol = _symbol(row.get("symbol")) if isinstance(row, dict) else ""
        if processed >= SECTOR_ENRICH_PER_REFRESH:
            break
        if not symbol or row.get("sector_proxy") or _cached_classification(symbol):
            continue
        processed += 1
        try:
            info = yf.Ticker(symbol).get_info()
            sector = str((info or {}).get("sector") or (info or {}).get("sectorDisp") or "").strip()
            industry = str((info or {}).get("industry") or (info or {}).get("industryDisp") or "").strip()
            proxy = _sector_proxy(sector)
            with _LOCK:
                _SECTOR_CACHE[symbol] = {"ts": time.time(), "sector_name": sector, "industry_name": industry,
                                         "sector_proxy": proxy, "classification_source": "yfinance_profile_cache"}
            if proxy and isinstance(getattr(core, "SYMBOL_SECTOR", None), dict):
                core.SYMBOL_SECTOR[symbol] = proxy
        except Exception:
            pass


def _schedule_enrichment(core: Any, candidates: Sequence[Dict[str, Any]]) -> None:
    global _SECTOR_THREAD
    with _LOCK:
        if _SECTOR_THREAD is not None and _SECTOR_THREAD.is_alive():
            return
        missing = [dict(row) for row in candidates if isinstance(row, dict) and _symbol(row.get("symbol")) and not row.get("sector_proxy") and not _cached_classification(_symbol(row.get("symbol")))]
        if not missing:
            return
        _SECTOR_THREAD = threading.Thread(target=_enrich_worker, args=(core, missing), daemon=True, name="broad-momentum-sector-enrichment")
        _SECTOR_THREAD.start()


def apply_universe(core: Any, payload: Dict[str, Any], phase: str = "discovery") -> Dict[str, Any]:
    base, broad = _base_universe(core), _unique(payload.get("selected_symbols") or [])
    before = _unique(getattr(core, "UNIVERSE", []) or [])
    final = _compose_universe(_positions(core), base, broad) if broad else _unique(list(BENCHMARK_SYMBOLS) + _positions(core) + base)[:MAX_FINAL_UNIVERSE]
    _apply_classification(core, payload.get("candidates") or [], final)
    core.UNIVERSE = final
    _schedule_enrichment(core, list(payload.get("candidates") or [])[:MAX_BROAD_SLOTS])
    protected, base_set, broad_set = set(_unique(list(BENCHMARK_SYMBOLS) + _positions(core))), set(base), set(broad)
    extras = [symbol for symbol in before if symbol not in set(final)]
    record = {
        "version": VERSION, "generated_local": _now(core), "phase": phase,
        "status": payload.get("status"), "source_counts": payload.get("source_counts"),
        "source_errors": payload.get("source_errors"), "eligible_unique_count": payload.get("eligible_unique_count"),
        "discovery_pool_count": len(broad), "intended_working_universe_count": len(final),
        "scanner_input_universe_count": len(final) if phase == "pre_scan" else None,
        "pre_boundary_universe_count": len(before), "post_boundary_universe_count": len(final),
        "max_final_universe": MAX_FINAL_UNIVERSE, "within_policy_cap": len(final) <= MAX_FINAL_UNIVERSE,
        "appended_after_discovery_count": len(extras),
        "appended_after_discovery": [{"symbol": s, "owner_hint": _infer_owner(s, base_set, broad_set, protected)} for s in extras[:100]],
        "protected_symbols": _unique(list(BENCHMARK_SYMBOLS) + _positions(core)),
        "broad_symbols_used": [s for s in broad if s in final], "final_universe": final,
        "execution_authority": "existing_rules_only", "ml_authority": "shadow_recommendation_only",
    }
    try:
        state = (getattr(core, "portfolio", {}) or {}).setdefault("broad_momentum_discovery", {})
        if isinstance(state, dict):
            history = state.setdefault("boundary_history", [])
            state.update(record)
            if isinstance(history, list):
                history.append(dict(record)); del history[:-20]
    except Exception:
        pass
    return record


def enforce_scanner_boundary(core: Any, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return apply_universe(core, dict(payload or discover(core, force=False, wait=True)), phase="pre_scan")


def _linked_marker(fn: Any, marker: str, limit: int = 60) -> bool:
    queue, seen = [fn], set()
    while queue and len(seen) < limit:
        current = queue.pop(0)
        if not callable(current) or id(current) in seen:
            continue
        seen.add(id(current))
        if getattr(current, marker, None) == VERSION:
            return True
        for attr in ("__wrapped__", "_broad_momentum_original", "_shared_cycle_identity_original", "_dynamic_universe_builder_original"):
            linked = getattr(current, attr, None)
            if callable(linked):
                queue.append(linked)
    return False


def _patch_run_cycle(core: Any) -> bool:
    current = getattr(core, "run_cycle", None)
    if not callable(current) or _linked_marker(current, "_broad_momentum_discovery_version"):
        return False

    @functools.wraps(current)
    def wrapped(*args, __prior=current, **kwargs):
        payload: Dict[str, Any] | None = None
        try:
            clock = core.market_clock() if callable(getattr(core, "market_clock", None)) else {}
            if ENABLED and _paper_context() and isinstance(clock, dict) and clock.get("is_open"):
                payload = discover(core, force=False, wait=True)
                apply_universe(core, payload, phase="pre_cycle")
        except Exception:
            payload = None
        try:
            return __prior(*args, **kwargs)
        finally:
            if payload:
                try:
                    apply_universe(core, payload, phase="post_cycle")
                except Exception:
                    pass

    wrapped._broad_momentum_discovery_version = VERSION
    wrapped._broad_momentum_original = current
    wrapped.__wrapped__ = current
    core.run_cycle = wrapped
    return True


def status_payload(core: Any = None, force: bool = False) -> Dict[str, Any]:
    core = core or _module()
    payload = discover(core, force=True, wait=True) if force else dict(_LAST or {})
    if not payload:
        payload = {"status": "pending", "overall": "pending", "type": "broad_momentum_discovery_status",
                   "version": VERSION, "generated_local": _now(core), "reason": "awaiting_first_market_open_cycle",
                   "selected_symbols": [], "candidates": [], "top_candidates": []}
    current = _unique(getattr(core, "UNIVERSE", []) or []) if core is not None else []
    boundary = dict(((getattr(core, "portfolio", {}) or {}).get("broad_momentum_discovery") or {})) if core is not None else {}
    selected_count = len(payload.get("selected_symbols") or [])
    classified = sum(1 for row in payload.get("candidates") or [] if isinstance(row, dict) and row.get("sector_proxy"))
    return {**payload, "enabled": ENABLED, "paper_context": _paper_context(),
            "run_cycle_hook_active": _linked_marker(getattr(core, "run_cycle", None), "_broad_momentum_discovery_version") if core is not None else False,
            "scan_boundary_hook_active": bool(core is not None and getattr(core, "SCANNER_UNIVERSE_BOUNDARY_VERSION", None) == VERSION),
            "scanner_boundary_owner": "scanner_runtime_contract", "current_universe_count": len(current),
            "current_universe": current[:MAX_FINAL_UNIVERSE], "current_universe_over_policy_cap": max(0, len(current) - MAX_FINAL_UNIVERSE),
            "last_scanner_boundary": boundary,
            "classification": {"classified_count": classified, "unclassified_count": max(0, selected_count - classified),
                               "coverage_pct": round(100.0 * classified / selected_count, 2) if selected_count else 0.0,
                               "sector_cache_count": len(_SECTOR_CACHE),
                               "enrichment_in_progress": bool(_SECTOR_THREAD and _SECTOR_THREAD.is_alive()),
                               "enrichment_non_blocking": True}, "policy": _policy(), "authority": _authority()}


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_not_ready"}
    _base_universe(core)
    patched = _patch_run_cycle(core)
    return {"status": "ok", "overall": "pass", "version": VERSION, "enabled": ENABLED,
            "paper_context": _paper_context(),
            "run_cycle_hook_active": _linked_marker(getattr(core, "run_cycle", None), "_broad_momentum_discovery_version"),
            "scan_boundary_hook_active": getattr(core, "SCANNER_UNIVERSE_BOUNDARY_VERSION", None) == VERSION,
            "scanner_boundary_owner": "scanner_runtime_contract", "patched_run_cycle_this_call": patched,
            "authority_changed": False, "execution_authority": "existing_rules_only",
            "ml_authority": "shadow_recommendation_only"}


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APPS:
        return
    from flask import jsonify, request
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}

    def status_route():
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
        return jsonify(status_payload(core or _module(), force=force))

    def candidates_route():
        payload = status_payload(core or _module())
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 200))
        except Exception:
            limit = 100
        candidates = list(payload.get("candidates") or payload.get("top_candidates") or [])
        return jsonify({"status": payload.get("status"), "type": "broad_momentum_candidates", "version": VERSION,
                        "generated_local": payload.get("generated_local") or _now(core),
                        "selected_count": payload.get("selected_count", len(payload.get("selected_symbols") or [])),
                        "candidates": candidates[:limit], "selected_symbols": list(payload.get("selected_symbols") or [])[:limit],
                        "source_counts": payload.get("source_counts"), "source_errors": payload.get("source_errors"),
                        "classification": payload.get("classification"), "last_scanner_boundary": payload.get("last_scanner_boundary"),
                        "authority": payload.get("authority")})

    routes = {
        "/paper/broad-momentum-discovery-status": ("broad_momentum_discovery_status", status_route),
        "/paper/broad-momentum-candidates": ("broad_momentum_candidates", candidates_route),
    }
    for path, (endpoint, view) in routes.items():
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, view)
        else:
            current_endpoint = next((getattr(rule, "endpoint", None) for rule in flask_app.url_map.iter_rules() if getattr(rule, "rule", "") == path), None)
            if current_endpoint:
                flask_app.view_functions[current_endpoint] = view
    _REGISTERED_APPS.add(id(flask_app))
    apply(core or _module())


try:
    apply(_module())
except Exception:
    pass
