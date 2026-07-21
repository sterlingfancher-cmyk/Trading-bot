"""Scanner v2 missed-opportunity post-close audit.

Advisory-only diagnostics that compare notable daily movers against the bot's
current universe, scanner/decision telemetry, blocker records, and positions.
The module never mutates the executable universe, patches scan_signals, changes
thresholds, or places orders.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Iterable, List, Set

VERSION = "missed-opportunity-post-close-audit-2026-07-21-v2-failure-modes"
REGISTERED_APP_IDS: set[int] = set()
DEFAULT_SYMBOLS = ["BE", "NVTS", "STX", "NUAI", "CRWV", "ONDS"]
DEFAULT_MOVE_THRESHOLD_PCT = 8.0
MAX_SYMBOLS = 40

THEME_MAP = {
    "BE": "power_electrification",
    "NVTS": "semiconductor_power_and_components",
    "STX": "ai_data_center_infrastructure",
    "NUAI": "power_electrification",
    "CRWV": "ai_data_center_infrastructure",
    "ONDS": "autonomy_drones_and_sensing",
}


def _mod() -> Any | None:
    import sys
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


def _symbol(value: Any) -> str:
    raw = str(value or "").upper().strip().lstrip("$")
    if not raw or len(raw) > 10:
        return ""
    allowed = raw.replace(".", "").replace("-", "")
    return raw if allowed.isalnum() else ""


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


def _flatten_symbols(obj: Any, max_items: int = 20000) -> Set[str]:
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


def _records_for_symbol(obj: Any, symbol: str, max_hits: int = 30) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    keep = (
        "symbol", "ticker", "score", "reason", "category", "status", "decision",
        "blocked", "eligible", "entry_context", "trade_class", "bucket", "sector",
        "side", "price", "promotion_score", "quality_score", "cycle_id",
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
    for attr in (
        "UNIVERSE", "WATCHLIST", "WATCHLIST_SYMBOLS", "TRADING_UNIVERSE",
        "SCAN_UNIVERSE", "LONG_WATCHLIST", "SHORT_WATCHLIST",
    ):
        try:
            raw = getattr(core, attr, None)
            if isinstance(raw, (list, tuple, set)):
                symbols |= set(_unique(raw))
            symbols |= _flatten_symbols(raw)
        except Exception:
            pass
    for key in ("universe", "watchlist", "scanner_universe", "symbols", "long_symbols", "short_symbols"):
        raw = state.get(key)
        if isinstance(raw, (list, tuple, set)):
            symbols |= set(_unique(raw))
        symbols |= _flatten_symbols(raw)
    return symbols


def _fetch_daily_snapshot(symbol: str) -> Dict[str, Any]:
    empty = {
        "symbol": symbol, "data_available": False, "price": None, "previous_close": None,
        "pct_change": None, "volume": None, "avg_volume_20d": None, "volume_ratio": None,
        "data_error": None,
    }
    try:
        import yfinance as yf  # type: ignore
        data = yf.download(symbol, period="35d", interval="1d", progress=False, auto_adjust=False, threads=False)
        if data is None or len(data) < 2:
            empty["data_error"] = "not_enough_rows"
            return empty

        def values(column: str) -> List[float]:
            try:
                series = data[column]
                if hasattr(series, "columns"):
                    series = series.iloc[:, 0]
                result = []
                for raw in list(series):
                    value = _safe_float(raw)
                    if value is not None and value == value:
                        result.append(float(value))
                return result
            except Exception:
                return []

        closes = values("Close")
        volumes = values("Volume")
        if len(closes) < 2:
            empty["data_error"] = "close_values_unavailable"
            return empty
        price = closes[-1]
        previous = closes[-2]
        pct_change = ((price - previous) / previous) * 100.0 if previous else None
        volume = volumes[-1] if volumes else None
        prior_volumes = [v for v in volumes[:-1][-20:] if v > 0]
        avg_volume = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        volume_ratio = volume / avg_volume if volume is not None and avg_volume else None
        return {
            "symbol": symbol, "data_available": True, "price": round(price, 4),
            "previous_close": round(previous, 4),
            "pct_change": round(pct_change, 4) if pct_change is not None else None,
            "volume": int(volume) if volume is not None else None,
            "avg_volume_20d": round(avg_volume, 2) if avg_volume is not None else None,
            "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
            "data_error": None,
        }
    except Exception as exc:
        empty["data_error"] = f"snapshot_failed:{type(exc).__name__}"
        return empty


def _classification(in_universe: bool, seen: bool, in_position: bool) -> str:
    if in_position:
        return "captured_position"
    if not in_universe and not seen:
        return "universe_coverage_miss"
    if in_universe and not seen:
        return "universe_present_but_no_observation"
    if seen:
        return "seen_but_not_entered"
    return "outside_observed_pipeline"


def build_audit(core: Any = None, symbols: Iterable[Any] | None = None, force_market_data: bool = False,
                move_threshold_pct: float = DEFAULT_MOVE_THRESHOLD_PCT) -> Dict[str, Any]:
    core = core or _mod()
    selected = _unique(symbols or DEFAULT_SYMBOLS)
    if core is None:
        return {
            "status": "pending", "overall": "pending", "type": "missed_opportunity_post_close_audit",
            "version": VERSION, "symbols": selected, "reason": "core_not_ready",
        }

    state = _state(core)
    portfolio = _portfolio(core)
    universe = _universe(core, state)
    positions = set(_symbol(s) for s in ((portfolio.get("positions") or {}).keys() if isinstance(portfolio.get("positions"), dict) else []))

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
        records = _records_for_symbol(sections, symbol)
        section_hits = sorted({name for name, value in sections.items() if symbol in _flatten_symbols(value)})
        reasons = []
        for record in records:
            reason = str(record.get("reason") or "").strip()
            if reason and reason not in reasons:
                reasons.append(reason)
        snapshot = _fetch_daily_snapshot(symbol) if force_market_data else {
            "symbol": symbol, "data_available": None, "pct_change": None,
            "data_error": "market_data_not_requested; add force=1",
        }
        pct_change = _safe_float(snapshot.get("pct_change"))
        in_universe = symbol in universe
        seen = bool(section_hits)
        in_position = symbol in positions
        rows.append({
            "symbol": symbol,
            "theme_cluster": THEME_MAP.get(symbol, "unclassified"),
            "in_executable_universe": in_universe,
            "in_open_positions": in_position,
            "scanner_or_audit_seen": seen,
            "section_hits": section_hits,
            "record_count": len(records),
            "records": records[:12],
            "observed_reasons": reasons[:12],
            "market_snapshot": snapshot,
            "meets_move_threshold": bool(pct_change is not None and pct_change >= move_threshold_pct),
            "diagnostic_classification": _classification(in_universe, seen, in_position),
            "recommended_diagnostic_next_step": (
                "evaluate for shadow-universe coverage and liquidity" if not in_universe else
                "inspect scanner iteration, data availability, and persistence path" if not seen else
                "review ranking and blockers"
            ),
        })

    classes = [row["diagnostic_classification"] for row in rows]
    summary = {
        "symbols_requested": len(selected),
        "in_executable_universe": sum(1 for row in rows if row["in_executable_universe"]),
        "seen_by_scanner_or_audit": sum(1 for row in rows if row["scanner_or_audit_seen"]),
        "universe_coverage_misses": classes.count("universe_coverage_miss"),
        "universe_present_but_no_observation": classes.count("universe_present_but_no_observation"),
        "outside_observed_pipeline": classes.count("outside_observed_pipeline"),
        "seen_but_not_entered": classes.count("seen_but_not_entered"),
        "captured_positions": classes.count("captured_position"),
        "market_data_requested": bool(force_market_data),
        "move_threshold_pct": float(move_threshold_pct),
        "threshold_movers_confirmed": sum(1 for row in rows if row["meets_move_threshold"]),
        "theme_clusters": sorted({row["theme_cluster"] for row in rows}),
    }
    return {
        "status": "ok", "overall": "pass", "type": "missed_opportunity_post_close_audit",
        "version": VERSION, "generated_local": _now(core), "mode": "advisory_post_close_only",
        "summary": summary, "rows": rows,
        "authority": {
            "core_universe_mutated": False, "scan_signals_patched": False, "places_orders": False,
            "changes_thresholds": False, "changes_risk_or_sizing": False,
            "changes_ml_authority": False, "changes_live_authority": False,
        },
        "next_use": "Use repeated post-close audits to quantify universe coverage misses separately from scanner observation and ranking misses before changing scanner authority.",
    }


def lightweight_status(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if (core or _mod()) is not None else "pending",
        "overall": "pass" if (core or _mod()) is not None else "pending",
        "type": "missed_opportunity_post_close_audit", "version": VERSION,
        "mode": "advisory_post_close_only", "default_symbols": DEFAULT_SYMBOLS,
        "default_move_threshold_pct": DEFAULT_MOVE_THRESHOLD_PCT,
        "heavy_market_data_deferred": True,
        "authority": {
            "core_universe_mutated": False, "scan_signals_patched": False,
            "places_orders": False, "changes_thresholds": False,
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
        raw_symbols = str(request.args.get("symbols", "")).strip()
        symbols = raw_symbols.split(",") if raw_symbols else DEFAULT_SYMBOLS
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
        threshold = _safe_float(request.args.get("threshold"), DEFAULT_MOVE_THRESHOLD_PCT) or DEFAULT_MOVE_THRESHOLD_PCT
        return jsonify(build_audit(core or _mod(), symbols=symbols, force_market_data=force, move_threshold_pct=threshold))

    path = "/paper/missed-opportunity-post-close-audit-status"
    if path not in existing:
        flask_app.add_url_rule(path, "missed_opportunity_post_close_audit_status", route)
    REGISTERED_APP_IDS.add(id(flask_app))