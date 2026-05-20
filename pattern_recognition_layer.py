"""Quantified pattern recognition layer for the paper-trading bot.

The layer is intentionally conservative:
- It does not place standalone trades.
- It does not bypass risk controls, cooldowns, sector/bucket limits, or self-defense.
- It only adds a bounded score modifier plus diagnostics when a symbol already appears
  in the scanner/relative-strength workflow.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import time
from typing import Any, Dict, List, Tuple

import numpy as np

VERSION = "pattern-recognition-structure-layer-2026-05-19-v1"
PATCH_FLAG = "_pattern_recognition_layer_v1"
ROUTE_APP_IDS: set[int] = set()

ENABLED = os.environ.get("PATTERN_RECOGNITION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
ADVISORY_ONLY = os.environ.get("PATTERN_RECOGNITION_ADVISORY_ONLY", "false").lower() in {"1", "true", "yes", "on"}

MAX_SCORE_BONUS = float(os.environ.get("PATTERN_MAX_SCORE_BONUS", "0.0045"))
MAX_SCORE_PENALTY = float(os.environ.get("PATTERN_MAX_SCORE_PENALTY", "0.0060"))
MIN_CONFIDENCE_FOR_BONUS = float(os.environ.get("PATTERN_MIN_CONFIDENCE_FOR_BONUS", "0.55"))
SCAN_ROUTE_MAX_SYMBOLS = int(os.environ.get("PATTERN_ROUTE_MAX_SYMBOLS", "90"))
CACHE_TTL_SECONDS = int(os.environ.get("PATTERN_CACHE_TTL_SECONDS", "120"))

RS_PULLBACK_MAX_ABOVE_MA20 = float(os.environ.get("PATTERN_RS_PULLBACK_MAX_ABOVE_MA20", "0.018"))
RS_PULLBACK_MAX_ABOVE_VWAP = float(os.environ.get("PATTERN_RS_PULLBACK_MAX_ABOVE_VWAP", "0.020"))
VOL_CONTRACTION_RATIO = float(os.environ.get("PATTERN_VOL_CONTRACTION_RATIO", "0.72"))
BREAKOUT_LOOKBACK = int(os.environ.get("PATTERN_BREAKOUT_LOOKBACK", "20"))
HIGHER_LOW_LOOKBACK = int(os.environ.get("PATTERN_HIGHER_LOW_LOOKBACK", "9"))
FAILED_BREAKDOWN_LOOKBACK = int(os.environ.get("PATTERN_FAILED_BREAKDOWN_LOOKBACK", "18"))
GAP_MIN_PCT = float(os.environ.get("PATTERN_GAP_MIN_PCT", "0.012"))
EOD_STRENGTH_MIN_BARS_FROM_CLOSE = int(os.environ.get("PATTERN_EOD_STRENGTH_MIN_BARS_FROM_CLOSE", "12"))
CHASE_MAX_FROM_DAY_OPEN = float(os.environ.get("PATTERN_CHASE_MAX_FROM_DAY_OPEN", "0.060"))
CHASE_MAX_FROM_MA20 = float(os.environ.get("PATTERN_CHASE_MAX_FROM_MA20", "0.040"))
CHASE_MAX_FROM_VWAP = float(os.environ.get("PATTERN_CHASE_MAX_FROM_VWAP", "0.045"))
NEAR_HIGH_FACTOR = float(os.environ.get("PATTERN_NEAR_HIGH_FACTOR", "0.997"))

_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}


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


def _clean(arr: Any) -> np.ndarray:
    try:
        a = np.asarray(arr).astype(float).flatten()
        return a[~np.isnan(a)]
    except Exception:
        return np.array([])


def _ma(values: np.ndarray, bars: int) -> float | None:
    values = _clean(values)
    if len(values) < bars:
        return None
    return float(np.mean(values[-bars:]))


def _pct(values: np.ndarray, bars: int) -> float:
    values = _clean(values)
    if len(values) <= bars:
        return 0.0
    base = float(values[-bars])
    latest = float(values[-1])
    if base <= 0 or latest <= 0:
        return 0.0
    return (latest / base) - 1.0


def _session_bars(length: int) -> int:
    return max(1, min(int(length or 0), 78))


def _fetch_arrays(m: Any, symbol: str) -> Dict[str, np.ndarray] | None:
    try:
        df = m.fetch_intraday(symbol)
        if df is None:
            return None
        arrays = m.intraday_arrays(df)
        if not isinstance(arrays, dict) or len(_clean(arrays.get("close"))) < 35:
            return None
        return arrays
    except Exception:
        return None


def _session_change(arrays: Dict[str, np.ndarray] | None) -> float:
    if not isinstance(arrays, dict):
        return 0.0
    closes = _clean(arrays.get("close"))
    opens = _clean(arrays.get("open"))
    if len(closes) < 2 or len(opens) < 1:
        return 0.0
    bars = _session_bars(len(closes))
    try:
        session_open = float(opens[-bars]) if len(opens) >= bars else float(opens[0])
        px = float(closes[-1])
        return (px / session_open) - 1.0 if session_open > 0 and px > 0 else 0.0
    except Exception:
        return 0.0


def _vwap(closes: np.ndarray, vols: np.ndarray) -> float | None:
    closes = _clean(closes)
    vols = _clean(vols)
    if len(closes) < 2 or len(vols) < 2:
        return None
    n = min(_session_bars(len(closes)), len(closes), len(vols))
    c = closes[-n:]
    v = vols[-n:]
    denom = float(np.sum(v))
    return float(np.sum(c * v) / denom) if denom > 0 else None


def _volume_ratio(vols: np.ndarray) -> float:
    vols = _clean(vols)
    if len(vols) < 18:
        return 0.0
    recent = float(np.sum(vols[-6:]))
    base = vols[-60:-6] if len(vols) >= 66 else vols[:-6]
    if len(base) == 0:
        return 0.0
    base_avg_6 = float(np.mean(base)) * 6.0
    return recent / base_avg_6 if base_avg_6 > 0 else 0.0


def _range_percent(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, lookback: int) -> float:
    highs = _clean(highs)
    lows = _clean(lows)
    closes = _clean(closes)
    n = min(len(highs), len(lows), len(closes))
    if n < lookback + 2:
        return 0.0
    h = float(np.max(highs[-lookback:]))
    l = float(np.min(lows[-lookback:]))
    px = max(float(closes[-1]), 0.01)
    return (h - l) / px


def _market_benchmark_arrays(m: Any) -> Tuple[Dict[str, np.ndarray] | None, Dict[str, np.ndarray] | None]:
    return _fetch_arrays(m, "QQQ"), _fetch_arrays(m, "SPY")


def _pattern_evaluation(m: Any, symbol: str, side: str = "long", arrays: Dict[str, np.ndarray] | None = None, market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    symbol = str(symbol or "").upper().strip()
    side = str(side or "long").lower()
    market = market or {}
    arrays = arrays or _fetch_arrays(m, symbol)
    if not symbol or arrays is None:
        return {
            "symbol": symbol,
            "side": side,
            "status": "no_data",
            "patterns_detected": [],
            "bullish_pattern_count": 0,
            "bearish_or_chase_pattern_count": 0,
            "pattern_score_bonus": 0.0,
            "pattern_score_penalty": 0.0,
            "net_pattern_score_adjustment": 0.0,
            "pattern_confidence": 0.0,
            "pattern_bias": "unknown",
            "reason": "insufficient_intraday_data",
            "version": VERSION,
        }

    closes = _clean(arrays.get("close"))
    opens = _clean(arrays.get("open"))
    highs = _clean(arrays.get("high"))
    lows = _clean(arrays.get("low"))
    vols = _clean(arrays.get("volume"))
    if len(closes) < 35:
        return {
            "symbol": symbol,
            "side": side,
            "status": "no_data",
            "patterns_detected": [],
            "pattern_score_bonus": 0.0,
            "pattern_score_penalty": 0.0,
            "net_pattern_score_adjustment": 0.0,
            "pattern_confidence": 0.0,
            "pattern_bias": "unknown",
            "reason": "not_enough_bars",
            "version": VERSION,
        }

    px = float(closes[-1])
    ma8 = _ma(closes, 8)
    ma20 = _ma(closes, 20)
    ma34 = _ma(closes, 34)
    vwap = _vwap(closes, vols)
    session_bars = _session_bars(len(closes))
    session_open = float(opens[-session_bars]) if len(opens) >= session_bars else float(opens[0]) if len(opens) else px
    session_high = float(np.max(highs[-session_bars:])) if len(highs) >= session_bars else float(np.max(closes[-session_bars:]))
    session_low = float(np.min(lows[-session_bars:])) if len(lows) >= session_bars else float(np.min(closes[-session_bars:]))
    day_move = _session_change(arrays)
    vol_ratio = _volume_ratio(vols)

    qqq_arrays, spy_arrays = _market_benchmark_arrays(m)
    qqq_day = _session_change(qqq_arrays) if qqq_arrays else 0.0
    spy_day = _session_change(spy_arrays) if spy_arrays else 0.0
    rel_edge_qqq = day_move - qqq_day
    rel_edge_spy = day_move - spy_day

    trend_up = bool(ma8 and ma20 and ma34 and px > ma20 and ma8 >= ma20 * 0.997 and ma20 >= ma34 * 0.990)
    above_vwap = bool(vwap and px >= vwap)
    near_ma20 = bool(ma20 and abs((px / ma20) - 1.0) <= RS_PULLBACK_MAX_ABOVE_MA20)
    near_vwap = bool(vwap and abs((px / vwap) - 1.0) <= RS_PULLBACK_MAX_ABOVE_VWAP)
    pulled_back_from_high = bool(session_high and px <= session_high * (1.0 - 0.004))
    reclaimed_fast = bool(ma8 and len(closes) >= 2 and closes[-1] > ma8 and closes[-2] <= ma8 * 1.001)

    patterns: List[Dict[str, Any]] = []
    penalties: List[Dict[str, Any]] = []

    def add(name: str, weight: float, detail: str) -> None:
        patterns.append({"name": name, "weight": round(float(weight), 4), "detail": detail})

    def penalize(name: str, weight: float, detail: str) -> None:
        penalties.append({"name": name, "weight": round(float(weight), 4), "detail": detail})

    if side == "long":
        if trend_up and above_vwap and rel_edge_qqq >= 0.008 and (near_ma20 or near_vwap or pulled_back_from_high or reclaimed_fast):
            add("relative_strength_pullback", 1.00, "outperforming QQQ while holding VWAP/MA structure without chasing the high")

        recent_range = _range_percent(highs, lows, closes, 8)
        base_range = _range_percent(highs[:-6], lows[:-6], closes[:-6], 24) if len(closes) > 40 else 0.0
        recent_high = float(np.max(highs[-BREAKOUT_LOOKBACK-1:-1])) if len(highs) > BREAKOUT_LOOKBACK + 2 else session_high
        broke_recent_high = px > recent_high and len(highs) > BREAKOUT_LOOKBACK + 2
        if base_range > 0 and recent_range > 0 and recent_range <= base_range * VOL_CONTRACTION_RATIO and broke_recent_high and vol_ratio >= 1.0:
            add("volatility_contraction_breakout", 0.90, "range compressed, then price expanded through recent resistance with volume confirmation")

        prev_breakout_level = float(np.max(highs[-BREAKOUT_LOOKBACK-4:-4])) if len(highs) > BREAKOUT_LOOKBACK + 6 else 0.0
        retested_level = bool(prev_breakout_level and np.min(lows[-4:]) <= prev_breakout_level * 1.006 and px >= prev_breakout_level)
        if trend_up and prev_breakout_level and retested_level and px > (vwap or px * 2):
            add("breakout_retest_hold", 0.85, "prior breakout area was retested and held above VWAP")

        if len(lows) >= HIGHER_LOW_LOOKBACK + 3 and trend_up:
            swing1 = float(np.min(lows[-HIGHER_LOW_LOOKBACK:-6]))
            swing2 = float(np.min(lows[-6:-2]))
            swing3 = float(np.min(lows[-3:]))
            if swing2 > swing1 * 0.998 and swing3 >= swing2 * 0.995 and px > (ma8 or px * 2):
                add("higher_low_continuation", 0.75, "successive intraday pullbacks are holding higher lows above trend support")

        if ma20 and len(lows) >= FAILED_BREAKDOWN_LOOKBACK:
            broke_below = float(np.min(lows[-FAILED_BREAKDOWN_LOOKBACK:-3])) < ma20 * 0.992
            reclaimed = px > ma20 and closes[-2] <= ma20 * 1.003
            if broke_below and reclaimed and rel_edge_qqq >= 0:
                add("failed_breakdown_reclaim", 0.80, "brief breakdown under MA20 was reclaimed while relative strength stayed positive")

        if len(opens) >= session_bars + 1 and session_open > 0:
            prev_close = float(closes[-session_bars-1]) if len(closes) > session_bars else float(closes[0])
            gap_pct = (session_open / prev_close) - 1.0 if prev_close > 0 else 0.0
            if gap_pct >= GAP_MIN_PCT and px >= session_open and above_vwap and vol_ratio >= 0.9:
                add("gap_hold", 0.65, "gap is holding above session open and VWAP")

        minutes_to_close = None
        try:
            clock = m.market_clock()
            if isinstance(clock, dict):
                minutes_to_close = _safe_float(clock.get("minutes_to_close"), None)
        except Exception:
            minutes_to_close = None
        if minutes_to_close is not None and 0 <= minutes_to_close <= EOD_STRENGTH_MIN_BARS_FROM_CLOSE * 5:
            if px >= session_high * 0.985 and rel_edge_qqq > 0 and trend_up:
                add("eod_strength_hold", 0.60, "holding near session highs into the close while outperforming QQQ")

        from_open = (px / session_open) - 1.0 if session_open > 0 else 0.0
        from_ma20 = (px / ma20) - 1.0 if ma20 and ma20 > 0 else 0.0
        from_vwap = (px / vwap) - 1.0 if vwap and vwap > 0 else 0.0
        near_high_after_move = bool(px >= session_high * NEAR_HIGH_FACTOR and from_open >= 0.035)
        if from_open > CHASE_MAX_FROM_DAY_OPEN or from_ma20 > CHASE_MAX_FROM_MA20 or from_vwap > CHASE_MAX_FROM_VWAP or near_high_after_move:
            penalize("overextension_chase_risk", 1.00, "price is stretched from open, VWAP, MA20, or pinned near the high after a large move")
        if not trend_up and day_move < 0:
            penalize("weak_structure", 0.65, "long setup lacks trend alignment")
    else:
        trend_down = bool(ma8 and ma20 and ma34 and px < ma20 and ma8 <= ma20 * 1.003 and ma20 <= ma34 * 1.010)
        if trend_down and px < (vwap or px * -1) and rel_edge_qqq <= -0.006:
            add("relative_weakness_breakdown", 0.80, "short candidate is underperforming QQQ and trading below VWAP/MA structure")
        if trend_up and rel_edge_qqq > 0:
            penalize("short_against_relative_strength", 0.80, "short conflicts with positive relative strength")

    raw_bonus = sum(float(p["weight"]) for p in patterns)
    raw_penalty = sum(float(p["weight"]) for p in penalties)
    confidence = max(0.0, min(1.0, (raw_bonus / 3.0) + (0.10 if vol_ratio >= 1.0 else 0.0) + (0.08 if abs(rel_edge_qqq) >= 0.01 else 0.0)))
    score_bonus = 0.0
    if confidence >= MIN_CONFIDENCE_FOR_BONUS and raw_bonus > 0:
        score_bonus = min(MAX_SCORE_BONUS, MAX_SCORE_BONUS * (raw_bonus / 2.5))
    score_penalty = min(MAX_SCORE_PENALTY, MAX_SCORE_PENALTY * (raw_penalty / 1.5)) if raw_penalty > 0 else 0.0
    net = score_bonus - score_penalty

    if raw_bonus > 0 and raw_penalty == 0:
        bias = "bullish_continuation" if side == "long" else "bearish_continuation"
    elif raw_bonus > 0 and raw_penalty > 0:
        bias = "mixed_structure"
    elif raw_penalty > 0:
        bias = "chase_or_weak_structure"
    else:
        bias = "neutral"

    return {
        "symbol": symbol,
        "side": side,
        "status": "ok",
        "version": VERSION,
        "pattern_bias": bias,
        "patterns_detected": [p["name"] for p in patterns],
        "pattern_details": patterns,
        "risk_patterns": [p["name"] for p in penalties],
        "risk_pattern_details": penalties,
        "bullish_pattern_count": len(patterns),
        "bearish_or_chase_pattern_count": len(penalties),
        "pattern_confidence": round(float(confidence), 4),
        "pattern_score_bonus": round(float(score_bonus), 6),
        "pattern_score_penalty": round(float(score_penalty), 6),
        "net_pattern_score_adjustment": round(float(net), 6),
        "advisory_only": bool(ADVISORY_ONLY),
        "metrics": {
            "price": round(px, 4),
            "day_move_pct": round(day_move * 100.0, 2),
            "qqq_day_pct": round(qqq_day * 100.0, 2),
            "spy_day_pct": round(spy_day * 100.0, 2),
            "relative_edge_qqq_pct": round(rel_edge_qqq * 100.0, 2),
            "relative_edge_spy_pct": round(rel_edge_spy * 100.0, 2),
            "volume_ratio": round(vol_ratio, 2),
            "ma8": round(float(ma8), 4) if ma8 else None,
            "ma20": round(float(ma20), 4) if ma20 else None,
            "ma34": round(float(ma34), 4) if ma34 else None,
            "vwap": round(float(vwap), 4) if vwap else None,
            "session_open": round(session_open, 4),
            "session_high": round(session_high, 4),
            "session_low": round(session_low, 4),
            "trend_up": bool(trend_up),
            "above_vwap": bool(above_vwap),
            "near_ma20": bool(near_ma20),
            "near_vwap": bool(near_vwap),
            "pulled_back_from_high": bool(pulled_back_from_high),
        },
    }


def evaluate_symbol(m: Any, symbol: str, side: str = "long", market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _pattern_evaluation(m, symbol, side=side, market=market)


def _symbols_for_route(m: Any) -> List[str]:
    out: List[str] = []
    try:
        for s in list(getattr(m, "UNIVERSE", []) or []):
            sym = str(s).upper().strip()
            if sym and sym not in out:
                out.append(sym)
    except Exception:
        pass
    try:
        for s in ["SPY", "QQQ"] + list((getattr(m, "portfolio", {}) or {}).get("positions", {}).keys()):
            sym = str(s).upper().strip()
            if sym and sym not in out:
                out.append(sym)
    except Exception:
        pass
    return out[:SCAN_ROUTE_MAX_SYMBOLS]


def leaders_payload(m: Any, force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and _CACHE.get("payload") and now - float(_CACHE.get("ts", 0.0)) < CACHE_TTL_SECONDS:
        return dict(_CACHE["payload"])
    try:
        market = getattr(m, "portfolio", {}).get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    rows = []
    for symbol in _symbols_for_route(m):
        try:
            if symbol in {"SPY", "QQQ"}:
                continue
            row = evaluate_symbol(m, symbol, "long", market=market)
            if row.get("status") == "ok":
                rows.append(row)
        except Exception as exc:
            rows.append({"symbol": symbol, "status": "error", "error": str(exc), "version": VERSION})
    rows = sorted(rows, key=lambda r: (_safe_float(r.get("net_pattern_score_adjustment")), _safe_float(r.get("pattern_confidence"))), reverse=True)
    top_positive = [r for r in rows if _safe_float(r.get("net_pattern_score_adjustment")) > 0][:20]
    top_risk = sorted([r for r in rows if r.get("risk_patterns")], key=lambda r: _safe_float(r.get("pattern_score_penalty")), reverse=True)[:20]
    payload = {
        "status": "ok",
        "type": "pattern_leaders",
        "version": VERSION,
        "generated_local": _now_text(),
        "enabled": bool(ENABLED),
        "advisory_only": bool(ADVISORY_ONLY),
        "trade_authority": "bounded_score_modifier_only",
        "symbols_checked": len(rows),
        "top_positive_patterns": top_positive,
        "top_chase_or_weak_patterns": top_risk,
        "recommended_action": "Use high-confidence pattern rows to rank existing scanner candidates; do not let a pattern bypass risk controls or force standalone entries.",
    }
    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return dict(payload)


def status_payload(m: Any) -> Dict[str, Any]:
    payload = leaders_payload(m, force=False)
    return {
        "status": "ok",
        "type": "pattern_recognition_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "patched": bool(getattr(m, PATCH_FLAG, False)),
        "enabled": bool(ENABLED),
        "advisory_only": bool(ADVISORY_ONLY),
        "trade_authority": "bounded_score_modifier_only",
        "max_score_bonus": MAX_SCORE_BONUS,
        "max_score_penalty": MAX_SCORE_PENALTY,
        "patterns_supported": [
            "relative_strength_pullback",
            "volatility_contraction_breakout",
            "breakout_retest_hold",
            "higher_low_continuation",
            "failed_breakdown_reclaim",
            "gap_hold",
            "eod_strength_hold",
            "overextension_chase_risk",
        ],
        "leaders_count": len(payload.get("top_positive_patterns", [])),
        "top_symbols": [r.get("symbol") for r in payload.get("top_positive_patterns", [])[:10]],
        "risk_symbols": [r.get("symbol") for r in payload.get("top_chase_or_weak_patterns", [])[:10]],
        "notes": [
            "Pattern recognition modifies scanner scores only within bounded limits.",
            "No pattern can override halts, self-defense, cooldowns, sector caps, bucket caps, or entry quality controls.",
        ],
    }


def decision_diagnostic_payload(m: Any) -> Dict[str, Any]:
    try:
        market = getattr(m, "portfolio", {}).get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    rows = []
    try:
        long_signals, short_signals, rejected = getattr(m, "_pattern_original_scan_signals", m.scan_signals)(market)
    except Exception:
        long_signals, short_signals, rejected = [], [], []
    for item in list(long_signals or [])[:25]:
        if isinstance(item, dict):
            symbol = str(item.get("symbol", "")).upper()
            rows.append({
                "symbol": symbol,
                "side": item.get("side", "long"),
                "base_score": item.get("score"),
                "pattern": evaluate_symbol(m, symbol, item.get("side", "long"), market=market),
            })
    return {
        "status": "ok",
        "type": "pattern_decision_diagnostic",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_mode": market.get("market_mode"),
        "rows": rows,
        "rejected_sample_count": len(rejected or []),
    }


def outcome_scorecard_payload(m: Any) -> Dict[str, Any]:
    trades = []
    try:
        trades = list((getattr(m, "portfolio", {}) or {}).get("trades", []) or [])
    except Exception:
        trades = []
    groups: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        if not isinstance(t, dict):
            continue
        pat = t.get("pattern_recognition") or t.get("pattern_context") or {}
        if not isinstance(pat, dict):
            pat = {}
        names = pat.get("patterns_detected") or []
        if not names and isinstance(t.get("pattern_names"), list):
            names = t.get("pattern_names")
        if not names:
            continue
        pnl = _safe_float(t.get("pnl_dollars"), 0.0)
        action = str(t.get("action", ""))
        for name in names:
            g = groups.setdefault(str(name), {"pattern": str(name), "rows": 0, "execution_rows": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0})
            g["rows"] += 1
            if action in {"exit", "partial_exit"}:
                g["execution_rows"] += 1
                g["net_pnl"] += pnl
                if pnl >= 0:
                    g["wins"] += 1
                    g["gross_profit"] += pnl
                else:
                    g["losses"] += 1
                    g["gross_loss"] += pnl
    scorecards = []
    for g in groups.values():
        exec_rows = int(g.get("execution_rows", 0))
        wins = int(g.get("wins", 0))
        gross_loss_abs = abs(float(g.get("gross_loss", 0.0)))
        scorecards.append({
            "pattern": g["pattern"],
            "rows": int(g.get("rows", 0)),
            "execution_rows": exec_rows,
            "wins": wins,
            "losses": int(g.get("losses", 0)),
            "win_rate": round(wins / exec_rows, 4) if exec_rows else None,
            "net_pnl": round(float(g.get("net_pnl", 0.0)), 2),
            "profit_factor": round(float(g.get("gross_profit", 0.0)) / gross_loss_abs, 4) if gross_loss_abs > 0 else (999.0 if float(g.get("gross_profit", 0.0)) > 0 else None),
            "sample_confidence": "insufficient_data" if exec_rows < 20 else "developing" if exec_rows < 60 else "usable",
        })
    scorecards = sorted(scorecards, key=lambda x: (_safe_float(x.get("net_pnl")), _safe_float(x.get("win_rate"), -1)), reverse=True)
    return {
        "status": "ok",
        "type": "pattern_outcome_scorecard",
        "version": VERSION,
        "generated_local": _now_text(),
        "scorecards": scorecards,
        "recommendation": "Keep pattern authority bounded until each pattern has enough closed trades and walk-forward validation.",
    }


def _apply_adjustment(signal: Dict[str, Any], pat: Dict[str, Any]) -> None:
    if not isinstance(signal, dict) or not isinstance(pat, dict):
        return
    base_score = _safe_float(signal.get("score"), 0.0)
    adjustment = _safe_float(pat.get("net_pattern_score_adjustment"), 0.0)
    if ADVISORY_ONLY:
        adjustment = 0.0
    adjusted = max(0.0, base_score + adjustment)
    signal["pattern_recognition"] = pat
    signal["pattern_score_adjustment"] = round(adjustment, 6)
    signal["pre_pattern_score"] = round(base_score, 6)
    signal["score"] = round(adjusted, 6)
    if pat.get("patterns_detected"):
        signal["entry_context"] = signal.get("entry_context") or "pattern_recognition_ranked"
    if pat.get("pattern_bias"):
        signal["pattern_bias"] = pat.get("pattern_bias")


def apply(m: Any) -> Dict[str, Any]:
    if m is None:
        return {"status": "warn", "version": VERSION, "reason": "missing_core_module"}
    if getattr(m, PATCH_FLAG, False):
        return {"status": "ok", "version": VERSION, "already_applied": True}
    if not ENABLED:
        setattr(m, PATCH_FLAG, True)
        return {"status": "ok", "version": VERSION, "enabled": False}

    patched: List[str] = []
    original_scan = getattr(m, "scan_signals", None)
    if callable(original_scan):
        setattr(m, "_pattern_original_scan_signals", original_scan)

        def patched_scan_signals(market: Dict[str, Any]):
            long_signals, short_signals, rejected = original_scan(market)
            try:
                for sig in long_signals or []:
                    if isinstance(sig, dict):
                        pat = evaluate_symbol(m, sig.get("symbol"), sig.get("side", "long"), market=market)
                        _apply_adjustment(sig, pat)
                for sig in short_signals or []:
                    if isinstance(sig, dict):
                        pat = evaluate_symbol(m, sig.get("symbol"), sig.get("side", "short"), market=market)
                        _apply_adjustment(sig, pat)
                long_signals = sorted(long_signals or [], key=lambda x: x.get("score", 0.0), reverse=True)
                short_signals = sorted(short_signals or [], key=lambda x: x.get("score", 0.0), reverse=True)
            except Exception as exc:
                try:
                    rejected.append({"symbol": "PATTERN_RECOGNITION", "reason": "pattern_patch_error", "error": str(exc)})
                except Exception:
                    pass
            return long_signals, short_signals, rejected

        m.scan_signals = patched_scan_signals
        patched.append("scan_signals")

    original_entry_quality = getattr(m, "entry_quality_check", None)
    if callable(original_entry_quality):
        setattr(m, "_pattern_original_entry_quality_check", original_entry_quality)

        def patched_entry_quality_check(signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], exclude_symbol: str | None = None):
            pat = signal.get("pattern_recognition") if isinstance(signal, dict) else None
            if not isinstance(pat, dict) and isinstance(signal, dict):
                pat = evaluate_symbol(m, signal.get("symbol"), signal.get("side", "long"), market=market)
                signal["pattern_recognition"] = pat
            ok, info = original_entry_quality(signal, params, market, exclude_symbol=exclude_symbol)
            if isinstance(info, dict) and isinstance(pat, dict):
                info = dict(info)
                info["pattern_recognition"] = {
                    "pattern_bias": pat.get("pattern_bias"),
                    "patterns_detected": pat.get("patterns_detected", []),
                    "risk_patterns": pat.get("risk_patterns", []),
                    "pattern_confidence": pat.get("pattern_confidence"),
                    "net_pattern_score_adjustment": pat.get("net_pattern_score_adjustment"),
                    "authority": "diagnostic_attached_to_entry_quality",
                }
            return ok, info

        m.entry_quality_check = patched_entry_quality_check
        patched.append("entry_quality_check")

    original_enter = getattr(m, "enter_position", None)
    if callable(original_enter):
        setattr(m, "_pattern_original_enter_position", original_enter)

        def patched_enter_position(signal: Dict[str, Any], params: Dict[str, Any], market_mode: str | None = None):
            result = original_enter(signal, params, market_mode=market_mode)
            try:
                symbol = str(signal.get("symbol", "")).upper()
                pat = signal.get("pattern_recognition")
                if symbol and isinstance(pat, dict):
                    pos = (getattr(m, "portfolio", {}) or {}).get("positions", {}).get(symbol)
                    if isinstance(pos, dict):
                        pos["pattern_recognition"] = pat
                        pos["pattern_names"] = pat.get("patterns_detected", [])
                    trades = (getattr(m, "portfolio", {}) or {}).get("trades", [])
                    if trades and isinstance(trades[-1], dict) and trades[-1].get("action") == "entry" and trades[-1].get("symbol") == symbol:
                        trades[-1]["pattern_recognition"] = {
                            "patterns_detected": pat.get("patterns_detected", []),
                            "risk_patterns": pat.get("risk_patterns", []),
                            "pattern_bias": pat.get("pattern_bias"),
                            "pattern_confidence": pat.get("pattern_confidence"),
                            "net_pattern_score_adjustment": pat.get("net_pattern_score_adjustment"),
                        }
            except Exception:
                pass
            return result

        m.enter_position = patched_enter_position
        patched.append("enter_position")

    original_exit = getattr(m, "exit_position", None)
    if callable(original_exit):
        setattr(m, "_pattern_original_exit_position", original_exit)

        def patched_exit_position(symbol: str, px: float, reason: str, market_mode: str | None = None, extra: Dict[str, Any] | None = None):
            extra = dict(extra or {})
            try:
                pos = (getattr(m, "portfolio", {}) or {}).get("positions", {}).get(symbol)
                if isinstance(pos, dict) and isinstance(pos.get("pattern_recognition"), dict):
                    pat = pos.get("pattern_recognition")
                    extra.setdefault("pattern_recognition", {
                        "patterns_detected": pat.get("patterns_detected", []),
                        "risk_patterns": pat.get("risk_patterns", []),
                        "pattern_bias": pat.get("pattern_bias"),
                        "pattern_confidence": pat.get("pattern_confidence"),
                        "net_pattern_score_adjustment": pat.get("net_pattern_score_adjustment"),
                    })
                    extra.setdefault("pattern_names", pat.get("patterns_detected", []))
            except Exception:
                pass
            return original_exit(symbol, px, reason, market_mode=market_mode, extra=extra)

        m.exit_position = patched_exit_position
        patched.append("exit_position")

    setattr(m, PATCH_FLAG, True)
    return {"status": "ok", "version": VERSION, "enabled": True, "patched": patched, "authority": "bounded_score_modifier_only"}


def _add_self_check_endpoints() -> Dict[str, Any]:
    try:
        import self_check
        light = getattr(self_check, "LIGHT_ENDPOINTS", None)
        if not isinstance(light, list):
            return {"status": "warn", "reason": "LIGHT_ENDPOINTS_missing"}
        additions = [
            ("/paper/pattern-recognition-status", "governance", False),
            ("/paper/pattern-leaders", "governance", False),
            ("/paper/pattern-decision-diagnostic", "governance", False),
            ("/paper/pattern-outcome-scorecard", "governance", False),
        ]
        added = []
        for path, category, required in additions:
            if not any(isinstance(row, dict) and row.get("path") == path for row in light):
                light.append({"path": path, "category": category, "required": required})
                added.append(path)
        return {"status": "ok", "added": added, "count": len(light)}
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

    def _core() -> Any:
        return core

    if "/paper/pattern-recognition-status" not in existing:
        flask_app.add_url_rule("/paper/pattern-recognition-status", "paper_pattern_recognition_status", lambda: jsonify(status_payload(_core())))
    if "/paper/pattern-leaders" not in existing:
        flask_app.add_url_rule("/paper/pattern-leaders", "paper_pattern_leaders", lambda: jsonify(leaders_payload(_core(), force=True)))
    if "/paper/pattern-decision-diagnostic" not in existing:
        flask_app.add_url_rule("/paper/pattern-decision-diagnostic", "paper_pattern_decision_diagnostic", lambda: jsonify(decision_diagnostic_payload(_core())))
    if "/paper/pattern-outcome-scorecard" not in existing:
        flask_app.add_url_rule("/paper/pattern-outcome-scorecard", "paper_pattern_outcome_scorecard", lambda: jsonify(outcome_scorecard_payload(_core())))

    ROUTE_APP_IDS.add(id(flask_app))
    self_check_result = _add_self_check_endpoints()
    return {
        "status": "ok",
        "version": VERSION,
        "registered": True,
        "routes": [
            "/paper/pattern-recognition-status",
            "/paper/pattern-leaders",
            "/paper/pattern-decision-diagnostic",
            "/paper/pattern-outcome-scorecard",
        ],
        "self_check": self_check_result,
    }
