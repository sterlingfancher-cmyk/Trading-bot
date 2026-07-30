"""Bounded paper-only opening-surge participation valve.

Allows one reduced-size opening-range breakout long when a defensive macro label
conflicts with a strongly bullish NQ open and a cluster of individual leaders.
It never permits longs during confirmed bear conditions and does not bypass the
core quality, timing, cooldown, stop, or hard-risk controls.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from typing import Any, Dict, List

import numpy as np

VERSION = "opening-surge-participation-2026-07-30-v1"
ENABLED = os.getenv("OPENING_SURGE_PARTICIPATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
START_MIN = int(os.getenv("OPENING_SURGE_START_MINUTES_AFTER_OPEN", "15"))
END_MIN = int(os.getenv("OPENING_SURGE_END_MINUTES_AFTER_OPEN", "45"))
MAX_DAILY = int(os.getenv("OPENING_SURGE_MAX_ENTRIES_PER_DAY", "1"))
MAX_CANDIDATES = int(os.getenv("OPENING_SURGE_MAX_CANDIDATES_PER_CYCLE", "3"))
MIN_CLUSTER = int(os.getenv("OPENING_SURGE_MIN_CLUSTER_CANDIDATES", "2"))
MIN_SCORE = float(os.getenv("OPENING_SURGE_MIN_SCORE", "0.045"))
MIN_DAY_MOVE = float(os.getenv("OPENING_SURGE_MIN_DAY_MOVE", "0.080"))
MAX_DAY_MOVE = float(os.getenv("OPENING_SURGE_MAX_DAY_MOVE", "0.200"))
MIN_SESSION_MOVE = float(os.getenv("OPENING_SURGE_MIN_SESSION_MOVE", "0.040"))
MAX_SESSION_MOVE = float(os.getenv("OPENING_SURGE_MAX_SESSION_MOVE", "0.080"))
MIN_RANGE_BREAK = float(os.getenv("OPENING_SURGE_MIN_OPENING_RANGE_BREAK", "0.002"))
NEAR_HIGH = float(os.getenv("OPENING_SURGE_NEAR_SESSION_HIGH_FACTOR", "0.985"))
MIN_RVOL = float(os.getenv("OPENING_SURGE_MIN_RELATIVE_VOLUME", "1.25"))
STRONG_MOVE_RVOL_EXCEPTION = float(os.getenv("OPENING_SURGE_STRONG_MOVE_VOLUME_EXCEPTION", "0.080"))
MIN_NQ_PCT = float(os.getenv("OPENING_SURGE_MIN_NQ_FUTURES_PCT", "0.80"))
MAX_LONG_ALLOC = float(os.getenv("OPENING_SURGE_MAX_LONG_ALLOC_PCT", "0.05"))
MAX_SIGNAL_FACTOR = float(os.getenv("OPENING_SURGE_MAX_SIGNAL_ALLOC_FACTOR", "1.00"))
MAX_LOSS = float(os.getenv("OPENING_SURGE_MAX_DAILY_LOSS_FRACTION", "0.005"))
MODES = {x.strip() for x in os.getenv("OPENING_SURGE_ALLOWED_MARKET_MODES", "crash_warning,risk_off").split(",") if x.strip()}
BUCKETS = {x.strip() for x in os.getenv(
    "OPENING_SURGE_ALLOWED_BUCKETS",
    "semi_leaders,mega_cap_ai,ai_cloud_breakout,data_center_infra,bitcoin_ai_compute,"
    "power_grid_data_center,small_cap_momentum,cloud_cyber_software,space_stocks,dynamic_discovery",
).split(",") if x.strip()}
EXTRA = [x.strip().upper() for x in os.getenv(
    "OPENING_SURGE_EXTRA_SYMBOLS", "WDC,CORZ,CRWV,LRCX,NBIS,SNDK,RIOT,AMD,BE,PWR"
).split(",") if x.strip()]

_LOCK = threading.RLock()
_WATCHDOG: set[int] = set()
_APPS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_PERMISSION: Dict[str, Any] = {}
_LAST_SCAN: Dict[str, Any] = {}


def _d(x): return x if isinstance(x, dict) else {}
def _l(x): return x if isinstance(x, list) else []
def _f(x, default=0.0):
    try:
        y = float(x)
        return default if math.isnan(y) or math.isinf(y) else y
    except Exception:
        return default

def _i(x, default=0):
    try: return int(float(x))
    except Exception: return default

def _now(core=None):
    try: return str(core.local_ts_text())
    except Exception: return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _today(core=None):
    try: return str(core.today_key())
    except Exception: return dt.datetime.now().strftime("%Y-%m-%d")

def _state(core): return _d(getattr(core, "portfolio", {}))
def _paper():
    return os.getenv("LIVE_TRADING_ENABLED", "false").lower() not in {"1", "true", "yes", "on"} and os.getenv("BROKER_MODE", "").lower() not in {"live", "real", "production"}

def _clock(core):
    try: return _d(core.market_clock())
    except Exception: return {}

def _minutes(core, clock):
    if clock.get("minutes_since_open") is not None: return max(0.0, _f(clock.get("minutes_since_open")))
    try:
        now = core.now_local(); opening = core.regular_open_datetime(now)
        return max(0.0, (now - opening).total_seconds() / 60.0)
    except Exception: return 9999.0

def _entries_today(core):
    try: trades = core.trades_for_date(_today(core))
    except Exception: trades = _l(_state(core).get("trades"))
    return sum(1 for t in _l(trades) if isinstance(t, dict) and t.get("action") == "entry" and (
        "opening_surge" in str(t.get("entry_context") or "") or t.get("trade_class") == "opening_surge_breakout_starter"
    ))

def _permission(core, market):
    global _LAST_PERMISSION
    market = _d(market); state = _state(core); clock = _clock(core); minutes = _minutes(core, clock)
    try: risk = _d(core.get_risk_controls())
    except Exception: risk = _d(state.get("risk_controls"))
    feedback = _d(state.get("feedback_loop")); warmup = {}
    try: warmup = _d(core.opening_warmup_status(clock))
    except Exception: pass
    futures = _d(market.get("futures_bias")); nq = _f(futures.get("nq_pct"))
    futures_ok = nq >= MIN_NQ_PCT and str(futures.get("nq_trend") or "").lower() == "up" and (
        str(futures.get("bias") or "").lower() in {"bullish", "bullish_but_extended"}
        or str(futures.get("action") or "").lower() == "gap_chase_protection"
    )
    daily = max(_f(risk.get("daily_loss_fraction")), _f(risk.get("realized_loss_fraction")), _f(risk.get("daily_loss_pct")) / 100.0)
    intraday = max(_f(risk.get("intraday_drawdown_fraction")), _f(risk.get("intraday_drawdown_pct")) / 100.0)
    used = _entries_today(core); positions = _d(state.get("positions")); mode = str(market.get("market_mode") or "").lower()
    reasons: List[str] = []
    checks = [
        (not ENABLED, "opening_surge_disabled"), (not _paper(), "not_paper_context"),
        (not bool(clock.get("is_open")), "market_closed"), (bool(warmup.get("active")), "opening_warmup_active"),
        (minutes < START_MIN, "before_opening_surge_window"), (minutes > END_MIN, "after_opening_surge_window"),
        (mode not in MODES, "market_mode_not_defensive_dislocation"),
        (bool(market.get("bear_confirmed")), "bear_confirmed_blocks_opening_long"),
        (not futures_ok, "bullish_nq_open_not_confirmed"), (bool(risk.get("halted")), "risk_halted"),
        (bool(risk.get("profit_guard_active")), "profit_guard_active"),
        (bool(risk.get("self_defense_active")), "self_defense_active"),
        (bool(feedback.get("hard_halt")), "feedback_hard_halt"),
        (bool(feedback.get("block_new_entries")), "feedback_blocks_entries"),
        (daily >= MAX_LOSS, "daily_loss_above_opening_surge_limit"),
        (intraday >= MAX_LOSS, "intraday_drawdown_above_opening_surge_limit"),
        (bool(positions), "opening_surge_requires_empty_book"), (used >= MAX_DAILY, "opening_surge_daily_allowance_used"),
    ]
    reasons.extend(reason for failed, reason in checks if failed)
    _LAST_PERMISSION = {
        "active": not reasons, "reasons": reasons, "market_mode": mode, "regime": market.get("regime"),
        "bear_confirmed": bool(market.get("bear_confirmed")), "market_open": bool(clock.get("is_open")),
        "opening_warmup": warmup, "minutes_since_open": round(minutes, 2), "window_start_minutes": START_MIN,
        "window_end_minutes": END_MIN, "futures_bullish": futures_ok, "futures_bias": futures,
        "minimum_nq_pct": MIN_NQ_PCT, "daily_loss_fraction": round(daily, 6),
        "intraday_drawdown_fraction": round(intraday, 6), "max_loss_fraction": MAX_LOSS,
        "open_positions_count": len(positions), "entries_used": used, "entries_remaining": max(0, MAX_DAILY - used),
    }
    return dict(_LAST_PERMISSION)

def _clean(x):
    try:
        a = np.asarray(x, dtype=float).reshape(-1)
        return a[np.isfinite(a)]
    except Exception: return np.array([])

def _rvol(vols, bars):
    vols = _clean(vols)
    if bars <= 0 or len(vols) < bars: return 0.0
    current = float(np.sum(vols[-bars:])); end = len(vols) - bars; samples = []
    for offset in range(1, 5):
        start = end - 78 * offset
        if start < 0: break
        chunk = vols[start:start + bars]
        if len(chunk) == bars and float(np.sum(chunk)) > 0: samples.append(float(np.sum(chunk)))
    baseline = float(np.mean(samples)) if samples else 0.0
    return current / baseline if baseline > 0 else 0.0

def _bucket(core, symbol, row):
    if row.get("bucket"): return str(row.get("bucket"))
    try: return str(core.symbol_bucket(symbol) or "default")
    except Exception: return str(_d(getattr(core, "SYMBOL_BUCKET", {})).get(symbol, "default"))

def _profile(core, row, minutes):
    symbol = str(row.get("symbol") or "").upper().strip(); score = _f(row.get("score"))
    base = {"symbol": symbol, "score": round(score, 6), "qualified": False}
    if not symbol: return {**base, "reason": "missing_symbol"}
    if score < MIN_SCORE: return {**base, "reason": "score_below_opening_surge_floor"}
    try:
        df = core.fetch_intraday(symbol); arrays = core.intraday_arrays(df)
    except Exception as exc: return {**base, "reason": "intraday_fetch_error", "error": str(exc)}
    closes, opens, highs = _clean(_d(arrays).get("close")), _clean(_d(arrays).get("open")), _clean(_d(arrays).get("high"))
    lows, vols = _clean(_d(arrays).get("low")), _clean(_d(arrays).get("volume"))
    bars = max(1, min(len(closes), int(minutes // 5) + 1))
    if bars < 4 or len(opens) < bars or len(highs) < bars: return {**base, "reason": "not_enough_opening_session_bars", "session_bars": bars}
    c, o, h = closes[-bars:], opens[-bars:], highs[-bars:]; l = lows[-bars:] if len(lows) >= bars else c
    px, session_open = float(c[-1]), float(o[0]); previous_close = float(closes[-bars - 1]) if len(closes) > bars else session_open
    if px <= 0 or session_open <= 0 or previous_close <= 0: return {**base, "reason": "bad_price"}
    day_move, session_move = px / previous_close - 1.0, px / session_open - 1.0
    range_high, session_high, session_low = float(np.max(h[:min(3, bars - 1)])), float(np.max(h)), float(np.min(l))
    broke = px >= range_high * (1.0 + MIN_RANGE_BREAK); high_hold = px >= session_high * NEAR_HIGH
    fast_hold = px >= float(np.mean(c[-min(3, len(c)):])) * 0.998; rvol = _rvol(vols, bars)
    volume_ok = rvol >= MIN_RVOL or session_move >= STRONG_MOVE_RVOL_EXCEPTION
    bucket = _bucket(core, symbol, row); failures = []
    for failed, reason in [
        (day_move < MIN_DAY_MOVE, "total_day_move_below_gap_surge_minimum"),
        (day_move > MAX_DAY_MOVE, "total_day_move_too_extended"),
        (session_move < MIN_SESSION_MOVE, "opening_session_follow_through_below_minimum"),
        (session_move > MAX_SESSION_MOVE, "opening_session_follow_through_too_extended"),
        (not broke, "opening_range_not_broken"), (not high_hold, "not_holding_near_session_high"),
        (not fast_hold, "fast_momentum_not_holding"), (not volume_ok, "relative_volume_not_confirmed"),
        (bucket not in BUCKETS, "bucket_not_opening_surge_eligible"),
    ]:
        if failed: failures.append(reason)
    return {**base, "qualified": not failures, "reason": "opening_surge_breakout_confirmed" if not failures else ",".join(failures),
        "price": round(px, 4), "session_bars": bars, "previous_close": round(previous_close, 4),
        "day_move_pct": round(day_move * 100, 3), "session_move_pct": round(session_move * 100, 3),
        "opening_range_high": round(range_high, 4), "session_high": round(session_high, 4), "session_low": round(session_low, 4),
        "broke_opening_range": broke, "holding_near_high": high_hold, "fast_momentum_hold": fast_hold,
        "relative_volume_ratio": round(rvol, 3), "volume_confirmed": volume_ok, "bucket": bucket,
        "sector": row.get("sector") or _d(getattr(core, "SYMBOL_SECTOR", {})).get(symbol, "UNKNOWN"),
        "source_reason": row.get("reason")}

def _patch_universe(core):
    try:
        universe = list(getattr(core, "UNIVERSE", []) or [])
        for symbol in EXTRA:
            if symbol not in universe: universe.append(symbol)
        core.UNIVERSE = universe
    except Exception: pass
    sectors = {"WDC":"XLK","CORZ":"XLK","CRWV":"XLK","LRCX":"XLK","NBIS":"XLK","SNDK":"XLK","RIOT":"XLK","AMD":"XLK","BE":"XLI","PWR":"XLI"}
    buckets = {"WDC":"data_center_infra","CORZ":"bitcoin_ai_compute","CRWV":"ai_cloud_breakout","LRCX":"semi_leaders","NBIS":"ai_cloud_breakout","SNDK":"data_center_infra","RIOT":"bitcoin_ai_compute","AMD":"semi_leaders","BE":"power_grid_data_center","PWR":"power_grid_data_center"}
    try:
        for s, v in sectors.items(): getattr(core, "SYMBOL_SECTOR", {}).setdefault(s, v)
        for s, v in buckets.items(): getattr(core, "SYMBOL_BUCKET", {}).setdefault(s, v)
    except Exception: pass

def _wrap_risk(core):
    current = getattr(core, "risk_parameters", None)
    if not callable(current) or getattr(current, "_opening_surge_permission_guard", False): return False
    def wrapped(market, __prior=current):
        params = dict(__prior(market) or {}); permission = _permission(core, market)
        if permission.get("active"):
            positions = _d(_state(core).get("positions")); normal_max = max(1, _i(params.get("max_positions"), 1))
            params.update({"allow_longs": True, "max_positions": min(normal_max, len(positions) + 1),
                "long_alloc_pct": min(max(0.0, _f(params.get("long_alloc_pct"))), MAX_LONG_ALLOC),
                "opening_surge_permission": permission, "opening_surge_only": True})
        return params
    wrapped._opening_surge_permission_guard = True; wrapped._opening_surge_version = VERSION; wrapped._opening_surge_prior = current
    core.risk_parameters = wrapped; return True

def _wrap_scan(core):
    current = getattr(core, "scan_signals", None)
    if not callable(current) or getattr(current, "_opening_surge_scan_guard", False): return False
    def wrapped(market, __prior=current):
        global _LAST_SCAN
        longs, shorts, rejected = __prior(market); permission = _permission(core, market)
        if not permission.get("active"): return longs, shorts, rejected
        by_symbol = {}
        for row in list(_l(longs)) + [x for x in _l(rejected) if isinstance(x, dict) and str(x.get("side") or "long").lower() == "long" and _f(x.get("score")) >= MIN_SCORE]:
            if not isinstance(row, dict): continue
            symbol = str(row.get("symbol") or "").upper()
            if symbol and (symbol not in by_symbol or _f(row.get("score")) > _f(by_symbol[symbol].get("score"))): by_symbol[symbol] = dict(row)
        profiles = [_profile(core, row, _f(permission.get("minutes_since_open"))) for row in by_symbol.values()]
        qualified = sorted([x for x in profiles if x.get("qualified")], key=lambda x: (_f(x.get("score")), _f(x.get("relative_volume_ratio"))), reverse=True)
        promoted = []
        if len(qualified) >= MIN_CLUSTER:
            for p in qualified[:MAX_CANDIDATES]:
                row = dict(by_symbol.get(str(p.get("symbol")), {})); row.update({"symbol":p.get("symbol"),"side":"long","score":p.get("score"),
                    "price":p.get("price"),"sector":p.get("sector"),"bucket":p.get("bucket"),
                    "entry_context":"opening_surge_breakout_starter","trade_class":"opening_surge_breakout_starter",
                    "alloc_factor":min(max(0.0,_f(row.get("alloc_factor"),1.0)),MAX_SIGNAL_FACTOR),"opening_surge_participation":p})
                promoted.append(row)
        _LAST_SCAN = {"version":VERSION,"updated_local":_now(core),"permission":permission,"cluster_confirmed":len(qualified)>=MIN_CLUSTER,
            "minimum_cluster_candidates":MIN_CLUSTER,"qualified_count":len(qualified),"qualified_symbols":[x.get("symbol") for x in qualified],
            "promoted_symbols":[x.get("symbol") for x in promoted],"profiles":profiles[:20]}
        _state(core)["opening_surge_participation"] = dict(_LAST_SCAN)
        return promoted, shorts, rejected
    wrapped._opening_surge_scan_guard = True; wrapped._opening_surge_version = VERSION; wrapped._opening_surge_prior = current
    core.scan_signals = wrapped; return True

def install(core):
    global _LAST_INSTALL
    if core is None: return {"status":"pending","version":VERSION,"reason":"core_missing"}
    with _LOCK:
        _patch_universe(core); rp, sp = _wrap_risk(core), _wrap_scan(core)
        rf, sf = getattr(core,"risk_parameters",None), getattr(core,"scan_signals",None)
        _LAST_INSTALL = {"status":"ok","version":VERSION,"generated_local":_now(core),"risk_parameters_patched_this_call":rp,
            "scan_signals_patched_this_call":sp,"risk_guard_active":bool(getattr(rf,"_opening_surge_permission_guard",False)),
            "scan_guard_active":bool(getattr(sf,"_opening_surge_scan_guard",False)),"risk_callable":getattr(rf,"__qualname__",None),
            "scan_callable":getattr(sf,"__qualname__",None)}
        setattr(core,"OPENING_SURGE_PARTICIPATION_VERSION",VERSION); return dict(_LAST_INSTALL)

def status_payload(core):
    market = _d(_state(core).get("last_market")) if core else {}; permission = _permission(core, market) if core else {}
    rf, sf = (getattr(core,"risk_parameters",None), getattr(core,"scan_signals",None)) if core else (None,None)
    ra, sa = bool(getattr(rf,"_opening_surge_permission_guard",False)), bool(getattr(sf,"_opening_surge_scan_guard",False))
    return {"status":"ok" if ra and sa else "warn","overall":"pass" if ra and sa else "warn","type":"opening_surge_participation_status",
        "version":VERSION,"generated_local":_now(core),"risk_guard_active":ra,"scan_guard_active":sa,"permission_live":permission,
        "last_scan":dict(_LAST_SCAN),"stored_state":_d(_state(core).get("opening_surge_participation")) if core else {},"last_install":dict(_LAST_INSTALL),
        "settings":{"start_minutes_after_open":START_MIN,"end_minutes_after_open":END_MIN,"max_entries_per_day":MAX_DAILY,
            "max_candidates_per_cycle":MAX_CANDIDATES,"minimum_cluster_candidates":MIN_CLUSTER,"minimum_score":MIN_SCORE,
            "minimum_day_move_pct":MIN_DAY_MOVE*100,"maximum_day_move_pct":MAX_DAY_MOVE*100,
            "minimum_session_follow_through_pct":MIN_SESSION_MOVE*100,"maximum_session_follow_through_pct":MAX_SESSION_MOVE*100,
            "minimum_relative_volume":MIN_RVOL,"minimum_nq_futures_pct":MIN_NQ_PCT,"allowed_market_modes":sorted(MODES)},
        "authority":{"paper_only":True,"places_orders_directly":False,"changes_live_authority":False,"changes_ml_authority":False,
            "changes_hard_risk_limits":False,"changes_signal_generation":True,"changes_strategy_permission":True,"changes_sizing":True,
            "bounded_opening_long_exception":True,"bear_confirmed_long_exception":False}}

def register_routes(flask_app, core):
    if flask_app is None: return {"status":"pending","version":VERSION,"reason":"flask_app_missing"}
    install(core)
    if id(flask_app) in _APPS: return {"status":"ok","version":VERSION,"already_registered":True}
    from flask import jsonify
    path = "/paper/opening-surge-participation-status"
    if path not in {getattr(r,"rule","") for r in flask_app.url_map.iter_rules()}:
        flask_app.add_url_rule(path,"opening_surge_participation_status",lambda:jsonify(status_payload(core)))
    _APPS.add(id(flask_app)); return {"status":"ok","version":VERSION,"routes":[path]}

def start_watchdog(core):
    install(core); app = getattr(core,"app",None)
    if app is not None: register_routes(app,core)
    if core is None or id(core) in _WATCHDOG: return {"status":"ok","version":VERSION,"watchdog_started":core is not None and id(core) in _WATCHDOG}
    _WATCHDOG.add(id(core))
    def watch():
        for n in range(1200):
            try: install(core)
            except Exception: pass
            time.sleep(0.5 if n < 60 else 30.0)
    threading.Thread(target=watch,daemon=True,name="opening-surge-participation-watchdog").start()
    return {"status":"ok","version":VERSION,"watchdog_started":True}
