"""Shadow-only cross-asset opportunity ranking.

This module is research/observability only. It never places orders, changes
strategy/risk/sizing/thresholds, or feeds candidates back into execution.

Stocks and ETFs are sourced from the latest authoritative scanner telemetry
already stored in paper state. Crypto research is limited to BTC/ETH/SOL and
uses the existing core.download_prices adapter with a bounded cache.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, Iterable, List

VERSION = "multi-asset-shadow-ranker-2026-08-07-v1"
CACHE_SECONDS = 900.0
CRYPTO_SYMBOLS = ("BTC-USD", "ETH-USD", "SOL-USD")
ETF_SYMBOLS = {
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI",
    "XLY", "XLP", "XLU", "XLB", "XLRE", "GLD", "SLV", "SMH", "IBB",
    "ARKK", "TLT", "HYG", "LQD",
}
MAX_SCANNER_ROWS = 40
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}
_REGISTERED_APP_IDS: set[int] = set()

AUTHORITY = {
    "places_orders": False,
    "changes_strategy": False,
    "changes_thresholds": False,
    "changes_risk_or_sizing": False,
    "changes_live_or_ml_authority": False,
    "feeds_execution_candidates": False,
    "research_only": True,
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _state(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _asset_class(symbol: str) -> str:
    symbol = str(symbol or "").upper().strip()
    if symbol in CRYPTO_SYMBOLS or symbol.endswith("-USD"):
        return "crypto"
    if symbol in ETF_SYMBOLS:
        return "etf"
    return "equity"


def _scanner_rows(core: Any) -> List[Dict[str, Any]]:
    state = _state(core)
    last = _d(_d(state.get("auto_runner")).get("last_result"))
    by_symbol: Dict[str, Dict[str, Any]] = {}

    def add(row: Any, lifecycle: str, direction: str | None = None) -> None:
        if not isinstance(row, dict):
            return
        symbol = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
        if not symbol or symbol in CRYPTO_SYMBOLS or symbol.endswith("-USD"):
            return
        score = _f(row.get("score"), None)
        current = by_symbol.get(symbol)
        candidate = {
            "symbol": symbol,
            "asset_class": _asset_class(symbol),
            "source": "authoritative_scanner_telemetry",
            "lifecycle": lifecycle,
            "direction": str(row.get("side") or direction or "long").lower(),
            "raw_score": score,
            "reason": row.get("reason") or row.get("entry_block_reason"),
            "sector": row.get("sector"),
            "bucket": row.get("bucket"),
            "execution_authority": False,
        }
        if current is None:
            by_symbol[symbol] = candidate
            return
        old_score = _f(current.get("raw_score"), None)
        if score is not None and (old_score is None or score > old_score):
            by_symbol[symbol] = candidate

    for row in _l(last.get("entries")):
        add(row, "accepted_entry")
    for row in _l(last.get("blocked_entries")):
        add(row, "blocked")
    for row in _l(last.get("rejected_signals")):
        add(row, "rejected")

    for direction, key in (("long", "long_signals"), ("short", "short_signals")):
        for item in _l(last.get(key)):
            if isinstance(item, dict):
                add(item, "signal", direction)
            else:
                symbol = str(item or "").upper().strip()
                if symbol and symbol not in by_symbol:
                    by_symbol[symbol] = {
                        "symbol": symbol,
                        "asset_class": _asset_class(symbol),
                        "source": "authoritative_scanner_telemetry",
                        "lifecycle": "signal",
                        "direction": direction,
                        "raw_score": None,
                        "reason": None,
                        "sector": None,
                        "bucket": None,
                        "execution_authority": False,
                    }

    rows = list(by_symbol.values())
    rows.sort(key=lambda row: (_f(row.get("raw_score"), -1e9) or -1e9), reverse=True)
    return rows[:MAX_SCANNER_ROWS]


def _close_values(df: Any) -> List[float]:
    if df is None:
        return []
    try:
        series = df["Close"]
        if hasattr(series, "ndim") and int(series.ndim) > 1:
            series = series.iloc[:, 0]
        if hasattr(series, "dropna"):
            series = series.dropna()
        values = series.tolist() if hasattr(series, "tolist") else list(series)
        out = []
        for value in values:
            number = _f(value, None)
            if number is not None and number > 0:
                out.append(number)
        return out
    except Exception:
        return []


def _ret(values: List[float], bars: int) -> float | None:
    if len(values) <= bars:
        return None
    base = values[-1 - bars]
    return (values[-1] / base) - 1.0 if base > 0 else None


def _crypto_row(core: Any, symbol: str) -> Dict[str, Any]:
    fn = getattr(core, "download_prices", None)
    if not callable(fn):
        return {
            "symbol": symbol,
            "asset_class": "crypto",
            "source": "core.download_prices",
            "status": "unavailable",
            "reason": "download_prices_missing",
            "execution_authority": False,
        }
    try:
        df = fn(symbol, period="30d", interval="1h")
        closes = _close_values(df)
    except Exception as exc:
        return {
            "symbol": symbol,
            "asset_class": "crypto",
            "source": "core.download_prices",
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
            "execution_authority": False,
        }
    if len(closes) < 80:
        return {
            "symbol": symbol,
            "asset_class": "crypto",
            "source": "core.download_prices",
            "status": "insufficient_data",
            "bars": len(closes),
            "execution_authority": False,
        }

    ret24 = _ret(closes, 24)
    ret72 = _ret(closes, 72)
    sma20 = sum(closes[-20:]) / 20.0
    sma50 = sum(closes[-50:]) / 50.0
    trend20 = (closes[-1] / sma20) - 1.0 if sma20 > 0 else 0.0
    trend50 = (closes[-1] / sma50) - 1.0 if sma50 > 0 else 0.0
    hourly_returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
    recent = hourly_returns[-72:] if len(hourly_returns) >= 72 else hourly_returns
    if recent:
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / max(1, len(recent) - 1)
        daily_vol = math.sqrt(max(0.0, variance)) * math.sqrt(24.0)
    else:
        daily_vol = 0.0

    raw = (
        0.45 * float(ret24 or 0.0)
        + 0.30 * float(ret72 or 0.0)
        + 0.15 * trend20
        + 0.10 * trend50
        - 0.08 * max(0.0, daily_vol - 0.08)
    )
    return {
        "symbol": symbol,
        "asset_class": "crypto",
        "source": "core.download_prices",
        "status": "ok",
        "lifecycle": "shadow_research",
        "direction": "long_bias" if raw > 0 else "neutral_or_weak",
        "raw_score": round(raw, 6),
        "last_price": round(closes[-1], 6),
        "return_24h": round(float(ret24 or 0.0), 6),
        "return_72h": round(float(ret72 or 0.0), 6),
        "trend_vs_sma20": round(trend20, 6),
        "trend_vs_sma50": round(trend50, 6),
        "estimated_daily_volatility": round(daily_vol, 6),
        "bars": len(closes),
        "execution_authority": False,
    }


def _rank(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if _f(row.get("raw_score"), None) is None:
            continue
        groups.setdefault(str(row.get("asset_class") or "unknown"), []).append(row)

    scales = {"equity": 0.03, "etf": 0.03, "crypto": 0.08}
    for asset_class, group in groups.items():
        ordered = sorted(group, key=lambda r: float(_f(r.get("raw_score"), -1e9) or -1e9))
        count = len(ordered)
        for index, row in enumerate(ordered):
            percentile = 1.0 if count == 1 else index / float(count - 1)
            raw = float(_f(row.get("raw_score"), 0.0) or 0.0)
            scale = scales.get(asset_class, 0.05)
            positive_strength = max(0.0, min(1.0, raw / scale)) if scale > 0 else 0.0
            row["within_asset_percentile"] = round(percentile, 4)
            row["shadow_rank_score"] = round(70.0 * percentile + 30.0 * positive_strength, 2)

    ranked = sorted(
        rows,
        key=lambda row: (
            _f(row.get("shadow_rank_score"), -1e9) or -1e9,
            _f(row.get("raw_score"), -1e9) or -1e9,
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, 1):
        row["shadow_rank"] = index
    return ranked


def _build(core: Any, include_crypto: bool) -> Dict[str, Any]:
    state = _state(core)
    last_result = _d(_d(state.get("auto_runner")).get("last_result"))
    rows = _scanner_rows(core)
    provider_calls = 0
    if include_crypto:
        for symbol in CRYPTO_SYMBOLS:
            rows.append(_crypto_row(core, symbol))
            provider_calls += 1

    ranked = _rank(rows)
    counts: Dict[str, int] = {}
    for row in ranked:
        counts[str(row.get("asset_class") or "unknown")] = counts.get(str(row.get("asset_class") or "unknown"), 0) + 1

    return {
        "status": "ok",
        "overall": "pass",
        "type": "multi_asset_shadow_ranking",
        "version": VERSION,
        "generated_epoch": time.time(),
        "authority": dict(AUTHORITY),
        "comparison_quality": "exploratory_shadow_only",
        "market_context": {
            "market_mode": last_result.get("market_mode"),
            "regime": last_result.get("regime"),
            "risk_score": last_result.get("risk_score"),
            "cycle_id": last_result.get("cycle_id"),
        },
        "asset_counts": counts,
        "crypto_symbols": list(CRYPTO_SYMBOLS),
        "external_provider_calls": provider_calls,
        "cache_seconds": CACHE_SECONDS,
        "rows": ranked[:50],
        "notes": [
            "Ranking is research-only and cannot feed execution.",
            "Equity/ETF rows reuse stored authoritative scanner telemetry and do not trigger a second scan.",
            "Crypto refresh is limited to BTC-USD, ETH-USD, and SOL-USD through the existing market-data adapter.",
            "Cross-asset scores are heuristic normalization for comparison, not proven expectancy or an entry signal.",
        ],
    }


def refresh(core: Any, *, force: bool = False) -> Dict[str, Any]:
    global _LAST
    now = time.time()
    with _LOCK:
        age = now - float(_LAST.get("generated_epoch") or 0.0) if _LAST else None
        if _LAST and not force and age is not None and age < CACHE_SECONDS:
            cached = dict(_LAST)
            cached["cache_hit"] = True
            cached["cache_age_seconds"] = round(age, 2)
            return cached
    payload = _build(core, include_crypto=True)
    payload["cache_hit"] = False
    payload["cache_age_seconds"] = 0.0
    with _LOCK:
        _LAST = payload
    return dict(payload)


def status_payload(core: Any = None) -> Dict[str, Any]:
    now = time.time()
    with _LOCK:
        latest = dict(_LAST) if _LAST else {}
    age = now - float(latest.get("generated_epoch") or 0.0) if latest else None
    return {
        "status": "ok",
        "overall": "pass",
        "type": "multi_asset_shadow_ranker_status",
        "version": VERSION,
        "authority": dict(AUTHORITY),
        "configured_crypto_symbols": list(CRYPTO_SYMBOLS),
        "cache_seconds": CACHE_SECONDS,
        "latest_available": bool(latest),
        "latest_age_seconds": round(age, 2) if age is not None else None,
        "latest": latest,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    app_id = id(flask_app)
    if app_id in _REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    if "multi_asset_shadow_status" not in getattr(flask_app, "view_functions", {}):
        def multi_asset_shadow_status():
            return status_payload(core)
        flask_app.add_url_rule(
            "/paper/multi-asset-shadow-status",
            endpoint="multi_asset_shadow_status",
            view_func=multi_asset_shadow_status,
            methods=["GET"],
        )

    if "multi_asset_shadow_refresh" not in getattr(flask_app, "view_functions", {}):
        def multi_asset_shadow_refresh():
            return refresh(core, force=False)
        flask_app.add_url_rule(
            "/paper/multi-asset-shadow-refresh",
            endpoint="multi_asset_shadow_refresh",
            view_func=multi_asset_shadow_refresh,
            methods=["GET"],
        )

    _REGISTERED_APP_IDS.add(app_id)
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "routes": [
            "/paper/multi-asset-shadow-status",
            "/paper/multi-asset-shadow-refresh",
        ],
        "authority": dict(AUTHORITY),
    }
