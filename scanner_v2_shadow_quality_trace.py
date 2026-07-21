"""Scanner v2 shadow liquidity, data-quality, and observation trace.

Advisory-only. This module never mutates the executable universe, patches the
scanner, changes thresholds or sizing, or places orders. Heavy market-data work
runs only when force=1 is explicitly requested.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, Iterable, List, Set

VERSION = "scanner-v2-shadow-quality-trace-2026-07-21-v1"
REGISTERED_APP_IDS: set[int] = set()
DEFAULT_SYMBOLS = ["BE", "NVTS", "STX", "NUAI", "CRWV", "ONDS"]
MAX_SYMBOLS = 60
MIN_PRICE = 3.0
MIN_AVG_VOLUME = 350000.0
MIN_DOLLAR_VOLUME = 5000000.0


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _symbol(value: Any) -> str:
    raw = str(value or "").upper().strip().lstrip("$")
    clean = raw.replace(".", "").replace("-", "")
    return raw if raw and len(raw) <= 10 and clean.isalnum() else ""


def _unique(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for value in values or []:
        symbol = _symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out[:MAX_SYMBOLS]


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _state(core: Any) -> Dict[str, Any]:
    try:
        value = core.load_state()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        value = getattr(core, "portfolio", {})
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _flatten_symbols(obj: Any, max_items: int = 25000) -> Set[str]:
    found: Set[str] = set()
    seen = 0

    def walk(value: Any) -> None:
        nonlocal seen
        if seen >= max_items:
            return
        seen += 1
        if isinstance(value, dict):
            for key in ("symbol", "ticker", "asset"):
                if key in value:
                    symbol = _symbol(value.get(key))
                    if symbol:
                        found.add(symbol)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(obj)
    return found


def _records(obj: Any, symbol: str, max_hits: int = 40) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    keep = (
        "symbol", "ticker", "score", "reason", "category", "status", "decision",
        "blocked", "eligible", "entry_context", "trade_class", "bucket", "sector",
        "side", "price", "promotion_score", "quality_score", "cycle_id", "timestamp",
    )

    def walk(value: Any) -> None:
        if len(hits) >= max_hits:
            return
        if isinstance(value, dict):
            row_symbol = _symbol(value.get("symbol") or value.get("ticker") or value.get("asset"))
            if row_symbol == symbol:
                hits.append({key: value.get(key) for key in keep if key in value})
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(obj)
    return hits


def _universe(core: Any, state: Dict[str, Any]) -> Set[str]:
    symbols: Set[str] = set()
    for attr in ("UNIVERSE", "WATCHLIST", "WATCHLIST_SYMBOLS", "TRADING_UNIVERSE", "SCAN_UNIVERSE"):
        try:
            raw = getattr(core, attr, None)
            if isinstance(raw, (list, tuple, set)):
                symbols |= set(_unique(raw))
            symbols |= _flatten_symbols(raw)
        except Exception:
            pass
    for key in ("universe", "watchlist", "scanner_universe", "symbols"):
        raw = state.get(key)
        if isinstance(raw, (list, tuple, set)):
            symbols |= set(_unique(raw))
        symbols |= _flatten_symbols(raw)
    return symbols


def _market_snapshot(symbol: str) -> Dict[str, Any]:
    empty = {"symbol": symbol, "data_available": False, "data_error": None}
    try:
        import yfinance as yf  # type: ignore
        data = yf.download(symbol, period="35d", interval="1d", progress=False, auto_adjust=False, threads=False)
        if data is None or len(data) < 6:
            empty["data_error"] = "not_enough_rows"
            return empty

        def values(column: str) -> List[float]:
            try:
                series = data[column]
                if hasattr(series, "columns"):
                    series = series.iloc[:, 0]
                out: List[float] = []
                for raw in list(series):
                    value = _safe_float(raw)
                    if value is not None and value == value:
                        out.append(float(value))
                return out
            except Exception:
                return []

        closes = values("Close")
        volumes = values("Volume")
        if len(closes) < 6:
            empty["data_error"] = "close_values_unavailable"
            return empty
        price = closes[-1]
        previous = closes[-2]
        five_back = closes[-6]
        pct_1d = ((price - previous) / previous) * 100.0 if previous else None
        pct_5d = ((price - five_back) / five_back) * 100.0 if five_back else None
        volume = volumes[-1] if volumes else None
        prior = [v for v in volumes[:-1][-20:] if v > 0]
        avg_volume = sum(prior) / len(prior) if prior else None
        dollar_volume = price * avg_volume if avg_volume else None
        volume_ratio = volume / avg_volume if volume is not None and avg_volume else None
        quality_pass = bool(
            price >= MIN_PRICE and
            (avg_volume or 0.0) >= MIN_AVG_VOLUME and
            (dollar_volume or 0.0) >= MIN_DOLLAR_VOLUME
        )
        return {
            "symbol": symbol,
            "data_available": True,
            "data_error": None,
            "price": round(price, 4),
            "pct_change_1d": round(pct_1d, 4) if pct_1d is not None else None,
            "pct_change_5d": round(pct_5d, 4) if pct_5d is not None else None,
            "volume": int(volume) if volume is not None else None,
            "avg_volume_20d": round(avg_volume, 2) if avg_volume is not None else None,
            "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
            "dollar_volume": round(dollar_volume, 2) if dollar_volume is not None else None,
            "shadow_liquidity_pass": quality_pass,
            "quality_floor": {
                "min_price": MIN_PRICE,
                "min_avg_volume": MIN_AVG_VOLUME,
                "min_dollar_volume": MIN_DOLLAR_VOLUME,
            },
        }
    except Exception as exc:
        empty["data_error"] = f"snapshot_failed:{type(exc).__name__}"
        return empty


def build_trace(core: Any = None, symbols: Iterable[Any] | None = None, force_market_data: bool = False) -> Dict[str, Any]:
    core = core or _mod()
    selected = _unique(symbols or DEFAULT_SYMBOLS)
    if core is None:
        return {"status": "pending", "overall": "pending", "type": "scanner_v2_shadow_quality_trace", "version": VERSION, "reason": "core_not_ready"}

    state = _state(core)
    portfolio = _portfolio(core)
    universe = _universe(core, state)
    sections: Dict[str, Any] = {}
    for key in (
        "scanner_audit", "decision_audit", "decision_audit_summary", "blocked_entry_reason_audit",
        "entry_decision_visibility", "post_harvest_redeployment", "dynamic_universe_builder",
        "scanner_v2_shadow_universe", "missed_mover_audit", "ml_feature_journal",
    ):
        value = portfolio.get(key) if key in portfolio else state.get(key)
        if isinstance(value, (dict, list)):
            sections[key] = value

    rows: List[Dict[str, Any]] = []
    for symbol in selected:
        records = _records(sections, symbol)
        hits = sorted(name for name, value in sections.items() if symbol in _flatten_symbols(value))
        in_universe = symbol in universe
        classification = (
            "observed_with_records" if records else
            "observed_without_records" if hits else
            "universe_present_but_no_observation" if in_universe else
            "universe_coverage_miss"
        )
        rows.append({
            "symbol": symbol,
            "in_executable_universe": in_universe,
            "section_hits": hits,
            "record_count": len(records),
            "records": records[:15],
            "observation_classification": classification,
            "market_snapshot": _market_snapshot(symbol) if force_market_data else {
                "symbol": symbol,
                "data_available": None,
                "data_error": "market_data_not_requested; add force=1",
            },
            "recommended_next_trace": (
                "instrument scan_signals candidate lifecycle persistence" if classification == "universe_present_but_no_observation" else
                "continue shadow quality and leadership scoring" if classification == "universe_coverage_miss" else
                "inspect existing records and blockers"
            ),
        })

    return {
        "status": "ok",
        "overall": "pass",
        "type": "scanner_v2_shadow_quality_trace",
        "version": VERSION,
        "generated_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "advisory_shadow_only",
        "summary": {
            "symbols_requested": len(selected),
            "market_data_requested": bool(force_market_data),
            "universe_coverage_miss": sum(1 for row in rows if row["observation_classification"] == "universe_coverage_miss"),
            "universe_present_but_no_observation": sum(1 for row in rows if row["observation_classification"] == "universe_present_but_no_observation"),
            "observed_symbols": sum(1 for row in rows if row["section_hits"]),
            "liquidity_pass": sum(1 for row in rows if row["market_snapshot"].get("shadow_liquidity_pass") is True),
        },
        "rows": rows,
        "authority": {
            "core_universe_mutated": False,
            "scan_signals_patched": False,
            "places_orders": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
        "next_gate": "Use repeated shadow quality traces before adding composite scoring or any paper-only promotion authority.",
    }


def lightweight_status(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if (core or _mod()) is not None else "pending",
        "overall": "pass" if (core or _mod()) is not None else "pending",
        "type": "scanner_v2_shadow_quality_trace",
        "version": VERSION,
        "mode": "advisory_shadow_only",
        "default_symbols": DEFAULT_SYMBOLS,
        "heavy_market_data_deferred": True,
        "authority": {
            "core_universe_mutated": False,
            "scan_signals_patched": False,
            "places_orders": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return lightweight_status(core or _mod())


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def route():
        raw = str(request.args.get("symbols", "")).strip()
        symbols = raw.split(",") if raw else DEFAULT_SYMBOLS
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes"}
        return jsonify(build_trace(core or _mod(), symbols=symbols, force_market_data=force))

    path = "/paper/scanner-v2-shadow-quality-trace-status"
    if path not in existing:
        flask_app.add_url_rule(path, "scanner_v2_shadow_quality_trace_status", route)
    REGISTERED_APP_IDS.add(id(flask_app))
