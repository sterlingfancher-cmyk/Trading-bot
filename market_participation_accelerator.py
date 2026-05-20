"""Market participation accelerator for broad green tapes.

This layer is designed for days when the overall tape is green but the bot is
under-participating or over-selecting stretched individual names. It adds a
small benchmark-anchor candidate, usually QQQ/SPY, when the market is confirmed
constructive/risk-on and the book is underexposed.

It does not bypass downstream risk controls, entry-quality checks, cooldowns,
sector/bucket caps, or the loss-streak governor.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from typing import Any, Dict, List, Tuple

VERSION = "market-participation-accelerator-2026-05-20-v1"
PATCH_FLAG = "_market_participation_accelerator_v1"
ROUTE_APP_IDS: set[int] = set()

ENABLED = os.environ.get("MARKET_PARTICIPATION_ACCELERATOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
ANCHOR_SYMBOLS = [s.strip().upper() for s in os.environ.get("PARTICIPATION_ANCHOR_SYMBOLS", "QQQ,SPY").split(",") if s.strip()]
MIN_RISK_SCORE = int(os.environ.get("PARTICIPATION_MIN_RISK_SCORE", "62"))
MIN_ACTIVE_MODE = {"risk_on", "constructive"}
MAX_ANCHOR_POSITIONS = int(os.environ.get("PARTICIPATION_MAX_ANCHOR_POSITIONS", "1"))
MAX_TOTAL_POSITIONS_FOR_ANCHOR = int(os.environ.get("PARTICIPATION_MAX_TOTAL_POSITIONS_FOR_ANCHOR", "2"))
SCORE_BUFFER = float(os.environ.get("PARTICIPATION_SCORE_BUFFER", "0.0040"))
ANCHOR_SCORE_FLOOR = float(os.environ.get("PARTICIPATION_ANCHOR_SCORE_FLOOR", "0.0420"))
ANCHOR_ALLOC_FACTOR = float(os.environ.get("PARTICIPATION_ANCHOR_ALLOC_FACTOR", "0.85"))
REQUIRE_QQQ_UP = os.environ.get("PARTICIPATION_REQUIRE_QQQ_UP", "true").lower() not in {"0", "false", "no", "off"}
AVOID_AFTER_LOSSES = os.environ.get("PARTICIPATION_AVOID_AFTER_LOSSES", "true").lower() not in {"0", "false", "no", "off"}
MAX_LOSSES_TODAY = int(os.environ.get("PARTICIPATION_MAX_LOSSES_TODAY", "1"))


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _portfolio(m: Any) -> Dict[str, Any]:
    p = getattr(m, "portfolio", {})
    return p if isinstance(p, dict) else {}


def _positions(m: Any) -> Dict[str, Any]:
    p = _portfolio(m).get("positions") or {}
    return p if isinstance(p, dict) else {}


def _realized(m: Any) -> Dict[str, Any]:
    try:
        fn = getattr(m, "get_realized_pnl", None)
        if callable(fn):
            val = fn()
            if isinstance(val, dict):
                return val
    except Exception:
        pass
    perf = _portfolio(m).get("performance") or {}
    if isinstance(perf, dict):
        return {"losses_today": perf.get("losses_today", 0), "today": perf.get("realized_pnl_today", 0.0)}
    return {}


def _anchor_positions(m: Any) -> List[str]:
    held = []
    for sym, pos in _positions(m).items():
        bucket = pos.get("bucket") if isinstance(pos, dict) else None
        if str(sym).upper() in ANCHOR_SYMBOLS or bucket == "benchmark_etf":
            held.append(str(sym).upper())
    return held


def _base_allowed(m: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    mode = str(market.get("market_mode") or "")
    risk_score = int(_safe_float(market.get("risk_score"), 0))
    qqq_trend = str(market.get("qqq_trend") or "")
    qqq_5d = _safe_float(market.get("qqq_5d_pct"), 0.0)
    spy_5d = _safe_float(market.get("spy_5d_pct"), 0.0)
    futures = market.get("futures_bias") or {}
    breadth = market.get("breadth") or {}
    rp = _realized(m)
    losses_today = int(_safe_float(rp.get("losses_today"), 0))
    positions_count = len(_positions(m))
    anchors_held = _anchor_positions(m)

    reasons: List[str] = []
    if not ENABLED:
        reasons.append("disabled")
    if mode not in MIN_ACTIVE_MODE:
        reasons.append("market_mode_not_constructive")
    if risk_score < MIN_RISK_SCORE:
        reasons.append("risk_score_below_minimum")
    if REQUIRE_QQQ_UP and not (qqq_trend == "up" and qqq_5d > 0):
        reasons.append("qqq_not_confirmed_up")
    if futures.get("action") == "block_opening_longs" or futures.get("bias") in {"bearish", "mixed_bearish"}:
        reasons.append("futures_block_longs")
    if breadth.get("action") == "risk_off_confirmation":
        reasons.append("breadth_risk_off")
    if AVOID_AFTER_LOSSES and losses_today > MAX_LOSSES_TODAY:
        reasons.append("losses_today_above_participation_limit")
    if positions_count > MAX_TOTAL_POSITIONS_FOR_ANCHOR:
        reasons.append("book_already_exposed")
    if len(anchors_held) >= MAX_ANCHOR_POSITIONS:
        reasons.append("anchor_already_held")

    return len(reasons) == 0, {
        "mode": mode,
        "risk_score": risk_score,
        "qqq_trend": qqq_trend,
        "qqq_5d_pct": qqq_5d,
        "spy_5d_pct": spy_5d,
        "futures_action": futures.get("action"),
        "breadth_action": breadth.get("action"),
        "losses_today": losses_today,
        "positions_count": positions_count,
        "anchors_held": anchors_held,
        "reasons": reasons,
    }


def _fetch_anchor_signal(m: Any, symbol: str, market: Dict[str, Any], existing_score: float = 0.0) -> Dict[str, Any] | None:
    try:
        df = m.fetch_intraday(symbol)
        if df is None:
            return None
        arrays = m.intraday_arrays(df)
        closes = arrays.get("close")
        if closes is None or len(closes) < 35:
            return None
        px = float(closes[-1])
        score_fn = getattr(m, "signal_score", None)
        raw_score = _safe_float(score_fn(symbol, closes, market, "long"), 0.0) if callable(score_fn) else 0.0
        min_score_fn = getattr(m, "min_entry_score_for_market", None)
        min_score = _safe_float(min_score_fn(market, "long"), 0.0) if callable(min_score_fn) else 0.0
        score = max(existing_score, raw_score, min_score + SCORE_BUFFER, ANCHOR_SCORE_FLOOR)
        sector = getattr(m, "SYMBOL_SECTOR", {}).get(symbol, symbol)
        bucket_fn = getattr(m, "symbol_bucket", None)
        bucket = bucket_fn(symbol) if callable(bucket_fn) else "benchmark_etf"
        return {
            "symbol": symbol,
            "side": "long",
            "score": round(float(score), 6),
            "price": px,
            "sector": sector,
            "bucket": bucket,
            "entry_context": "benchmark_participation_anchor",
            "alloc_factor": ANCHOR_ALLOC_FACTOR,
            "participation_anchor": {
                "version": VERSION,
                "raw_score": round(float(raw_score), 6),
                "required_score": round(float(min_score), 6),
                "score_buffer": SCORE_BUFFER,
                "reason": "broad_green_market_underexposed_anchor",
            },
        }
    except Exception:
        return None


def _augment_long_signals(m: Any, long_signals: List[Dict[str, Any]], market: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allowed, context = _base_allowed(m, market)
    added: List[Dict[str, Any]] = []
    updated: List[str] = []
    if not allowed:
        return long_signals, {"allowed": False, "context": context, "added": [], "updated": []}

    existing_by_symbol = {str(s.get("symbol", "")).upper(): s for s in long_signals if isinstance(s, dict)}
    anchors_to_consider = [s for s in ANCHOR_SYMBOLS if s not in _positions(m)]
    for sym in anchors_to_consider:
        existing = existing_by_symbol.get(sym)
        existing_score = _safe_float(existing.get("score"), 0.0) if isinstance(existing, dict) else 0.0
        anchor_signal = _fetch_anchor_signal(m, sym, market, existing_score=existing_score)
        if not anchor_signal:
            continue
        if existing is not None:
            existing.update(anchor_signal)
            updated.append(sym)
        else:
            long_signals.append(anchor_signal)
            added.append(anchor_signal)
        break

    long_signals = sorted(long_signals, key=lambda x: _safe_float(x.get("score"), 0.0), reverse=True)
    return long_signals, {"allowed": True, "context": context, "added": [s.get("symbol") for s in added], "updated": updated}


def status_payload(m: Any) -> Dict[str, Any]:
    market: Dict[str, Any] = {}
    try:
        market = _portfolio(m).get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    allowed, context = _base_allowed(m, market if isinstance(market, dict) else {}) if m is not None else (False, {})
    return {
        "status": "ok",
        "type": "market_participation_accelerator_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "enabled": bool(ENABLED),
        "patched": bool(getattr(m, PATCH_FLAG, False)) if m is not None else False,
        "allowed_now": bool(allowed),
        "context": context,
        "anchor_symbols": ANCHOR_SYMBOLS,
        "anchor_alloc_factor": ANCHOR_ALLOC_FACTOR,
        "trade_authority": "scanner_candidate_anchor_only",
        "notes": [
            "Adds a benchmark anchor candidate only when the tape is constructive/risk-on and the book is underexposed.",
            "Does not bypass entry quality, loss-streak governor, risk halts, cooldowns, sector caps, or bucket caps.",
        ],
    }


def apply(m: Any) -> Dict[str, Any]:
    if m is None:
        return {"status": "warn", "version": VERSION, "reason": "missing_core_module"}
    if getattr(m, PATCH_FLAG, False):
        return {"status": "ok", "version": VERSION, "already_applied": True}
    if not ENABLED:
        setattr(m, PATCH_FLAG, True)
        return {"status": "ok", "version": VERSION, "enabled": False}

    original_scan = getattr(m, "scan_signals", None)
    if not callable(original_scan):
        setattr(m, PATCH_FLAG, True)
        return {"status": "warn", "version": VERSION, "reason": "scan_signals_missing"}

    setattr(m, "_participation_original_scan_signals", original_scan)

    def patched_scan_signals(market: Dict[str, Any]):
        long_signals, short_signals, rejected = original_scan(market)
        try:
            long_signals = list(long_signals or [])
            long_signals, info = _augment_long_signals(m, long_signals, market or {})
            try:
                _portfolio(m)["market_participation_accelerator"] = info
            except Exception:
                pass
        except Exception as exc:
            rejected = list(rejected or [])
            rejected.append({"symbol": "MARKET_PARTICIPATION", "reason": "participation_accelerator_error", "error": str(exc), "version": VERSION})
        return long_signals, short_signals, rejected

    m.scan_signals = patched_scan_signals
    setattr(m, PATCH_FLAG, True)
    return {"status": "ok", "version": VERSION, "enabled": True, "patched": ["scan_signals"]}


def _add_self_check_endpoints() -> Dict[str, Any]:
    try:
        import self_check
        light = getattr(self_check, "LIGHT_ENDPOINTS", None)
        if not isinstance(light, list):
            return {"status": "warn", "reason": "LIGHT_ENDPOINTS_missing"}
        path = "/paper/market-participation-accelerator-status"
        if not any(isinstance(row, dict) and row.get("path") == path for row in light):
            light.append({"path": path, "category": "governance", "required": False})
            return {"status": "ok", "added": [path], "count": len(light)}
        return {"status": "ok", "added": [], "count": len(light)}
    except Exception as exc:
        return {"status": "warn", "error": str(exc)}


def register_routes(flask_app: Any, m: Any | None = None) -> Dict[str, Any]:
    if flask_app is None or id(flask_app) in ROUTE_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify

    core = m
    if core is not None:
        apply(core)

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/market-participation-accelerator-status" not in existing:
        flask_app.add_url_rule(
            "/paper/market-participation-accelerator-status",
            "paper_market_participation_accelerator_status",
            lambda: jsonify(status_payload(core)),
        )

    ROUTE_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "registered": True, "routes": ["/paper/market-participation-accelerator-status"], "self_check": _add_self_check_endpoints()}
