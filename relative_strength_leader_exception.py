"""Relative-strength leader exception plus dynamic opportunity discovery.

Adds a conservative two-layer scanner:
1) a curated relative-strength watchlist for known AI/semis/compute leaders, and
2) a broader dynamic discovery pool that can promote outside tickers into the
live scan when they show strong relative strength, volume, trend, and no-chase
pullback quality.

The module is intentionally reduced-size and bounded. It does not disable app.py
risk controls, self-defense, position limits, cooldowns, or journal/state guards.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, List, Tuple

import numpy as np

VERSION = "relative-strength-dynamic-discovery-2026-05-19-v2"
PATCH_FLAG = "_relative_strength_dynamic_discovery_patch_v2"
ROUTE_APP_IDS: set[int] = set()

_ENABLED = os.environ.get("RS_LEADER_EXCEPTION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
DISCOVERY_ENABLED = os.environ.get("DYNAMIC_DISCOVERY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

_DEFAULT_RS_SYMBOLS = "ALAB,CRDO,MRVL,MU,SNDK,NVDA,AMD,ARM,AVGO,SMCI,VRT,AAOI,IONQ,RKLB,SOUN,WULF,MARA,RIOT,BTDR,CLSK"
_DEFAULT_DISCOVERY_SYMBOLS = (
    "ALAB,CRDO,MRVL,MU,SNDK,NVDA,AMD,ARM,AVGO,TSM,SMCI,VRT,AAOI,ANET,DELL,HPE,COHR,LITE,WDC,STX,TER,MPWR,ACLS,UCTT,"
    "PLTR,NET,CRWD,PANW,SNOW,DDOG,ZS,OKTA,SHOP,ROKU,COIN,HOOD,APP,DUOL,TOST,"
    "IONQ,RKLB,SOUN,RGTI,QBTS,ACHR,JOBY,TEM,RXRX,BBAI,AI,"
    "WULF,MARA,RIOT,BTDR,CLSK,IREN,CIFR,HUT,CORZ,APLD,"
    "GEV,VST,CEG,NRG,ETN,PWR,MOD,POWL,IESC,"
    "LMT,RTX,NOC,GD,HWM,AXON,KTOS,AVAV,"
    "CAT,DE,EMR,PH,URI,OSK,"
    "LLY,NVO,VRTX,REGN,ISRG,BSX,MDT,UNH,"
    "JPM,GS,MS,AXP,V,MA,BX,KKR,"
    "XOM,CVX,COP,SLB,OXY,LNG,CCJ,UEC,"
    "GLD,SLV,GDX,GDXJ,NEM,AEM,WPM,FNV,RGLD,PAAS,HL,CDE,"
    "DHI,LEN,PHM,TOL,HD,LOW,COST,WMT,"
    "TSLA,RIVN,LCID,F,GM"
)
RS_LEADER_SYMBOLS = [s.strip().upper() for s in os.environ.get("RS_LEADER_SYMBOLS", _DEFAULT_RS_SYMBOLS).split(",") if s.strip()]
DISCOVERY_SYMBOLS = [s.strip().upper() for s in os.environ.get("DYNAMIC_DISCOVERY_SYMBOLS", _DEFAULT_DISCOVERY_SYMBOLS).split(",") if s.strip()]
RS_LEADER_MAX_SYMBOLS_PER_CYCLE = int(os.environ.get("RS_LEADER_MAX_SYMBOLS_PER_CYCLE", "12"))
DISCOVERY_MAX_SYMBOLS_PER_CYCLE = int(os.environ.get("DYNAMIC_DISCOVERY_MAX_SYMBOLS_PER_CYCLE", "45"))
RS_LEADER_MAX_ROUTE_SYMBOLS = int(os.environ.get("RS_LEADER_MAX_ROUTE_SYMBOLS", "20"))
DISCOVERY_MAX_ROUTE_SYMBOLS = int(os.environ.get("DYNAMIC_DISCOVERY_MAX_ROUTE_SYMBOLS", "120"))
CACHE_TTL_SECONDS = int(os.environ.get("DYNAMIC_DISCOVERY_CACHE_TTL_SECONDS", os.environ.get("RS_LEADER_CACHE_TTL_SECONDS", "120")))

RS_LEADER_MIN_QQQ_DAY_PCT = float(os.environ.get("RS_LEADER_MIN_QQQ_DAY_PCT", "-0.0125"))
RS_LEADER_MAX_QQQ_DAY_PCT = float(os.environ.get("RS_LEADER_MAX_QQQ_DAY_PCT", "0.0090"))
RS_LEADER_MIN_SPY_DAY_PCT = float(os.environ.get("RS_LEADER_MIN_SPY_DAY_PCT", "-0.0125"))
RS_LEADER_MAX_VIX_5D_PCT = float(os.environ.get("RS_LEADER_MAX_VIX_5D_PCT", "15.0"))

RS_LEADER_MIN_STOCK_DAY_PCT = float(os.environ.get("RS_LEADER_MIN_STOCK_DAY_PCT", "0.0080"))
RS_LEADER_MIN_RELATIVE_EDGE_PCT = float(os.environ.get("RS_LEADER_MIN_RELATIVE_EDGE_PCT", "0.0150"))
DISCOVERY_MIN_STOCK_DAY_PCT = float(os.environ.get("DYNAMIC_DISCOVERY_MIN_STOCK_DAY_PCT", "0.0120"))
DISCOVERY_MIN_RELATIVE_EDGE_PCT = float(os.environ.get("DYNAMIC_DISCOVERY_MIN_RELATIVE_EDGE_PCT", "0.0180"))
RS_LEADER_MIN_VOLUME_RATIO = float(os.environ.get("RS_LEADER_MIN_VOLUME_RATIO", "0.90"))
DISCOVERY_MIN_VOLUME_RATIO = float(os.environ.get("DYNAMIC_DISCOVERY_MIN_VOLUME_RATIO", "1.05"))
RS_LEADER_MAX_ABOVE_VWAP_PCT = float(os.environ.get("RS_LEADER_MAX_ABOVE_VWAP_PCT", "0.0250"))
RS_LEADER_MAX_ABOVE_MA20_PCT = float(os.environ.get("RS_LEADER_MAX_ABOVE_MA20_PCT", "0.0225"))
RS_LEADER_NEAR_HIGH_PULLBACK_PCT = float(os.environ.get("RS_LEADER_NEAR_HIGH_PULLBACK_PCT", "0.0060"))
RS_LEADER_SCORE_BONUS = float(os.environ.get("RS_LEADER_SCORE_BONUS", "0.0040"))
DISCOVERY_SCORE_BONUS = float(os.environ.get("DYNAMIC_DISCOVERY_SCORE_BONUS", "0.0030"))
RS_LEADER_ALLOC_FACTOR = float(os.environ.get("RS_LEADER_ALLOC_FACTOR", "0.45"))
DISCOVERY_ALLOC_FACTOR = float(os.environ.get("DYNAMIC_DISCOVERY_ALLOC_FACTOR", "0.35"))
RS_LEADER_MAX_POSITIONS = int(os.environ.get("RS_LEADER_MAX_POSITIONS", "2"))
DISCOVERY_MAX_PROMOTED_PER_CYCLE = int(os.environ.get("DYNAMIC_DISCOVERY_MAX_PROMOTED_PER_CYCLE", "3"))

RS_LEADER_STOP_LOSS_PCT = float(os.environ.get("RS_LEADER_STOP_LOSS_PCT", "-0.0080"))
RS_LEADER_PROFIT_LOCK_1_PCT = float(os.environ.get("RS_LEADER_PROFIT_LOCK_1_PCT", "0.0120"))
RS_LEADER_PROFIT_LOCK_1_FLOOR_PCT = float(os.environ.get("RS_LEADER_PROFIT_LOCK_1_FLOOR_PCT", "0.0020"))
RS_LEADER_PROFIT_LOCK_2_PCT = float(os.environ.get("RS_LEADER_PROFIT_LOCK_2_PCT", "0.0220"))
RS_LEADER_PROFIT_LOCK_2_FLOOR_PCT = float(os.environ.get("RS_LEADER_PROFIT_LOCK_2_FLOOR_PCT", "0.0075"))

_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}

_SECTOR_HINTS = {
    "LMT": "XLI", "RTX": "XLI", "NOC": "XLI", "GD": "XLI", "HWM": "XLI", "AXON": "XLI", "KTOS": "XLI", "AVAV": "XLI",
    "CAT": "XLI", "DE": "XLI", "EMR": "XLI", "PH": "XLI", "URI": "XLI", "OSK": "XLI",
    "LLY": "XLV", "NVO": "XLV", "VRTX": "XLV", "REGN": "XLV", "ISRG": "XLV", "BSX": "XLV", "MDT": "XLV", "UNH": "XLV",
    "JPM": "XLF", "GS": "XLF", "MS": "XLF", "AXP": "XLF", "V": "XLF", "MA": "XLF", "BX": "XLF", "KKR": "XLF",
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "SLB": "XLE", "OXY": "XLE", "LNG": "XLE", "CCJ": "XLE", "UEC": "XLE",
    "DHI": "XLY", "LEN": "XLY", "PHM": "XLY", "TOL": "XLY", "HD": "XLY", "LOW": "XLY", "COST": "XLP", "WMT": "XLP",
    "TSLA": "XLY", "RIVN": "XLY", "LCID": "XLY", "F": "XLY", "GM": "XLY",
}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if np.isnan(x) or np.isinf(x):
            return default
        return x
    except Exception:
        return default


def _dedupe(symbols: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for s in symbols:
        sym = str(s or "").upper().strip()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _clean(arr: Any) -> np.ndarray:
    try:
        a = np.asarray(arr).astype(float).flatten()
        return a[~np.isnan(a)]
    except Exception:
        return np.array([])


def _session_bars(length: int) -> int:
    return max(1, min(int(length or 0), 78))


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


def _session_change(arrays: Dict[str, np.ndarray]) -> float:
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


def _session_high(closes: np.ndarray, highs: np.ndarray) -> float:
    bars = _session_bars(len(closes))
    source = highs if len(highs) >= bars else closes
    return float(np.max(source[-bars:])) if len(source) else 0.0


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


def _infer_sector(m: Any, symbol: str) -> str:
    symbol = str(symbol).upper()
    sector_map = getattr(m, "SYMBOL_SECTOR", {}) or {}
    if symbol in sector_map:
        return sector_map[symbol]
    if symbol in {"GLD", "SLV", "GDX", "GDXJ", "NEM", "AEM", "WPM", "FNV", "RGLD", "PAAS", "HL", "CDE"}:
        return "PRECIOUS_METALS"
    return _SECTOR_HINTS.get(symbol, "XLK")


def _infer_bucket(m: Any, symbol: str, source: str) -> str:
    symbol = str(symbol).upper()
    bucket_map = getattr(m, "SYMBOL_BUCKET", {}) or {}
    if symbol in bucket_map:
        return bucket_map[symbol]
    if source == "dynamic_discovery":
        if _infer_sector(m, symbol) == "PRECIOUS_METALS":
            return "precious_metals"
        return "dynamic_discovery"
    return "semi_leaders"


def _market_intraday_context(m: Any, market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    market = market or {}
    qqq_arrays = _fetch_arrays(m, "QQQ") or {}
    spy_arrays = _fetch_arrays(m, "SPY") or {}
    qqq_day = _session_change(qqq_arrays) if qqq_arrays else 0.0
    spy_day = _session_change(spy_arrays) if spy_arrays else 0.0
    mode = market.get("market_mode") or "unknown"
    bear_confirmed = bool(market.get("bear_confirmed", False))
    vix_5d_pct = _safe_float(market.get("vix_5d_pct"), 0.0)
    try:
        rc = m.get_risk_controls()
    except Exception:
        rc = {}
    feedback = getattr(m, "portfolio", {}).get("feedback_loop") or {}
    mildly_soft = qqq_day >= RS_LEADER_MIN_QQQ_DAY_PCT and qqq_day <= RS_LEADER_MAX_QQQ_DAY_PCT and spy_day >= RS_LEADER_MIN_SPY_DAY_PCT
    risk_ok = (
        _ENABLED
        and mode not in {"risk_off", "crash_warning", "defensive_rotation"}
        and not bear_confirmed
        and vix_5d_pct <= RS_LEADER_MAX_VIX_5D_PCT
        and not bool(rc.get("halted", False))
        and not bool(rc.get("self_defense_active", False))
        and not bool(feedback.get("hard_halt", False))
    )
    return {
        "enabled": bool(_ENABLED),
        "dynamic_discovery_enabled": bool(DISCOVERY_ENABLED),
        "market_mode": mode,
        "risk_score": market.get("risk_score"),
        "regime": market.get("regime"),
        "qqq_day_pct": round(qqq_day * 100.0, 3),
        "spy_day_pct": round(spy_day * 100.0, 3),
        "mildly_soft_or_flat": bool(mildly_soft),
        "risk_ok": bool(risk_ok),
        "bear_confirmed": bear_confirmed,
        "vix_5d_pct": vix_5d_pct,
        "risk_controls_halted": bool(rc.get("halted", False)),
        "self_defense_active": bool(rc.get("self_defense_active", False)),
    }


def _leader_count_open(m: Any) -> int:
    count = 0
    try:
        for pos in (getattr(m, "portfolio", {}).get("positions") or {}).values():
            ctx = str(pos.get("entry_context", ""))
            if ctx.startswith("relative_strength_leader_exception") or ctx.startswith("dynamic_discovery"):
                count += 1
    except Exception:
        pass
    return count


def _candidate_for_symbol(m: Any, symbol: str, market: Dict[str, Any], market_ctx: Dict[str, Any], qqq_arrays: Dict[str, np.ndarray] | None, source: str) -> Dict[str, Any]:
    symbol = str(symbol).upper().strip()
    arrays = _fetch_arrays(m, symbol)
    if arrays is None:
        return {"symbol": symbol, "source": source, "entry_allowed": False, "reason": "no_intraday_data"}
    closes = _clean(arrays.get("close")); highs = _clean(arrays.get("high")); vols = _clean(arrays.get("volume"))
    px = float(closes[-1])
    ma8, ma20, ma34 = _ma(closes, 8), _ma(closes, 20), _ma(closes, 34)
    vwap = _vwap(closes, vols)
    day_move = _session_change(arrays)
    qqq_day = _session_change(qqq_arrays) if qqq_arrays else _safe_float(market_ctx.get("qqq_day_pct")) / 100.0
    relative_edge = day_move - qqq_day
    high = _session_high(closes, highs)
    vol_ratio = _volume_ratio(vols)
    min_day = DISCOVERY_MIN_STOCK_DAY_PCT if source == "dynamic_discovery" else RS_LEADER_MIN_STOCK_DAY_PCT
    min_edge = DISCOVERY_MIN_RELATIVE_EDGE_PCT if source == "dynamic_discovery" else RS_LEADER_MIN_RELATIVE_EDGE_PCT
    min_vol = DISCOVERY_MIN_VOLUME_RATIO if source == "dynamic_discovery" else RS_LEADER_MIN_VOLUME_RATIO
    trend_ok = bool(ma8 and ma20 and ma34 and px > ma20 and ma8 >= ma20 * 0.998 and ma20 >= ma34 * 0.990)
    above_vwap = bool(vwap and px >= vwap)
    not_too_far_above_vwap = bool(vwap and ((px / vwap) - 1.0) <= RS_LEADER_MAX_ABOVE_VWAP_PCT)
    not_too_far_above_ma20 = bool(ma20 and ((px / ma20) - 1.0) <= RS_LEADER_MAX_ABOVE_MA20_PCT)
    pulled_back_from_high = bool(high and px <= high * (1.0 - RS_LEADER_NEAR_HIGH_PULLBACK_PCT))
    no_chase = (not_too_far_above_vwap and not_too_far_above_ma20) or (pulled_back_from_high and not_too_far_above_ma20)
    stock_green = day_move >= min_day
    rs_ok = relative_edge >= min_edge
    volume_ok = vol_ratio >= min_vol or day_move >= 0.04
    leader_slots_ok = _leader_count_open(m) < RS_LEADER_MAX_POSITIONS
    original_score = 0.0
    try:
        scorer = getattr(m, "_rs_original_signal_score", None) or getattr(m, "signal_score", None)
        qqq_close = _clean((qqq_arrays or {}).get("close")) if qqq_arrays else np.array([])
        if callable(scorer):
            original_score = float(scorer(symbol, closes, market, "long", benchmark_prices=qqq_close))
    except Exception:
        original_score = 0.0
    momentum_score = 0.35 * _pct(closes, 3) + 0.30 * _pct(closes, 6) + 0.25 * _pct(closes, 12) + 0.10 * _pct(closes, 24)
    relative_bonus = min(0.008, max(0.0, relative_edge * 0.20))
    score = max(0.0, original_score, momentum_score) + (DISCOVERY_SCORE_BONUS if source == "dynamic_discovery" else RS_LEADER_SCORE_BONUS) + relative_bonus
    failed: List[str] = []
    if not market_ctx.get("risk_ok"): failed.append("market_risk_not_ok")
    if not market_ctx.get("mildly_soft_or_flat"): failed.append("market_not_mildly_soft_or_flat")
    if not stock_green: failed.append("stock_not_green_enough")
    if not rs_ok: failed.append("relative_edge_too_small")
    if not trend_ok: failed.append("trend_not_confirmed")
    if not above_vwap: failed.append("below_vwap")
    if not volume_ok: failed.append("volume_not_confirmed")
    if not no_chase: failed.append("wait_for_pullback_not_chasing_high")
    if not leader_slots_ok: failed.append("relative_strength_leader_position_limit")
    if source == "dynamic_discovery" and not DISCOVERY_ENABLED: failed.append("dynamic_discovery_disabled")
    entry_allowed = len(failed) == 0
    return {
        "symbol": symbol,
        "source": source,
        "entry_allowed": bool(entry_allowed),
        "reason": (f"{source}_ok" if entry_allowed else ",".join(failed)),
        "score": round(float(score), 6),
        "price": round(px, 4),
        "sector": _infer_sector(m, symbol),
        "bucket": _infer_bucket(m, symbol, source),
        "stock_day_pct": round(day_move * 100.0, 2),
        "qqq_day_pct": round(qqq_day * 100.0, 2),
        "relative_edge_pct": round(relative_edge * 100.0, 2),
        "volume_ratio": round(vol_ratio, 2),
        "above_vwap": bool(above_vwap),
        "vwap": round(float(vwap), 4) if vwap else None,
        "ma8": round(float(ma8), 4) if ma8 else None,
        "ma20": round(float(ma20), 4) if ma20 else None,
        "ma34": round(float(ma34), 4) if ma34 else None,
        "session_high": round(float(high), 4) if high else None,
        "not_too_far_above_vwap": bool(not_too_far_above_vwap),
        "not_too_far_above_ma20": bool(not_too_far_above_ma20),
        "pulled_back_from_high": bool(pulled_back_from_high),
        "no_chase": bool(no_chase),
        "trend_ok": bool(trend_ok),
        "volume_ok": bool(volume_ok),
        "alloc_factor": round(DISCOVERY_ALLOC_FACTOR if source == "dynamic_discovery" else RS_LEADER_ALLOC_FACTOR, 4),
        "strategy_id": f"{source}__relative_strength_scan__adaptive_profit_lock__reduced_risk__long__v2",
    }


def _scan_symbols(m: Any, market: Dict[str, Any], market_ctx: Dict[str, Any], qqq_arrays: Dict[str, np.ndarray] | None, max_symbols: int, route_mode: bool = False) -> List[Dict[str, Any]]:
    symbols: List[Tuple[str, str]] = [(s, "relative_strength_leader_exception") for s in RS_LEADER_SYMBOLS]
    if DISCOVERY_ENABLED:
        limit = DISCOVERY_MAX_ROUTE_SYMBOLS if route_mode else DISCOVERY_MAX_SYMBOLS_PER_CYCLE
        for s in DISCOVERY_SYMBOLS[:limit]:
            if s not in RS_LEADER_SYMBOLS:
                symbols.append((s, "dynamic_discovery"))
    symbols = [(s, src) for i, (s, src) in enumerate(symbols) if s and i < max_symbols]
    candidates: List[Dict[str, Any]] = []
    for symbol, source in symbols:
        try:
            candidates.append(_candidate_for_symbol(m, symbol, market, market_ctx, qqq_arrays, source))
        except Exception as exc:
            candidates.append({"symbol": symbol, "source": source, "entry_allowed": False, "reason": "candidate_error", "error": str(exc)})
    return sorted(candidates, key=lambda x: (_safe_float(x.get("score")), _safe_float(x.get("relative_edge_pct"))), reverse=True)


def _leader_payload(m: Any, market: Dict[str, Any] | None = None, force: bool = False, max_symbols: int | None = None, route_mode: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and _CACHE.get("payload") and now - float(_CACHE.get("ts", 0.0)) < CACHE_TTL_SECONDS:
        return dict(_CACHE["payload"])
    try:
        market = market or m.market_status(force=False)
    except Exception:
        market = market or {}
    market_ctx = _market_intraday_context(m, market)
    qqq_arrays = _fetch_arrays(m, "QQQ")
    default_max = RS_LEADER_MAX_ROUTE_SYMBOLS + DISCOVERY_MAX_ROUTE_SYMBOLS if route_mode else RS_LEADER_MAX_SYMBOLS_PER_CYCLE + DISCOVERY_MAX_SYMBOLS_PER_CYCLE
    candidates = _scan_symbols(m, market, market_ctx, qqq_arrays, max_symbols or default_max, route_mode=route_mode)
    allowed = [c for c in candidates if c.get("entry_allowed")]
    payload = {
        "status": "ok",
        "type": "relative_strength_dynamic_discovery",
        "version": VERSION,
        "generated_local": _now_text(),
        "advisory_only": False,
        "trade_authority": "reduced_size_exception_only",
        "config": {
            "enabled": bool(_ENABLED),
            "dynamic_discovery_enabled": bool(DISCOVERY_ENABLED),
            "rs_symbols_count": len(RS_LEADER_SYMBOLS),
            "dynamic_discovery_symbols_count": len(DISCOVERY_SYMBOLS),
            "max_symbols_per_cycle": RS_LEADER_MAX_SYMBOLS_PER_CYCLE + DISCOVERY_MAX_SYMBOLS_PER_CYCLE,
            "max_route_symbols": RS_LEADER_MAX_ROUTE_SYMBOLS + DISCOVERY_MAX_ROUTE_SYMBOLS,
            "min_stock_day_pct": round(RS_LEADER_MIN_STOCK_DAY_PCT * 100.0, 2),
            "dynamic_min_stock_day_pct": round(DISCOVERY_MIN_STOCK_DAY_PCT * 100.0, 2),
            "min_relative_edge_pct": round(RS_LEADER_MIN_RELATIVE_EDGE_PCT * 100.0, 2),
            "dynamic_min_relative_edge_pct": round(DISCOVERY_MIN_RELATIVE_EDGE_PCT * 100.0, 2),
            "alloc_factor": RS_LEADER_ALLOC_FACTOR,
            "dynamic_alloc_factor": DISCOVERY_ALLOC_FACTOR,
            "max_open_exception_positions": RS_LEADER_MAX_POSITIONS,
        },
        "market_context": market_ctx,
        "allowed_count": len(allowed),
        "blocked_count": len([c for c in candidates if not c.get("entry_allowed")]),
        "allowed_symbols": [c.get("symbol") for c in allowed],
        "allowed_dynamic_symbols": [c.get("symbol") for c in allowed if c.get("source") == "dynamic_discovery"],
        "candidates": candidates,
        "recommended_action": "Promote only reduced-size candidates that pass relative strength, volume, trend, and no-chase checks; wait for pullback/reclaim when flagged.",
    }
    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return dict(payload)


def _is_rs_signal(signal: Dict[str, Any]) -> bool:
    ctx = str(signal.get("entry_context", ""))
    return ctx.startswith("relative_strength_leader_exception") or ctx.startswith("dynamic_discovery")


def _confirm_signal_still_valid(m: Any, signal: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    payload = _leader_payload(m, market=market, force=True, route_mode=False)
    symbol = str(signal.get("symbol", "")).upper()
    for c in payload.get("candidates", []):
        if c.get("symbol") == symbol:
            return bool(c.get("entry_allowed")), c
    return False, {"reason": "symbol_not_in_dynamic_discovery_scan", "symbol": symbol}


def _patch_universe(m: Any) -> None:
    try:
        for s in _dedupe(RS_LEADER_SYMBOLS + DISCOVERY_SYMBOLS):
            if hasattr(m, "UNIVERSE") and s in RS_LEADER_SYMBOLS and s not in m.UNIVERSE:
                m.UNIVERSE.append(s)
            if hasattr(m, "SYMBOL_SECTOR"):
                m.SYMBOL_SECTOR.setdefault(s, _infer_sector(m, s))
            if hasattr(m, "SYMBOL_BUCKET"):
                m.SYMBOL_BUCKET.setdefault(s, _infer_bucket(m, s, "relative_strength_leader_exception" if s in RS_LEADER_SYMBOLS else "dynamic_discovery"))
    except Exception:
        pass


def apply(m: Any) -> None:
    if m is None or getattr(m, PATCH_FLAG, False):
        return
    _patch_universe(m)
    original_scan = getattr(m, "scan_signals", None)
    original_entry_quality = getattr(m, "entry_quality_check", None)
    original_manage_exits = getattr(m, "manage_exits", None)
    original_signal_score = getattr(m, "signal_score", None)
    if callable(original_signal_score) and not hasattr(m, "_rs_original_signal_score"):
        setattr(m, "_rs_original_signal_score", original_signal_score)

    if callable(original_scan):
        setattr(m, "_rs_original_scan_signals", original_scan)
        def patched_scan_signals(market: Dict[str, Any]):
            long_signals, short_signals, rejected = original_scan(market)
            try:
                existing = {str(s.get("symbol", "")).upper() for s in long_signals if isinstance(s, dict)}
                payload = _leader_payload(m, market=market, force=True, route_mode=False)
                promoted_dynamic = 0
                for candidate in payload.get("candidates", []):
                    symbol = str(candidate.get("symbol", "")).upper()
                    if not symbol or symbol in existing:
                        continue
                    if candidate.get("entry_allowed"):
                        if candidate.get("source") == "dynamic_discovery" and promoted_dynamic >= DISCOVERY_MAX_PROMOTED_PER_CYCLE:
                            rejected.append({"symbol": symbol, "side": "long", "reason": "dynamic_discovery_cycle_promotion_limit", "quality_info": candidate})
                            continue
                        entry_context = "dynamic_discovery_relative_strength_exception" if candidate.get("source") == "dynamic_discovery" else "relative_strength_leader_exception"
                        if candidate.get("source") == "dynamic_discovery":
                            promoted_dynamic += 1
                        signal = {
                            "symbol": symbol,
                            "side": "long",
                            "score": round(_safe_float(candidate.get("score")), 6),
                            "price": _safe_float(candidate.get("price")),
                            "sector": candidate.get("sector"),
                            "bucket": candidate.get("bucket"),
                            "entry_context": entry_context,
                            "alloc_factor": _safe_float(candidate.get("alloc_factor"), DISCOVERY_ALLOC_FACTOR),
                            "catalyst": {"active": True, "reason": entry_context, "relative_edge_pct": candidate.get("relative_edge_pct"), "stock_day_pct": candidate.get("stock_day_pct"), "volume_ratio": candidate.get("volume_ratio")},
                            "strategy_id": candidate.get("strategy_id"),
                        }
                        long_signals.append(signal)
                        existing.add(symbol)
                    else:
                        rejected.append({"symbol": symbol, "side": "long", "score": candidate.get("score"), "reason": f"{candidate.get('source')}_block", "quality_info": candidate})
                long_signals = sorted(long_signals, key=lambda x: x.get("score", 0.0), reverse=True)
            except Exception as exc:
                rejected.append({"symbol": "DYNAMIC_DISCOVERY", "reason": "patch_error", "error": str(exc)})
            return long_signals, short_signals, rejected
        m.scan_signals = patched_scan_signals

    if callable(original_entry_quality):
        setattr(m, "_rs_original_entry_quality_check", original_entry_quality)
        def patched_entry_quality_check(signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], exclude_symbol: str | None = None):
            ok, info = original_entry_quality(signal, params, market, exclude_symbol=exclude_symbol)
            if ok or not _is_rs_signal(signal):
                return ok, info
            confirmed, confirm_info = _confirm_signal_still_valid(m, signal, market)
            if not confirmed:
                return False, {"reason": "relative_strength_dynamic_discovery_no_longer_valid", "original_quality_info": info, "confirm_info": confirm_info}
            patched_market = dict(market or {})
            futures = dict((market or {}).get("futures_bias", {}) or {})
            futures["action"] = "normal"
            futures["bias"] = futures.get("bias") or "relative_strength_exception"
            futures["relative_strength_exception_override"] = True
            patched_market["futures_bias"] = futures
            patched_signal = dict(signal)
            patched_signal["alloc_factor"] = min(_safe_float(signal.get("alloc_factor"), RS_LEADER_ALLOC_FACTOR), DISCOVERY_ALLOC_FACTOR if str(signal.get("entry_context", "")).startswith("dynamic_discovery") else RS_LEADER_ALLOC_FACTOR)
            ok2, info2 = original_entry_quality(patched_signal, params, patched_market, exclude_symbol=exclude_symbol)
            if ok2:
                signal["alloc_factor"] = patched_signal["alloc_factor"]
                return True, {"reason": "relative_strength_dynamic_discovery_ok", "original_quality_info": info, "base_quality_info": info2, "confirm_info": confirm_info, "alloc_factor": signal["alloc_factor"]}
            return False, {"reason": "relative_strength_dynamic_discovery_base_quality_block", "original_quality_info": info, "base_quality_info": info2, "confirm_info": confirm_info}
        m.entry_quality_check = patched_entry_quality_check

    if callable(original_manage_exits):
        setattr(m, "_rs_original_manage_exits", original_manage_exits)
        def patched_manage_exits(params: Dict[str, Any], market: Dict[str, Any]):
            exits = original_manage_exits(params, market)
            try:
                exited = {str(e.get("symbol", "")).upper() for e in exits or [] if isinstance(e, dict)}
                for symbol, pos in list((getattr(m, "portfolio", {}).get("positions") or {}).items()):
                    if str(symbol).upper() in exited:
                        continue
                    ctx = str(pos.get("entry_context", ""))
                    if not (ctx.startswith("relative_strength_leader_exception") or ctx.startswith("dynamic_discovery")):
                        continue
                    px = m.latest_price(symbol) or _safe_float(pos.get("last_price", pos.get("entry")))
                    if px <= 0:
                        continue
                    pos["last_price"] = float(px)
                    pnl_pct = m.position_pnl_pct(pos, px)
                    entry = max(_safe_float(pos.get("entry")), 0.01)
                    peak = max(_safe_float(pos.get("peak", px)), float(px))
                    pos["peak"] = peak
                    peak_profit_pct = (peak - entry) / entry
                    reason = None
                    if pnl_pct <= RS_LEADER_STOP_LOSS_PCT:
                        reason = "relative_strength_dynamic_discovery_tight_stop"
                    elif peak_profit_pct >= RS_LEADER_PROFIT_LOCK_2_PCT and pnl_pct <= RS_LEADER_PROFIT_LOCK_2_FLOOR_PCT:
                        reason = "relative_strength_dynamic_discovery_profit_lock_level_2"
                    elif peak_profit_pct >= RS_LEADER_PROFIT_LOCK_1_PCT and pnl_pct <= RS_LEADER_PROFIT_LOCK_1_FLOOR_PCT:
                        reason = "relative_strength_dynamic_discovery_profit_lock_level_1"
                    elif (market or {}).get("bear_confirmed") or (market or {}).get("market_mode") in {"risk_off", "crash_warning", "defensive_rotation"}:
                        reason = "relative_strength_dynamic_discovery_market_protection"
                    if reason:
                        result = m.exit_position(symbol, px, reason, market_mode=(market or {}).get("market_mode"), extra={"entry_context": ctx, "peak_profit_pct": round(peak_profit_pct * 100.0, 2), "strategy_id": pos.get("strategy_id") or "relative_strength_dynamic_discovery__adaptive_profit_lock__reduced_risk__long__v2"})
                        if result:
                            exits.append(result)
            except Exception:
                pass
            return exits
        m.manage_exits = patched_manage_exits
    setattr(m, PATCH_FLAG, True)


def status_payload(m: Any) -> Dict[str, Any]:
    try:
        market = getattr(m, "portfolio", {}).get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    payload = _leader_payload(m, market=market, force=False, route_mode=False)
    return {
        "status": "ok",
        "type": "leadership_exception_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "patched": bool(getattr(m, PATCH_FLAG, False)),
        "enabled": bool(_ENABLED),
        "dynamic_discovery_enabled": bool(DISCOVERY_ENABLED),
        "trade_authority": payload.get("trade_authority"),
        "market_context": payload.get("market_context"),
        "allowed_count": payload.get("allowed_count"),
        "allowed_symbols": payload.get("allowed_symbols"),
        "allowed_dynamic_symbols": payload.get("allowed_dynamic_symbols"),
        "top_candidates": (payload.get("candidates") or [])[:10],
        "risk_model": {"alloc_factor": RS_LEADER_ALLOC_FACTOR, "dynamic_alloc_factor": DISCOVERY_ALLOC_FACTOR, "max_open_exception_positions": RS_LEADER_MAX_POSITIONS, "tight_stop_pct": round(RS_LEADER_STOP_LOSS_PCT * 100.0, 2), "profit_lock_1_pct": round(RS_LEADER_PROFIT_LOCK_1_PCT * 100.0, 2), "profit_lock_2_pct": round(RS_LEADER_PROFIT_LOCK_2_PCT * 100.0, 2)},
    }


def diagnostic_payload(m: Any, route_mode: bool = True) -> Dict[str, Any]:
    try:
        market = getattr(m, "portfolio", {}).get("last_market") or m.market_status(force=False)
    except Exception:
        market = {}
    payload = _leader_payload(m, market=market, force=True, route_mode=route_mode)
    return {
        "status": "ok",
        "type": "down_market_long_diagnostic",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_context": payload.get("market_context"),
        "allowed_symbols": payload.get("allowed_symbols"),
        "allowed_dynamic_symbols": payload.get("allowed_dynamic_symbols"),
        "blocked_summary": [{"symbol": c.get("symbol"), "source": c.get("source"), "reason": c.get("reason"), "stock_day_pct": c.get("stock_day_pct"), "relative_edge_pct": c.get("relative_edge_pct"), "no_chase": c.get("no_chase")} for c in (payload.get("candidates") or []) if not c.get("entry_allowed")][:25],
        "candidates": payload.get("candidates"),
    }


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in ROUTE_APP_IDS:
        return
    from flask import jsonify
    module = m
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    def _module() -> Any:
        return module
    if "/paper/relative-strength-leaders" not in existing:
        flask_app.add_url_rule("/paper/relative-strength-leaders", "paper_relative_strength_leaders", lambda: jsonify(_leader_payload(_module(), force=True, route_mode=True)))
    if "/paper/dynamic-discovery-status" not in existing:
        flask_app.add_url_rule("/paper/dynamic-discovery-status", "paper_dynamic_discovery_status", lambda: jsonify(diagnostic_payload(_module(), route_mode=True)))
    if "/paper/leadership-exception-status" not in existing:
        flask_app.add_url_rule("/paper/leadership-exception-status", "paper_leadership_exception_status", lambda: jsonify(status_payload(_module())))
    if "/paper/down-market-long-diagnostic" not in existing:
        flask_app.add_url_rule("/paper/down-market-long-diagnostic", "paper_down_market_long_diagnostic", lambda: jsonify(diagnostic_payload(_module(), route_mode=True)))
    ROUTE_APP_IDS.add(id(flask_app))
