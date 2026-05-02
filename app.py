import os
import json
import time
import datetime
import threading
import traceback

import numpy as np
import pytz
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ============================================================
# CONFIG
# ============================================================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
MARKET_CACHE_TTL = int(os.environ.get("MARKET_CACHE_TTL", "300"))

MARKET_TZ = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
REGULAR_OPEN_HOUR = int(os.environ.get("REGULAR_OPEN_HOUR", "8"))
REGULAR_OPEN_MINUTE = int(os.environ.get("REGULAR_OPEN_MINUTE", "30"))
REGULAR_CLOSE_HOUR = int(os.environ.get("REGULAR_CLOSE_HOUR", "15"))
REGULAR_CLOSE_MINUTE = int(os.environ.get("REGULAR_CLOSE_MINUTE", "0"))

AUTO_RUN_ENABLED = os.environ.get("AUTO_RUN_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
AUTO_RUN_INTERVAL_SECONDS = int(os.environ.get("AUTO_RUN_INTERVAL_SECONDS", "300"))
AUTO_RUN_MARKET_ONLY = os.environ.get("AUTO_RUN_MARKET_ONLY", "true").lower() not in ["0", "false", "no", "off"]

# Critical safety fix:
# Manual /paper/run no longer places entries/exits after regular session by default.
ALLOW_MANUAL_AFTER_HOURS_TRADING = os.environ.get(
    "ALLOW_MANUAL_AFTER_HOURS_TRADING", "false"
).lower() in ["1", "true", "yes", "on"]

MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "0.03"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("MAX_INTRADAY_DRAWDOWN_PCT", "0.025"))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "1800"))
MIN_TRADE_ALLOC = float(os.environ.get("MIN_TRADE_ALLOC", "50"))

# Entry extension guard. Blocks chasing overstretched 5m moves.
EXTENSION_MAX_ABOVE_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_ABOVE_DAY_OPEN", "0.055"))
EXTENSION_MAX_BELOW_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_BELOW_DAY_OPEN", "0.055"))
EXTENSION_NEAR_HIGH_FACTOR = float(os.environ.get("EXTENSION_NEAR_HIGH_FACTOR", "0.996"))
EXTENSION_NEAR_LOW_FACTOR = float(os.environ.get("EXTENSION_NEAR_LOW_FACTOR", "1.004"))
EXTENSION_BIG_MOVE_CONFIRM = float(os.environ.get("EXTENSION_BIG_MOVE_CONFIRM", "0.035"))
EXTENSION_MAX_FROM_MA20 = float(os.environ.get("EXTENSION_MAX_FROM_MA20", "0.035"))

# Rotation guard. These are intentionally tighter than the prior version to reduce churn.
ROTATION_SCORE_MULTIPLIER = float(os.environ.get("ROTATION_SCORE_MULTIPLIER", "1.45"))
ROTATION_MIN_SCORE_EDGE = float(os.environ.get("ROTATION_MIN_SCORE_EDGE", "0.0065"))
ROTATION_MIN_HOLD_SECONDS = int(os.environ.get("ROTATION_MIN_HOLD_SECONDS", "2700"))
ROTATION_KEEP_WINNER_PCT = float(os.environ.get("ROTATION_KEEP_WINNER_PCT", "0.005"))

# Profit protection. Allows the bot to keep managing open risk, but blocks fresh risk
# after a strong day or after a meaningful giveback from the intraday equity peak.
DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT = float(os.environ.get("DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT", "0.0075"))
DAY_PROFIT_HARD_LOCK_PCT = float(os.environ.get("DAY_PROFIT_HARD_LOCK_PCT", "0.0100"))
DAY_PROFIT_GIVEBACK_LOCK_PCT = float(os.environ.get("DAY_PROFIT_GIVEBACK_LOCK_PCT", "0.0030"))

RUN_LOCK = threading.Lock()
AUTO_THREAD_STARTED = False

# ============================================================
# UNIVERSE
# ============================================================
UNIVERSE = [
    "NVDA", "AMD", "AVGO", "TSM", "MU", "ARM",
    "MSFT", "AMZN", "GOOGL", "META", "PLTR", "SNOW", "NET", "CRWD", "PANW",
    "SHOP", "ROKU", "COIN",
    "XOM", "CVX",
    "WDC", "STX", "GLW", "TER", "CIEN",
    "SPY", "QQQ"
]

SECTOR_ETFS = ["XLK", "XLY", "XLF", "XLE", "XLV", "XLU", "XLI", "XLP"]
MACRO_SYMBOLS = ["SPY", "QQQ", "^VIX", "^TNX"] + SECTOR_ETFS

SYMBOL_SECTOR = {
    "NVDA": "XLK", "AMD": "XLK", "AVGO": "XLK", "TSM": "XLK", "MU": "XLK", "ARM": "XLK",
    "MSFT": "XLK", "SNOW": "XLK", "NET": "XLK", "CRWD": "XLK", "PANW": "XLK",
    "WDC": "XLK", "STX": "XLK", "GLW": "XLK", "TER": "XLK", "CIEN": "XLK",
    "AMZN": "XLY", "SHOP": "XLY", "ROKU": "XLY", "GOOGL": "XLY", "META": "XLY",
    "COIN": "XLF",
    "XOM": "XLE", "CVX": "XLE",
    "SPY": "SPY", "QQQ": "QQQ"
}

_market_cache = {"ts": 0, "data": None}
_price_cache = {"ts": 0, "data": {}}


# ============================================================
# STATE
# ============================================================
def now_local():
    return datetime.datetime.now(MARKET_TZ)


def now_ts():
    return int(time.time())


def today_key():
    return now_local().strftime("%Y-%m-%d")


def local_ts_text(ts=None):
    if ts is None:
        ts = time.time()
    return datetime.datetime.fromtimestamp(ts, MARKET_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def default_risk_controls():
    return {
        "date": today_key(),
        "day_start_equity": 10000.0,
        "day_peak_equity": 10000.0,
        "day_pnl_pct": 0.0,
        "daily_loss_pct": 0.0,
        "daily_drawdown_pct": 0.0,  # kept for dashboard compatibility; now never negative
        "intraday_drawdown_pct": 0.0,
        "profit_guard_active": False,
        "profit_guard_reason": "",
        "halted": False,
        "halt_reason": "",
        "cooldowns": {}
    }


def default_realized_pnl():
    return {
        "date": today_key(),
        "today": 0.0,
        "total": 0.0,
        "wins_today": 0,
        "losses_today": 0,
        "wins_total": 0,
        "losses_total": 0
    }


def default_performance():
    return {
        "realized_pnl_today": 0.0,
        "realized_pnl_total": 0.0,
        "unrealized_pnl": 0.0,
        "wins_today": 0,
        "losses_today": 0,
        "wins_total": 0,
        "losses_total": 0,
        "open_positions": {}
    }


def default_auto_runner():
    return {
        "enabled": AUTO_RUN_ENABLED,
        "market_only": AUTO_RUN_MARKET_ONLY,
        "interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "market_open_now": False,
        "market_clock": {},
        "last_run_ts": None,
        "last_run_local": None,
        "last_run_source": None,
        "last_result": None,
        "last_attempt_ts": None,
        "last_attempt_local": None,
        "last_attempt_source": None,
        "last_successful_run_ts": None,
        "last_successful_run_local": None,
        "last_successful_run_source": None,
        "last_skip_ts": None,
        "last_skip_local": None,
        "last_skip_reason": None,
        "last_error": None,
        "last_error_trace": None,
        "thread_started": False
    }


def default_state():
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "last_market": {},
        "risk_controls": default_risk_controls(),
        "auto_runner": default_auto_runner(),
        "realized_pnl": default_realized_pnl(),
        "performance": default_performance()
    }


def load_state():
    state = default_state()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            pass

    state.setdefault("cash", 10000.0)
    state.setdefault("equity", 10000.0)
    state.setdefault("peak", state.get("equity", 10000.0))
    state.setdefault("positions", {})
    state.setdefault("history", [])
    state.setdefault("trades", [])
    state.setdefault("last_market", {})
    state.setdefault("risk_controls", default_risk_controls())
    state.setdefault("auto_runner", default_auto_runner())
    state.setdefault("realized_pnl", default_realized_pnl())
    state.setdefault("performance", default_performance())

    # Backfill newer fields without breaking old state.json.
    rc = state["risk_controls"]
    rc.setdefault("day_pnl_pct", 0.0)
    rc.setdefault("daily_loss_pct", max(0.0, float(rc.get("daily_drawdown_pct", 0.0))))
    rc["daily_drawdown_pct"] = max(0.0, float(rc.get("daily_drawdown_pct", 0.0)))
    rc.setdefault("profit_guard_active", False)
    rc.setdefault("profit_guard_reason", "")
    rc.setdefault("cooldowns", {})

    for symbol, pos in state.get("positions", {}).items():
        if not isinstance(pos, dict):
            continue
        pos.setdefault("side", "long")
        pos.setdefault("entry_time", int(time.time()))
        pos.setdefault("score", 0.0)
        pos.setdefault("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        pos.setdefault("adds", 0)
        pos.setdefault("last_price", pos.get("entry", 0))
        if pos.get("side", "long") == "short":
            pos.setdefault("trough", pos.get("last_price", pos.get("entry", 0)))
            pos.setdefault("margin", float(pos.get("entry", 0)) * float(pos.get("shares", 0)))
        else:
            pos.setdefault("peak", pos.get("last_price", pos.get("entry", 0)))

    return state


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


portfolio = load_state()


# ============================================================
# MARKET CLOCK
# ============================================================
def market_clock():
    now = now_local()
    open_dt = now.replace(
        hour=REGULAR_OPEN_HOUR,
        minute=REGULAR_OPEN_MINUTE,
        second=0,
        microsecond=0
    )
    close_dt = now.replace(
        hour=REGULAR_CLOSE_HOUR,
        minute=REGULAR_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )

    if now.weekday() >= 5:
        reason = "weekend"
        is_open = False
    elif now < open_dt:
        reason = "before_regular_session"
        is_open = False
    elif now >= close_dt:
        reason = "after_regular_session"
        is_open = False
    else:
        reason = "regular_session"
        is_open = True

    return {
        "is_open": bool(is_open),
        "now_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "reason": reason,
        "regular_open_local": open_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_close_local": close_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": str(MARKET_TZ)
    }


# ============================================================
# HELPERS
# ============================================================
def key_ok():
    supplied = request.args.get("key") or request.headers.get("X-Run-Key")
    return SECRET_KEY == "changeme" or supplied == SECRET_KEY


def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]


def _series_from_df(df, column):
    if df is None or getattr(df, "empty", True):
        return np.array([])

    try:
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            matches = [c for c in df.columns if c[0] == column or c[-1] == column]
            if matches:
                return clean(df[matches[0]].values)
    except Exception:
        pass

    if column not in df:
        return np.array([])

    return clean(df[column].values)


def price_series(df, column="Close"):
    return _series_from_df(df, column)


def download_prices(symbol, period="5d", interval="5m"):
    try:
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    except Exception:
        return None


def latest_price(symbol):
    now = time.time()
    cached = _price_cache["data"].get(symbol)
    if cached and now - cached["ts"] < 60:
        return cached["price"]

    try:
        df = download_prices(symbol, period="1d", interval="5m")
        prices = price_series(df, "Close")
        if len(prices) == 0:
            return None
        px = float(prices[-1])
        _price_cache["data"][symbol] = {"ts": now, "price": px}
        return px
    except Exception:
        return None


def pct_change(prices, bars):
    if len(prices) <= bars or float(prices[-bars]) == 0:
        return 0.0
    return float((prices[-1] / prices[-bars]) - 1)


def sma(prices, bars):
    if len(prices) < bars:
        return None
    return float(np.mean(prices[-bars:]))


def trend_state(prices):
    if len(prices) < 30:
        return "unknown"

    fast = sma(prices, 8)
    slow = sma(prices, 20)

    if fast is None or slow is None:
        return "unknown"

    if prices[-1] > slow and fast > slow:
        return "up"
    if prices[-1] < slow and fast < slow:
        return "down"
    return "flat"


def position_pnl_pct(pos, px):
    entry = float(pos.get("entry", 0))
    if entry <= 0:
        return 0.0

    if pos.get("side", "long") == "short":
        return (entry - float(px)) / entry

    return (float(px) - entry) / entry


def position_pnl_dollars(pos, px):
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry", 0))
    if pos.get("side", "long") == "short":
        return (entry - float(px)) * shares
    return (float(px) - entry) * shares


def position_value(pos, px):
    shares = float(pos.get("shares", 0))
    if pos.get("side", "long") == "short":
        margin = float(pos.get("margin", float(pos.get("entry", 0)) * shares))
        return margin + position_pnl_dollars(pos, px)
    return shares * float(px)


def record_trade(action, symbol, side, px, shares, extra=None):
    trade = {
        "time": int(time.time()),
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": round(float(px), 4),
        "shares": round(float(shares), 6)
    }

    if extra:
        trade.update(extra)

    portfolio.setdefault("trades", []).append(trade)
    portfolio["trades"] = portfolio["trades"][-500:]


def get_realized_pnl():
    rp = portfolio.setdefault("realized_pnl", default_realized_pnl())

    if rp.get("date") != today_key():
        rp["date"] = today_key()
        rp["today"] = 0.0
        rp["wins_today"] = 0
        rp["losses_today"] = 0

    rp.setdefault("today", 0.0)
    rp.setdefault("total", 0.0)
    rp.setdefault("wins_today", 0)
    rp.setdefault("losses_today", 0)
    rp.setdefault("wins_total", 0)
    rp.setdefault("losses_total", 0)
    return rp


def add_realized_pnl(pnl_dollars):
    pnl_dollars = float(pnl_dollars)
    rp = get_realized_pnl()

    rp["today"] = round(float(rp.get("today", 0.0)) + pnl_dollars, 2)
    rp["total"] = round(float(rp.get("total", 0.0)) + pnl_dollars, 2)

    if pnl_dollars >= 0:
        rp["wins_today"] = int(rp.get("wins_today", 0)) + 1
        rp["wins_total"] = int(rp.get("wins_total", 0)) + 1
    else:
        rp["losses_today"] = int(rp.get("losses_today", 0)) + 1
        rp["losses_total"] = int(rp.get("losses_total", 0)) + 1

    return rp


def get_risk_controls():
    rc = portfolio.setdefault("risk_controls", default_risk_controls())
    today = today_key()

    if rc.get("date") != today:
        current_equity = float(portfolio.get("equity", 10000.0))
        rc.clear()
        rc.update(default_risk_controls())
        rc["day_start_equity"] = current_equity
        rc["day_peak_equity"] = current_equity

    rc.setdefault("cooldowns", {})
    rc.setdefault("profit_guard_active", False)
    rc.setdefault("profit_guard_reason", "")
    return rc


def prune_cooldowns():
    rc = get_risk_controls()
    now = time.time()
    rc["cooldowns"] = {
        symbol: until for symbol, until in rc.get("cooldowns", {}).items()
        if float(until) > now
    }
    return rc["cooldowns"]


def is_in_cooldown(symbol):
    cooldowns = prune_cooldowns()
    return float(cooldowns.get(symbol, 0)) > time.time()


def set_cooldown(symbol):
    rc = get_risk_controls()
    rc.setdefault("cooldowns", {})[symbol] = time.time() + COOLDOWN_SECONDS


def update_daily_risk_controls(equity):
    rc = get_risk_controls()
    equity = float(equity)
    start = max(float(rc.get("day_start_equity", equity)), 0.01)
    old_peak = max(float(rc.get("day_peak_equity", equity)), 0.01)
    peak = max(old_peak, equity, 0.01)

    day_pnl_pct = (equity - start) / start
    daily_loss_pct = max(0.0, (start - equity) / start)
    intraday_drawdown_pct = max(0.0, (peak - equity) / peak)

    rc["day_peak_equity"] = peak
    rc["day_pnl_pct"] = round(day_pnl_pct * 100, 3)
    rc["daily_loss_pct"] = round(daily_loss_pct * 100, 3)
    rc["daily_drawdown_pct"] = round(daily_loss_pct * 100, 3)  # dashboard compatibility
    rc["intraday_drawdown_pct"] = round(intraday_drawdown_pct * 100, 3)

    daily_loss_triggered = daily_loss_pct >= MAX_DAILY_LOSS_PCT
    intraday_dd_triggered = intraday_drawdown_pct >= MAX_INTRADAY_DRAWDOWN_PCT

    if daily_loss_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"daily loss limit hit ({MAX_DAILY_LOSS_PCT * 100:.1f}%)"
    elif intraday_dd_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"intraday drawdown limit hit ({MAX_INTRADAY_DRAWDOWN_PCT * 100:.1f}%)"

    # Profit guard controls entries/rotations only. Existing stops still work.
    peak_return_pct = (peak - start) / start
    giveback_pct = (peak - equity) / start

    rc["profit_guard_active"] = False
    rc["profit_guard_reason"] = ""

    if peak_return_pct >= DAY_PROFIT_HARD_LOCK_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"day profit hard lock reached ({DAY_PROFIT_HARD_LOCK_PCT * 100:.2f}%)"
    elif day_pnl_pct >= DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"day profit pause reached ({DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT * 100:.2f}%)"
    elif peak_return_pct >= DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT and giveback_pct >= DAY_PROFIT_GIVEBACK_LOCK_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"profit giveback guard triggered ({DAY_PROFIT_GIVEBACK_LOCK_PCT * 100:.2f}%)"

    return rc


def performance_snapshot():
    rp = get_realized_pnl()
    open_pnl = {}
    unrealized_total = 0.0

    for s, pos in portfolio.get("positions", {}).items():
        px = float(pos.get("last_price", pos.get("entry", 0)))
        pnl_dollars = position_pnl_dollars(pos, px)
        pnl_pct = position_pnl_pct(pos, px) * 100
        unrealized_total += pnl_dollars

        open_pnl[s] = {
            "side": pos.get("side", "long"),
            "entry": round(float(pos.get("entry", 0)), 4),
            "last_price": round(px, 4),
            "shares": round(float(pos.get("shares", 0)), 6),
            "pnl_dollars": round(float(pnl_dollars), 2),
            "pnl_pct": round(float(pnl_pct), 2),
            "score": round(float(pos.get("score", 0.0)), 6),
            "sector": pos.get("sector", SYMBOL_SECTOR.get(s, "UNKNOWN")),
            "entry_time": pos.get("entry_time"),
            "adds": pos.get("adds", 0)
        }

    perf = {
        "realized_pnl_today": round(float(rp.get("today", 0.0)), 2),
        "realized_pnl_total": round(float(rp.get("total", 0.0)), 2),
        "wins_today": int(rp.get("wins_today", 0)),
        "losses_today": int(rp.get("losses_today", 0)),
        "wins_total": int(rp.get("wins_total", 0)),
        "losses_total": int(rp.get("losses_total", 0)),
        "unrealized_pnl": round(float(unrealized_total), 2),
        "open_positions": open_pnl
    }
    portfolio["performance"] = perf
    return perf


def reset_state(starting_cash=10000.0):
    global portfolio
    portfolio = default_state()
    portfolio["cash"] = float(starting_cash)
    portfolio["equity"] = float(starting_cash)
    portfolio["peak"] = float(starting_cash)
    portfolio["risk_controls"] = default_risk_controls()
    portfolio["risk_controls"]["day_start_equity"] = float(starting_cash)
    portfolio["risk_controls"]["day_peak_equity"] = float(starting_cash)
    portfolio["auto_runner"] = default_auto_runner()
    portfolio["realized_pnl"] = default_realized_pnl()
    portfolio["performance"] = default_performance()
    save_state(portfolio)
    return portfolio


# ============================================================
# MARKET / REGIME ENGINE
# ============================================================
def market_status(force=False):
    now = time.time()
    if not force and _market_cache["data"] and now - _market_cache["ts"] < MARKET_CACHE_TTL:
        return _market_cache["data"]

    series = {}
    for symbol in MACRO_SYMBOLS:
        try:
            df = download_prices(symbol, period="30d", interval="1d")
            prices = price_series(df, "Close")
            if len(prices) >= 10:
                series[symbol] = prices
        except Exception:
            continue

    spy = series.get("SPY", np.array([]))
    qqq = series.get("QQQ", np.array([]))
    vix = series.get("^VIX", np.array([]))
    tnx = series.get("^TNX", np.array([]))

    spy_trend = trend_state(spy)
    qqq_trend = trend_state(qqq)
    vix_5d = pct_change(vix, 5)
    tnx_5d = pct_change(tnx, 5)
    spy_5d = pct_change(spy, 5)
    qqq_5d = pct_change(qqq, 5)

    risk_score = 50

    if spy_trend == "up":
        risk_score += 15
    elif spy_trend == "down":
        risk_score -= 18

    if qqq_trend == "up":
        risk_score += 12
    elif qqq_trend == "down":
        risk_score -= 15

    if vix_5d < -0.05:
        risk_score += 10
    elif vix_5d > 0.08:
        risk_score -= 15

    if qqq_5d > spy_5d:
        risk_score += 5
    else:
        risk_score -= 3

    if tnx_5d > 0.05 and qqq_5d < 0:
        risk_score -= 6

    sector_scores = []
    for symbol in SECTOR_ETFS:
        prices = series.get(symbol, np.array([]))
        sector_scores.append((symbol, pct_change(prices, 5)))

    sector_scores = sorted(sector_scores, key=lambda x: x[1], reverse=True)
    sector_leaders = [s for s, _ in sector_scores[:3]]

    defensive_sectors = ["XLU", "XLV", "XLP"]
    risk_on_sectors = ["XLK", "XLY", "XLF", "XLE"]

    defensive_count = sum(1 for s in sector_leaders if s in defensive_sectors)
    risk_on_sector_count = sum(1 for s in sector_leaders if s in risk_on_sectors)

    defensive_leadership = defensive_count >= 2
    growth_leadership = risk_on_sector_count >= 1

    if growth_leadership:
        risk_score += 5
    if defensive_leadership:
        risk_score -= 5

    risk_score = int(max(0, min(100, risk_score)))

    if risk_score >= 70:
        mode = "risk_on"
        trade_permission = "aggressive"
        regime = "bull"
    elif risk_score >= 55:
        mode = "constructive"
        trade_permission = "normal"
        regime = "bull" if spy_trend == "up" else "neutral"
    elif risk_score >= 40:
        mode = "neutral"
        trade_permission = "reduced"
        regime = "neutral"
    elif risk_score >= 25:
        mode = "risk_off"
        trade_permission = "defensive"
        regime = "bear"
    else:
        mode = "crash_warning"
        trade_permission = "protective"
        regime = "bear"

    broad_market_soft = spy_5d <= 0 or qqq_5d <= 0
    defensive_rotation = defensive_count >= 2 and not growth_leadership and broad_market_soft
    bear_confirmed = (
        spy_trend == "down"
        and qqq_trend == "down"
        and spy_5d < 0
        and qqq_5d < 0
        and vix_5d > 0
    )

    if bear_confirmed:
        mode = "risk_off"
        trade_permission = "short_bias"
        regime = "bear"
    elif defensive_rotation:
        mode = "defensive_rotation"
        trade_permission = "defensive_pause"
        regime = "defensive"

    result = {
        "market_mode": mode,
        "risk_score": risk_score,
        "trade_permission": trade_permission,
        "regime": regime,
        "spy_trend": spy_trend,
        "qqq_trend": qqq_trend,
        "spy_5d_pct": round(spy_5d * 100, 2),
        "qqq_5d_pct": round(qqq_5d * 100, 2),
        "vix_5d_pct": round(vix_5d * 100, 2),
        "rates_5d_pct": round(tnx_5d * 100, 2),
        "sector_leaders": sector_leaders,
        "defensive_leadership": defensive_leadership,
        "growth_leadership": growth_leadership,
        "defensive_count": defensive_count,
        "risk_on_sector_count": risk_on_sector_count,
        "defensive_rotation": defensive_rotation,
        "broad_market_soft": broad_market_soft,
        "bear_confirmed": bear_confirmed
    }

    _market_cache["ts"] = now
    _market_cache["data"] = result
    return result


def risk_parameters(market):
    mode = market.get("market_mode", "neutral")

    if mode == "risk_on":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.15,
            "short_alloc_pct": 0.10,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.08,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.012,
            "trail_long": 0.98,
            "trail_short": 1.02
        }

    if mode == "constructive":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.12,
            "short_alloc_pct": 0.08,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.06,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.012,
            "trail_long": 0.982,
            "trail_short": 1.018
        }

    if mode == "neutral":
        return {
            "max_positions": 3,
            "long_alloc_pct": 0.08,
            "short_alloc_pct": 0.08,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.04,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.010,
            "trail_long": 0.985,
            "trail_short": 1.015
        }

    if mode == "risk_off":
        return {
            "max_positions": 3,
            "long_alloc_pct": 0.05,
            "short_alloc_pct": 0.10,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.08,
            "allow_longs": False,
            "allow_shorts": bool(market.get("bear_confirmed", False)),
            "stop_loss": -0.010,
            "trail_long": 0.985,
            "trail_short": 1.020
        }

    return {
        "max_positions": 2,
        "long_alloc_pct": 0.04,
        "short_alloc_pct": 0.08,
        "long_scale_pct": 0.0,
        "short_scale_pct": 0.04,
        "allow_longs": False,
        "allow_shorts": mode == "crash_warning" and bool(market.get("bear_confirmed", False)),
        "stop_loss": -0.008,
        "trail_long": 0.987,
        "trail_short": 1.018
    }


# ============================================================
# SIGNALS
# ============================================================
def fetch_intraday(symbol):
    df = download_prices(symbol, period="5d", interval="5m")
    if df is None or getattr(df, "empty", True):
        return None
    return df


def intraday_arrays(df):
    return {
        "close": price_series(df, "Close"),
        "open": price_series(df, "Open"),
        "high": price_series(df, "High"),
        "low": price_series(df, "Low"),
        "volume": price_series(df, "Volume")
    }


def signal_score(symbol, prices, market, side="long"):
    if len(prices) < 35:
        return 0.0

    px = float(prices[-1])
    ma8 = sma(prices, 8)
    ma20 = sma(prices, 20)
    ma34 = sma(prices, 34)

    if ma8 is None or ma20 is None or ma34 is None or px <= 0:
        return 0.0

    r3 = pct_change(prices, 3)
    r6 = pct_change(prices, 6)
    r12 = pct_change(prices, 12)
    r24 = pct_change(prices, 24)

    sector = SYMBOL_SECTOR.get(symbol, "UNKNOWN")
    sector_bonus = 0.003 if sector in market.get("sector_leaders", []) else 0.0

    if side == "long":
        if not (px > ma20 and ma8 >= ma20 and ma20 >= ma34):
            return 0.0
        score = (0.35 * r3) + (0.30 * r6) + (0.25 * r12) + (0.10 * r24)
        if px > ma8:
            score += 0.001
        score += sector_bonus
        return max(0.0, float(score))

    if not (px < ma20 and ma8 <= ma20 and ma20 <= ma34):
        return 0.0

    score = (0.35 * -r3) + (0.30 * -r6) + (0.25 * -r12) + (0.10 * -r24)
    if px < ma8:
        score += 0.001
    if sector in market.get("sector_leaders", []):
        score -= 0.003
    return max(0.0, float(score))


def entry_extension_check(symbol, side, arrays):
    closes = arrays.get("close", np.array([]))
    opens = arrays.get("open", np.array([]))
    highs = arrays.get("high", np.array([]))
    lows = arrays.get("low", np.array([]))

    if len(closes) < 20 or len(opens) == 0:
        return True, "ok"

    px = float(closes[-1])
    day_open = float(opens[-1])

    session_bars = min(len(closes), 78)
    session_high = float(np.max(highs[-session_bars:])) if len(highs) >= session_bars else float(np.max(closes[-session_bars:]))
    session_low = float(np.min(lows[-session_bars:])) if len(lows) >= session_bars else float(np.min(closes[-session_bars:]))
    ma20 = sma(closes, 20)

    if day_open <= 0 or px <= 0:
        return True, "ok"

    from_open = (px / day_open) - 1

    if side == "long":
        if from_open > EXTENSION_MAX_ABOVE_DAY_OPEN:
            return False, "extended_above_day_open"
        if from_open > EXTENSION_BIG_MOVE_CONFIRM and session_high > 0 and px >= session_high * EXTENSION_NEAR_HIGH_FACTOR:
            return False, "too_close_to_intraday_high_after_big_move"
        if ma20 and ma20 > 0 and (px / ma20 - 1) > EXTENSION_MAX_FROM_MA20:
            return False, "extended_above_5m_ma20"
        return True, "ok"

    if from_open < -EXTENSION_MAX_BELOW_DAY_OPEN:
        return False, "extended_below_day_open"
    if from_open < -EXTENSION_BIG_MOVE_CONFIRM and session_low > 0 and px <= session_low * EXTENSION_NEAR_LOW_FACTOR:
        return False, "too_close_to_intraday_low_after_big_move"
    if ma20 and ma20 > 0 and (ma20 / px - 1) > EXTENSION_MAX_FROM_MA20:
        return False, "extended_below_5m_ma20"

    return True, "ok"


def scan_signals(market):
    long_signals = []
    short_signals = []
    rejected = []

    for symbol in UNIVERSE:
        if is_in_cooldown(symbol):
            rejected.append({"symbol": symbol, "reason": "cooldown"})
            continue

        df = fetch_intraday(symbol)
        if df is None:
            rejected.append({"symbol": symbol, "reason": "no_data"})
            continue

        arrays = intraday_arrays(df)
        closes = arrays["close"]
        if len(closes) < 35:
            rejected.append({"symbol": symbol, "reason": "not_enough_bars"})
            continue

        px = float(closes[-1])
        long_score = signal_score(symbol, closes, market, "long")
        short_score = signal_score(symbol, closes, market, "short")

        if long_score > 0:
            ok, reason = entry_extension_check(symbol, "long", arrays)
            if ok:
                long_signals.append({
                    "symbol": symbol,
                    "side": "long",
                    "score": round(float(long_score), 6),
                    "price": px,
                    "sector": SYMBOL_SECTOR.get(symbol, "UNKNOWN")
                })
            else:
                rejected.append({"symbol": symbol, "side": "long", "score": round(float(long_score), 6), "reason": reason})

        if short_score > 0:
            ok, reason = entry_extension_check(symbol, "short", arrays)
            if ok:
                short_signals.append({
                    "symbol": symbol,
                    "side": "short",
                    "score": round(float(short_score), 6),
                    "price": px,
                    "sector": SYMBOL_SECTOR.get(symbol, "UNKNOWN")
                })
            else:
                rejected.append({"symbol": symbol, "side": "short", "score": round(float(short_score), 6), "reason": reason})

    long_signals = sorted(long_signals, key=lambda x: x["score"], reverse=True)
    short_signals = sorted(short_signals, key=lambda x: x["score"], reverse=True)
    return long_signals, short_signals, rejected


# ============================================================
# PORTFOLIO OPERATIONS
# ============================================================
def calculate_equity(refresh_prices=True):
    equity = float(portfolio.get("cash", 0.0))

    for symbol, pos in list(portfolio.get("positions", {}).items()):
        px = None
        if refresh_prices:
            px = latest_price(symbol)
        if px is None:
            px = float(pos.get("last_price", pos.get("entry", 0)))

        pos["last_price"] = float(px)

        if pos.get("side", "long") == "short":
            pos["trough"] = min(float(pos.get("trough", px)), float(px))
        else:
            pos["peak"] = max(float(pos.get("peak", px)), float(px))

        equity += position_value(pos, px)

    portfolio["equity"] = round(float(equity), 2)
    portfolio["peak"] = max(float(portfolio.get("peak", equity)), equity)
    portfolio.setdefault("history", []).append(round(float(equity), 2))
    portfolio["history"] = portfolio["history"][-500:]
    update_daily_risk_controls(equity)
    performance_snapshot()
    return equity


def exit_position(symbol, px, reason, market_mode=None, extra=None):
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        return None

    side = pos.get("side", "long")
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry", 0))
    pnl = position_pnl_dollars(pos, px)
    pnl_pct = position_pnl_pct(pos, px)

    if side == "short":
        margin = float(pos.get("margin", entry * shares))
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + margin + pnl
    else:
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + shares * float(px)

    del portfolio["positions"][symbol]
    add_realized_pnl(pnl)
    set_cooldown(symbol)

    details = {
        "exit_reason": reason,
        "pnl_dollars": round(float(pnl), 2),
        "pnl_pct": round(float(pnl_pct) * 100, 2),
        "cooldown_seconds": COOLDOWN_SECONDS,
        "market_mode": market_mode
    }
    if extra:
        details.update(extra)

    record_trade("exit", symbol, side, px, shares, details)

    return {
        "symbol": symbol,
        "side": side,
        "price": round(float(px), 4),
        "shares": round(shares, 6),
        "pnl_dollars": round(float(pnl), 2),
        "pnl_pct": round(float(pnl_pct) * 100, 2),
        "reason": reason
    }


def enter_position(signal, params, market_mode=None):
    symbol = signal["symbol"]
    side = signal["side"]
    px = float(signal["price"])

    if symbol in portfolio.get("positions", {}):
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "already_held"}

    if is_in_cooldown(symbol):
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "cooldown"}

    alloc_pct = float(params["short_alloc_pct"] if side == "short" else params["long_alloc_pct"])
    equity = max(float(portfolio.get("equity", portfolio.get("cash", 0.0))), 0.01)
    alloc = min(float(portfolio.get("cash", 0.0)), equity * alloc_pct)

    if alloc < MIN_TRADE_ALLOC or px <= 0:
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "insufficient_cash_or_bad_price"}

    shares = alloc / px
    portfolio["cash"] = float(portfolio.get("cash", 0.0)) - alloc

    pos = {
        "side": side,
        "entry": px,
        "last_price": px,
        "shares": shares,
        "entry_time": int(time.time()),
        "score": float(signal.get("score", 0.0)),
        "sector": signal.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN")),
        "adds": 0
    }

    if side == "short":
        pos["margin"] = alloc
        pos["trough"] = px
    else:
        pos["peak"] = px

    portfolio.setdefault("positions", {})[symbol] = pos

    record_trade("entry", symbol, side, px, shares, {
        "alloc": round(float(alloc), 2),
        "score": round(float(signal.get("score", 0.0)), 6),
        "sector": pos["sector"],
        "market_mode": market_mode
    })

    return {
        "symbol": symbol,
        "side": side,
        "entry": round(px, 4),
        "shares": round(shares, 6),
        "alloc": round(alloc, 2),
        "score": round(float(signal.get("score", 0.0)), 6)
    }


def manage_exits(params, market):
    exits = []
    mode = market.get("market_mode", "neutral")

    for symbol, pos in list(portfolio.get("positions", {}).items()):
        px = latest_price(symbol)
        if px is None:
            continue

        px = float(px)
        pos["last_price"] = px

        side = pos.get("side", "long")
        pnl_pct = position_pnl_pct(pos, px)

        exit_reason = None

        if pnl_pct <= float(params.get("stop_loss", -0.012)):
            exit_reason = "stop_loss"

        if side == "long":
            pos["peak"] = max(float(pos.get("peak", px)), px)
            if px <= float(pos.get("peak", px)) * float(params.get("trail_long", 0.98)):
                exit_reason = exit_reason or "trailing_stop_long"

            if market.get("bear_confirmed") or mode in ["risk_off", "crash_warning", "defensive_rotation"]:
                exit_reason = exit_reason or "market_regime_protection"

        else:
            pos["trough"] = min(float(pos.get("trough", px)), px)
            if px >= float(pos.get("trough", px)) * float(params.get("trail_short", 1.02)):
                exit_reason = exit_reason or "trailing_stop_short"

            if not market.get("bear_confirmed", False) and mode in ["risk_on", "constructive"]:
                exit_reason = exit_reason or "short_disabled_regime"

        if exit_reason:
            result = exit_position(symbol, px, exit_reason, market_mode=mode)
            if result:
                exits.append(result)

    return exits


def weakest_position_for_rotation(new_signal):
    candidates = []
    now = int(time.time())

    for symbol, pos in portfolio.get("positions", {}).items():
        if symbol == new_signal["symbol"]:
            continue

        px = float(pos.get("last_price", pos.get("entry", 0)))
        pnl_pct = position_pnl_pct(pos, px)
        held_seconds = now - int(pos.get("entry_time", now))
        score = float(pos.get("score", 0.0))
        same_side = pos.get("side", "long") == new_signal["side"]

        # Rotation should usually replace the weakest name on the same side.
        # It may replace a different side only if the market has explicitly changed.
        candidates.append({
            "symbol": symbol,
            "side": pos.get("side", "long"),
            "score": score,
            "pnl_pct": pnl_pct,
            "held_seconds": held_seconds,
            "same_side": same_side,
            "sector": pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        })

    if not candidates:
        return None

    same_side_candidates = [c for c in candidates if c["same_side"]]
    pool = same_side_candidates if same_side_candidates else candidates
    return sorted(pool, key=lambda c: (c["score"], c["pnl_pct"]))[0]


def rotation_allowed(new_signal, weakest, market):
    new_score = float(new_signal.get("score", 0.0))
    weak_score = float(weakest.get("score", 0.0))
    weak_pnl = float(weakest.get("pnl_pct", 0.0))
    held = int(weakest.get("held_seconds", 0))

    required_score = max(
        weak_score * ROTATION_SCORE_MULTIPLIER,
        weak_score + ROTATION_MIN_SCORE_EDGE
    )

    if held < ROTATION_MIN_HOLD_SECONDS:
        return False, {
            "reason": "rotation_min_hold_not_met",
            "held_seconds": held,
            "required_hold_seconds": ROTATION_MIN_HOLD_SECONDS,
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "required_score": round(required_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    if weak_pnl >= ROTATION_KEEP_WINNER_PCT:
        return False, {
            "reason": "keep_winner_guard",
            "weakest_pnl_pct": round(weak_pnl * 100, 2),
            "keep_winner_pct": round(ROTATION_KEEP_WINNER_PCT * 100, 2),
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    if new_score < required_score:
        return False, {
            "reason": "rotation_threshold_not_met",
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "required_score": round(required_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    sector_aligned = new_signal.get("sector") in market.get("sector_leaders", [])
    weak_sector_aligned = weakest.get("sector") in market.get("sector_leaders", [])

    # Require even better evidence when rotating into a sector that is not a current leader.
    if not sector_aligned and weak_sector_aligned:
        required_sector_score = required_score + ROTATION_MIN_SCORE_EDGE
        if new_score < required_sector_score:
            return False, {
                "reason": "sector_alignment_guard",
                "new_score": round(new_score, 6),
                "weakest_score": round(weak_score, 6),
                "required_score": round(required_sector_score, 6),
                "sector_aligned": False,
                "weak_sector_aligned": True,
                "weakest_symbol": weakest.get("symbol")
            }

    return True, {
        "reason": "rotation_to_stronger_signal",
        "new_score": round(new_score, 6),
        "weakest_score": round(weak_score, 6),
        "required_score": round(required_score, 6),
        "held_seconds": held,
        "weakest_pnl_pct": round(weak_pnl * 100, 2),
        "sector_aligned": sector_aligned,
        "weakest_symbol": weakest.get("symbol")
    }


def try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True):
    entries = []
    rotations = []
    blocked_entries = []

    if not new_entries_allowed:
        return entries, rotations, blocked_entries

    max_positions = int(params.get("max_positions", 0))
    mode = market.get("market_mode", "neutral")

    candidate_signals = []
    if params.get("allow_longs", False):
        candidate_signals.extend(long_signals)
    if params.get("allow_shorts", False):
        candidate_signals.extend(short_signals)

    candidate_signals = sorted(candidate_signals, key=lambda x: x["score"], reverse=True)

    for signal in candidate_signals:
        symbol = signal["symbol"]
        side = signal["side"]

        if symbol in portfolio.get("positions", {}):
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "already_held", "score": signal.get("score")})
            continue

        if len(portfolio.get("positions", {})) < max_positions:
            entry = enter_position(signal, params, market_mode=mode)
            if entry and not entry.get("blocked"):
                entries.append(entry)
            else:
                blocked_entries.append(entry)
            continue

        weakest = weakest_position_for_rotation(signal)
        if not weakest:
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "max_positions_full", "score": signal.get("score")})
            continue

        allowed, info = rotation_allowed(signal, weakest, market)
        if not allowed:
            blocked_entries.append({
                "symbol": symbol,
                "side": side,
                "score": signal.get("score"),
                "reason": "max_positions_full_no_rotation",
                "rotation_info": info
            })
            continue

        weakest_symbol = weakest["symbol"]
        pos = portfolio.get("positions", {}).get(weakest_symbol)
        if not pos:
            continue

        px_out = latest_price(weakest_symbol) or float(pos.get("last_price", pos.get("entry", 0)))
        exit_result = exit_position(
            weakest_symbol,
            px_out,
            "rotation_to_stronger_signal",
            market_mode=mode,
            extra={
                "new_score": round(float(signal.get("score", 0.0)), 6),
                "weakest_score": round(float(weakest.get("score", 0.0)), 6),
                "weakest_pnl_pct": round(float(weakest.get("pnl_pct", 0.0)) * 100, 2),
                "held_seconds": weakest.get("held_seconds"),
                "sector_aligned": signal.get("sector") in market.get("sector_leaders", [])
            }
        )

        entry_result = enter_position(signal, params, market_mode=mode)
        rotations.append({
            "out": weakest_symbol,
            "in": symbol,
            "exit": exit_result,
            "entry": entry_result,
            "info": info
        })

    return entries, rotations, blocked_entries


# ============================================================
# RUN CYCLE
# ============================================================
def set_auto_attempt(source):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_attempt_ts"] = ts
    ar["last_attempt_local"] = local_ts_text(ts)
    ar["last_attempt_source"] = source
    ar["last_error"] = None
    ar["last_error_trace"] = None


def set_auto_skip(reason, clock):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_skip_ts"] = ts
    ar["last_skip_local"] = local_ts_text(ts)
    ar["last_skip_reason"] = reason
    ar["market_open_now"] = bool(clock.get("is_open", False))
    ar["market_clock"] = clock


def set_auto_success(source, result, clock):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_run_ts"] = ts
    ar["last_run_local"] = local_ts_text(ts)
    ar["last_run_source"] = source
    ar["last_successful_run_ts"] = ts
    ar["last_successful_run_local"] = local_ts_text(ts)
    ar["last_successful_run_source"] = source
    ar["last_result"] = result
    ar["market_open_now"] = bool(clock.get("is_open", False))
    ar["market_clock"] = clock


def set_auto_error(exc):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ar["last_error"] = str(exc)
    ar["last_error_trace"] = traceback.format_exc()


def run_cycle(source="manual", allow_after_hours=None):
    if allow_after_hours is None:
        allow_after_hours = ALLOW_MANUAL_AFTER_HOURS_TRADING

    with RUN_LOCK:
        set_auto_attempt(source)
        clock = market_clock()
        portfolio.setdefault("auto_runner", default_auto_runner())["market_clock"] = clock
        portfolio["auto_runner"]["market_open_now"] = bool(clock.get("is_open", False))

        # Critical fix: manual and auto runs cannot trade outside regular session unless explicitly enabled.
        market_only = AUTO_RUN_MARKET_ONLY if source == "auto" else True
        if market_only and not clock["is_open"] and not allow_after_hours:
            calculate_equity(refresh_prices=True)
            reason = f"market closed: {clock['reason']}"
            set_auto_skip(reason, clock)
            save_state(portfolio)
            return {
                "skipped": True,
                "reason": reason,
                "market_open_now": False,
                "market_clock": clock,
                "cash": round(float(portfolio.get("cash", 0.0)), 2),
                "equity": round(float(portfolio.get("equity", 0.0)), 2),
                "positions": list(portfolio.get("positions", {}).keys()),
                "performance": performance_snapshot(),
                "risk_controls": get_risk_controls()
            }

        market = market_status(force=True)
        params = risk_parameters(market)

        exits = manage_exits(params, market)
        equity = calculate_equity(refresh_prices=True)
        rc = update_daily_risk_controls(equity)
        prune_cooldowns()

        long_signals, short_signals, rejected = scan_signals(market)

        new_entries_allowed = not bool(rc.get("halted", False)) and not bool(rc.get("profit_guard_active", False))
        entries, rotations, blocked_entries = try_entries_and_rotations(
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed
        )

        equity = calculate_equity(refresh_prices=True)
        rc = update_daily_risk_controls(equity)
        perf = performance_snapshot()

        result = {
            **market,
            "cash": round(float(portfolio.get("cash", 0.0)), 2),
            "equity": round(float(portfolio.get("equity", 0.0)), 2),
            "positions": list(portfolio.get("positions", {}).keys()),
            "risk_parameters": params,
            "risk_controls": rc,
            "new_entries_allowed": bool(new_entries_allowed),
            "entries": entries,
            "exits": exits,
            "rotations": rotations,
            "blocked_entries": blocked_entries[:15],
            "rejected_signals": rejected[:15],
            "long_signals": [s["symbol"] for s in long_signals[:10]],
            "short_signals": [s["symbol"] for s in short_signals[:10]],
            "signals_found": len(long_signals) + len(short_signals),
            "performance": perf,
            "market_clock": clock,
            "market_open_now": bool(clock.get("is_open", False))
        }

        portfolio["last_market"] = market
        set_auto_success(source, result, clock)
        save_state(portfolio)
        return result


def auto_runner_loop():
    while True:
        try:
            if AUTO_RUN_ENABLED:
                run_cycle(source="auto", allow_after_hours=False)
        except Exception as exc:
            set_auto_error(exc)
            try:
                save_state(portfolio)
            except Exception:
                pass

        time.sleep(max(30, AUTO_RUN_INTERVAL_SECONDS))


def ensure_auto_thread():
    global AUTO_THREAD_STARTED
    if AUTO_THREAD_STARTED:
        return

    AUTO_THREAD_STARTED = True
    portfolio.setdefault("auto_runner", default_auto_runner())["thread_started"] = True

    t = threading.Thread(target=auto_runner_loop, daemon=True)
    t.start()



# ============================================================
# DECISION SUPPORT / REVIEW LAYER
# ============================================================
def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def pct(value):
    return round(float(value) * 100, 2)


def money(value):
    return round(float(value), 2)


def _count_by(items, key, default="UNKNOWN"):
    counts = {}
    for item in items:
        value = item.get(key, default) if isinstance(item, dict) else default
        if value in [None, ""]:
            value = default
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _sum_by(items, key, value_key):
    totals = {}
    for item in items:
        bucket = item.get(key, "UNKNOWN") if isinstance(item, dict) else "UNKNOWN"
        if bucket in [None, ""]:
            bucket = "UNKNOWN"
        totals[bucket] = totals.get(bucket, 0.0) + safe_float(item.get(value_key, 0.0))
    return dict(sorted(((k, round(v, 2)) for k, v in totals.items()), key=lambda x: abs(x[1]), reverse=True))


def analyze_trading_journal(limit=20):
    limit = max(5, min(int(limit), 100))
    trades = list(portfolio.get("trades", []))[-limit:]
    exits = [t for t in trades if t.get("action") in ["exit", "rotation_exit"] or "pnl_dollars" in t]
    entries = [t for t in trades if t.get("action") == "entry"]
    rotations = [t for t in trades if t.get("action") == "rotation_exit"]
    stop_losses = [t for t in trades if t.get("exit_reason") == "stop_loss"]
    trailing_exits = [t for t in trades if str(t.get("exit_reason", "")).startswith("trailing_stop")]

    realized = [safe_float(t.get("pnl_dollars", 0.0)) for t in exits if "pnl_dollars" in t]
    wins = [x for x in realized if x >= 0]
    losses = [x for x in realized if x < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    win_rate = round((len(wins) / len(realized)) * 100, 2) if realized else 0.0
    avg_win = round(sum(wins) / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0

    hold_values = [safe_float(t.get("held_seconds"), None) for t in exits if t.get("held_seconds") is not None]
    avg_hold_minutes = round((sum(hold_values) / len(hold_values)) / 60, 1) if hold_values else None

    warnings = []
    if realized and len(losses) > len(wins):
        warnings.append("Loss count is higher than win count in the reviewed sample; tighten entry quality and avoid low-edge rotations.")
    if exits and len(rotations) / max(len(exits), 1) >= 0.35:
        warnings.append("Rotation exits make up a large share of exits; the system may still be churning positions too often.")
    if len(stop_losses) >= max(2, len(exits) * 0.30):
        warnings.append("Stop-loss exits are recurring; entries may be late, too extended, or stops may be too tight for current volatility.")
    if avg_win > 0 and avg_loss < 0 and abs(avg_loss) > avg_win:
        warnings.append("Average loss is larger than average win; focus on earlier invalidation or better profit protection.")
    if not warnings:
        warnings.append("No major recurring execution problem detected from the reviewed sample.")

    last_result = portfolio.get("auto_runner", {}).get("last_result") or {}
    blocked = last_result.get("blocked_entries", []) if isinstance(last_result, dict) else []
    rejected = last_result.get("rejected_signals", []) if isinstance(last_result, dict) else []

    missed_opportunities = []
    for item in blocked[:5]:
        missed_opportunities.append({
            "symbol": item.get("symbol"),
            "side": item.get("side"),
            "reason": item.get("reason"),
            "score": item.get("score"),
            "rotation_info": item.get("rotation_info")
        })
    for item in rejected[:5]:
        missed_opportunities.append({
            "symbol": item.get("symbol"),
            "side": item.get("side"),
            "reason": item.get("reason"),
            "score": item.get("score")
        })

    rules = [
        "Do not rotate unless the new setup clears both the score multiplier and minimum score-edge guard.",
        "Do not add fresh risk when profit guard is active; manage existing positions only.",
        "Treat repeated stop-loss exits in the same symbol as a cooldown problem, not a reason to re-enter faster."
    ]

    if len(rotations) >= 3:
        rules.insert(0, "Cut rotation frequency first; prefer holding the strongest confirmed positions over constantly replacing marginal signals.")
    if len(stop_losses) >= 3:
        rules.insert(0, "After two stop-loss exits in the reviewed sample, require stronger sector alignment before new entries.")

    return {
        "reviewed_trades": len(trades),
        "entries_reviewed": len(entries),
        "exits_reviewed": len(exits),
        "summary": {
            "sample_realized_pnl": money(sum(realized)),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": win_rate,
            "gross_profit": money(gross_profit),
            "gross_loss": money(gross_loss),
            "profit_factor": profit_factor,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "average_hold_minutes": avg_hold_minutes
        },
        "breakdowns": {
            "actions": _count_by(trades, "action"),
            "exit_reasons": _count_by(exits, "exit_reason", default="unknown_exit"),
            "symbols": _count_by(trades, "symbol"),
            "sides": _count_by(trades, "side")
        },
        "diagnosis": warnings,
        "missed_or_blocked_recent_setups": missed_opportunities[:10],
        "rules_to_apply_now": rules[:5],
        "recent_trades": trades
    }


def portfolio_risk_review():
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    equity = max(float(portfolio.get("equity", 0.0)), 0.01)
    cash = float(portfolio.get("cash", 0.0))
    positions = portfolio.get("positions", {}) or {}
    perf = performance_snapshot()
    rc = get_risk_controls()
    market = portfolio.get("last_market") or market_status(force=False)

    rows = []
    sector_exposure = {}
    side_exposure = {}
    total_position_value = 0.0
    open_losers = 0
    open_winners = 0

    for symbol, pos in positions.items():
        px = safe_float(pos.get("last_price", pos.get("entry", 0.0)))
        value = position_value(pos, px)
        pnl_dollars = position_pnl_dollars(pos, px)
        pnl_pct = position_pnl_pct(pos, px)
        sector = pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        side = pos.get("side", "long")
        total_position_value += value
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + value
        side_exposure[side] = side_exposure.get(side, 0.0) + value
        if pnl_dollars >= 0:
            open_winners += 1
        else:
            open_losers += 1
        rows.append({
            "symbol": symbol,
            "side": side,
            "sector": sector,
            "position_value": money(value),
            "position_pct_of_equity": pct(value / equity),
            "pnl_dollars": money(pnl_dollars),
            "pnl_pct": round(pnl_pct * 100, 2),
            "score": round(safe_float(pos.get("score")), 6)
        })

    rows = sorted(rows, key=lambda r: r["position_pct_of_equity"], reverse=True)
    sector_pct = {k: pct(v / equity) for k, v in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)}
    side_pct = {k: pct(v / equity) for k, v in sorted(side_exposure.items(), key=lambda x: x[1], reverse=True)}
    cash_pct = pct(cash / equity)
    invested_pct = pct(total_position_value / equity)

    growth_sectors = ["XLK", "XLY", "XLF"]
    defensive_sectors = ["XLV", "XLP", "XLU"]
    growth_pct = pct(sum(sector_exposure.get(s, 0.0) for s in growth_sectors) / equity)
    defensive_pct = pct(sum(sector_exposure.get(s, 0.0) for s in defensive_sectors) / equity)
    energy_pct = pct(sector_exposure.get("XLE", 0.0) / equity)
    unknown_pct = pct(sector_exposure.get("UNKNOWN", 0.0) / equity)

    vulnerabilities = []
    if rows and rows[0]["position_pct_of_equity"] >= 25:
        vulnerabilities.append(f"Largest position is {rows[0]['symbol']} at {rows[0]['position_pct_of_equity']}% of equity.")
    for sector, value_pct in sector_pct.items():
        if value_pct >= 45:
            vulnerabilities.append(f"Sector concentration is high in {sector} at {value_pct}% of equity.")
    if cash_pct < 15:
        vulnerabilities.append(f"Cash buffer is low at {cash_pct}% of equity.")
    if unknown_pct >= 10:
        vulnerabilities.append(f"Unknown/unmapped sector exposure is {unknown_pct}%; map those tickers before relying on sector controls.")
    if rc.get("profit_guard_active"):
        vulnerabilities.append(f"Profit guard is active: {rc.get('profit_guard_reason', '')}")
    if safe_float(rc.get("intraday_drawdown_pct")) >= 1.0:
        vulnerabilities.append(f"Intraday drawdown is elevated at {rc.get('intraday_drawdown_pct')}% from the day peak.")
    if open_losers > open_winners and len(rows) >= 3:
        vulnerabilities.append("More open positions are losing than winning; avoid adding risk until the open book improves.")
    if not vulnerabilities:
        vulnerabilities.append("No major concentration or drawdown vulnerability detected from current paper state.")

    recommendations = []
    if market.get("bear_confirmed"):
        recommendations.append("Bear confirmation is active; longs should remain blocked and shorts may be allowed only under the short-bias rules.")
    elif market.get("market_mode") in ["risk_on", "constructive"]:
        recommendations.append("Market mode supports long bias, but position additions should still respect profit guard, sector alignment, and max-position limits.")
    else:
        recommendations.append("Market mode is not strongly risk-on; reduce fresh entries and prioritize preserving cash.")

    if growth_pct >= 50:
        recommendations.append("Growth exposure is heavy; avoid adding more XLK/XLY/XLF names unless they clearly outrank existing holdings.")
    if cash_pct < 20:
        recommendations.append("Keep a cash reserve; do not force full deployment just because signals are available.")
    if safe_float(perf.get("unrealized_pnl")) > 0 and safe_float(rc.get("intraday_drawdown_pct")) > 0.75:
        recommendations.append("Open gains exist but intraday giveback is visible; prioritize trailing stops and avoid discretionary re-entry.")

    return {
        "equity": money(equity),
        "cash": money(cash),
        "cash_pct": cash_pct,
        "invested_pct": invested_pct,
        "market_mode": market.get("market_mode"),
        "regime": market.get("regime"),
        "risk_score": market.get("risk_score"),
        "risk_controls": rc,
        "performance": perf,
        "exposures": {
            "by_sector_pct": sector_pct,
            "by_side_pct": side_pct,
            "growth_pct": growth_pct,
            "defensive_pct": defensive_pct,
            "energy_pct": energy_pct,
            "unknown_pct": unknown_pct
        },
        "positions": rows,
        "vulnerabilities": vulnerabilities,
        "recommendations": recommendations
    }


def explain_current_system(force_market=False):
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    market = market_status(force=force_market) if force_market else (portfolio.get("last_market") or market_status(force=False))
    params = risk_parameters(market)
    rc = get_risk_controls()
    clock = market_clock()
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    last_result = ar.get("last_result") or {}

    reasons = []
    if market.get("risk_score", 0) >= 70:
        reasons.append("Risk score is high enough for a long-biased risk-on posture.")
    elif market.get("risk_score", 0) >= 55:
        reasons.append("Risk score is constructive but not fully aggressive.")
    else:
        reasons.append("Risk score is not strong enough for aggressive long exposure.")

    if market.get("bear_confirmed"):
        reasons.append("Bear confirmation is active, so long entries should be blocked and short rules may activate.")
    else:
        reasons.append("Bear confirmation is not active, so shorts remain disabled by design.")

    if rc.get("halted"):
        reasons.append(f"Trading is halted by risk control: {rc.get('halt_reason')}")
    elif rc.get("profit_guard_active"):
        reasons.append(f"Fresh entries are restricted by profit guard: {rc.get('profit_guard_reason')}")
    elif not clock.get("is_open"):
        reasons.append(f"Market is currently closed: {clock.get('reason')}. Manual /paper/run will not trade unless after-hours trading is explicitly enabled.")
    else:
        reasons.append("Market is open and risk controls are not halted.")

    long_allowed = bool(params.get("allow_longs")) and not rc.get("halted")
    short_allowed = bool(params.get("allow_shorts")) and not rc.get("halted")
    new_entries_allowed = bool(last_result.get("new_entries_allowed", not rc.get("halted") and not rc.get("profit_guard_active")))

    return {
        "market_clock": clock,
        "market": market,
        "risk_parameters": params,
        "risk_controls": rc,
        "current_permission": {
            "longs_allowed_by_regime": bool(params.get("allow_longs")),
            "shorts_allowed_by_regime": bool(params.get("allow_shorts")),
            "longs_allowed_now": long_allowed,
            "shorts_allowed_now": short_allowed,
            "new_entries_allowed_last_cycle": new_entries_allowed,
            "max_positions": params.get("max_positions")
        },
        "last_cycle": {
            "last_run_local": ar.get("last_run_local"),
            "last_skip_reason": ar.get("last_skip_reason"),
            "long_signals": last_result.get("long_signals", []),
            "short_signals": last_result.get("short_signals", []),
            "blocked_entries": last_result.get("blocked_entries", [])[:10],
            "rotations": last_result.get("rotations", [])[:10],
            "entries": last_result.get("entries", [])[:10],
            "exits": last_result.get("exits", [])[:10]
        },
        "plain_english": reasons
    }


def daily_trading_plan():
    market = portfolio.get("last_market") or market_status(force=False)
    params = risk_parameters(market)
    rc = get_risk_controls()
    clock = market_clock()

    stance = "balanced / reduced"
    if market.get("bear_confirmed"):
        stance = "defensive / short-bias only"
    elif market.get("market_mode") == "risk_on":
        stance = "long-biased risk-on"
    elif market.get("market_mode") == "constructive":
        stance = "selective long-biased"
    elif market.get("market_mode") in ["risk_off", "defensive_rotation", "crash_warning"]:
        stance = "capital preservation"

    guardrails = [
        f"Max positions: {params.get('max_positions')}",
        f"Longs allowed: {bool(params.get('allow_longs'))}",
        f"Shorts allowed: {bool(params.get('allow_shorts'))}",
        f"Stop loss: {round(abs(float(params.get('stop_loss', 0))) * 100, 2)}%",
        f"Profit guard active: {bool(rc.get('profit_guard_active'))}"
    ]

    if rc.get("profit_guard_active"):
        guardrails.append(f"Profit guard reason: {rc.get('profit_guard_reason')}")
    if rc.get("halted"):
        guardrails.append(f"Risk halt reason: {rc.get('halt_reason')}")

    return {
        "date": today_key(),
        "clock": clock,
        "market_stance": stance,
        "market_mode": market.get("market_mode"),
        "regime": market.get("regime"),
        "risk_score": market.get("risk_score"),
        "sector_leaders": market.get("sector_leaders", []),
        "guardrails": guardrails,
        "checklist": [
            {
                "phase": "Pre-market",
                "time": "Before regular open",
                "steps": [
                    "Open /paper/market?force=1 and confirm market mode, risk score, QQQ/SPY trend, VIX direction, and sector leaders.",
                    "Open /paper/risk-review and verify cash buffer, sector concentration, and open-position P/L.",
                    "Do not override the bot into longs if bear_confirmed is true."
                ]
            },
            {
                "phase": "Opening window",
                "time": "First 30-60 minutes",
                "steps": [
                    "Let the scanner rank setups; avoid manual entries outside the scanner.",
                    "Reject entries that are extended above the 5-minute MA20 or too close to the intraday high after a big move.",
                    "Avoid rotation unless the new score clearly beats the weakest holding by the configured rotation guard."
                ]
            },
            {
                "phase": "Midday management",
                "time": "Late morning to early afternoon",
                "steps": [
                    "Use /paper/explain to confirm why entries, exits, blocks, or rotations happened.",
                    "If profit guard is active, manage existing positions only and do not open fresh risk.",
                    "If losses cluster in the same symbol or sector, respect cooldowns and stop re-entry churn."
                ]
            },
            {
                "phase": "Closing routine",
                "time": "Final 30-45 minutes",
                "steps": [
                    "Review /paper/journal for stop-loss clusters, rotation churn, and average win/loss quality.",
                    "Check whether open winners need trailing-stop protection into the close.",
                    "Do not use /paper/run after close expecting trades; it is blocked by default after regular session."
                ]
            }
        ]
    }

# ============================================================
# HTML DASHBOARD
# ============================================================
DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Scanner + Long/Short Paper System</title>
    <style>
        body {
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
            padding: 22px;
            line-height: 1.35;
        }
        h1 { font-size: 32px; margin-bottom: 20px; }
        .hero { font-size: 24px; font-weight: 800; margin-bottom: 18px; }
        .grid { display: grid; gap: 14px; }
        .card {
            border: 1px solid #1e293b;
            background: #111c31;
            border-radius: 16px;
            padding: 18px;
        }
        .label { color: #94a3b8; letter-spacing: 2px; font-size: 14px; text-transform: uppercase; }
        .value { font-size: 28px; font-weight: 800; margin-top: 8px; }
        .small { font-size: 15px; color: #cbd5e1; }
        a { color: #38bdf8; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        td, th { border-bottom: 1px solid #1e293b; padding: 8px; text-align: left; }
        .good { color: #22c55e; }
        .bad { color: #ef4444; }
        .warn { color: #f59e0b; }
    </style>
</head>
<body>
    <h1>Scanner + Long/Short Paper System</h1>
    <div class="hero">
        Market: {{ market.market_mode }} |
        Risk: {{ market.risk_score }} |
        Regime: {{ market.regime }} |
        Leaders: {{ ", ".join(market.sector_leaders or []) }}
    </div>

    <div class="hero">
        Trading Halted: {{ "YES" if risk.halted else "NO" }} |
        Day P/L: {{ risk.day_pnl_pct }}% |
        Daily Loss: {{ risk.daily_loss_pct }}% |
        Intraday DD: {{ risk.intraday_drawdown_pct }}% |
        Profit Guard: {{ "ON" if risk.profit_guard_active else "OFF" }}
    </div>

    {% if risk.profit_guard_active %}
    <div class="hero warn">Profit Guard Reason: {{ risk.profit_guard_reason }}</div>
    {% endif %}

    <div class="hero">
        Auto Runner: {{ "ON" if auto.enabled else "OFF" }} |
        Thread: {{ "RUNNING" if auto.thread_started else "OFF" }} |
        Market Open: {{ "YES" if auto.market_open_now else "NO" }} |
        Last Run: {{ auto.last_run_local or "never" }} |
        Last Skip: {{ auto.last_skip_reason or "none" }} |
        Error: {{ auto.last_error or "none" }}
    </div>

    <div class="grid">
        <div class="card">
            <div class="label">Equity</div>
            <div class="value">${{ "%.2f"|format(equity) }}</div>
        </div>
        <div class="card">
            <div class="label">Cash</div>
            <div class="value">${{ "%.2f"|format(cash) }}</div>
        </div>
        <div class="card">
            <div class="label">Realized Today</div>
            <div class="value">${{ "%.2f"|format(performance.realized_pnl_today) }}</div>
        </div>
        <div class="card">
            <div class="label">Unrealized</div>
            <div class="value">${{ "%.2f"|format(performance.unrealized_pnl) }}</div>
        </div>
    </div>

    <h2>Open Positions</h2>
    <div class="card">
        <table>
            <tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Last</th><th>P/L $</th><th>P/L %</th><th>Score</th></tr>
            {% for sym, p in performance.open_positions.items() %}
            <tr>
                <td>{{ sym }}</td>
                <td>{{ p.side }}</td>
                <td>{{ p.entry }}</td>
                <td>{{ p.last_price }}</td>
                <td class="{{ 'good' if p.pnl_dollars >= 0 else 'bad' }}">{{ p.pnl_dollars }}</td>
                <td class="{{ 'good' if p.pnl_pct >= 0 else 'bad' }}">{{ p.pnl_pct }}%</td>
                <td>{{ p.score }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <p class="small">
        JSON: <a href="/paper/status">/paper/status</a> Â·
        Market: <a href="/paper/market?force=1">/paper/market?force=1</a> Â·
        Explain: <a href="/paper/explain">/paper/explain</a> Â·
        Journal: <a href="/paper/journal">/paper/journal</a> Â·
        Risk Review: <a href="/paper/risk-review">/paper/risk-review</a> Â·
        Daily Plan: <a href="/paper/daily-plan">/paper/daily-plan</a> Â·
        Run once: <a href="/paper/run">/paper/run</a>
    </p>
</body>
</html>
"""


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def home():
    ensure_auto_thread()
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    return render_template_string(
        DASHBOARD,
        cash=float(portfolio.get("cash", 0.0)),
        equity=float(portfolio.get("equity", 0.0)),
        market=portfolio.get("last_market") or market_status(force=False),
        risk=get_risk_controls(),
        auto=portfolio.setdefault("auto_runner", default_auto_runner()),
        performance=performance_snapshot()
    )


@app.route("/health")
def health():
    return jsonify({"status": "running", "time": local_ts_text(), "market_clock": market_clock()})


@app.route("/paper/status")
def paper_status():
    ensure_auto_thread()
    calculate_equity(refresh_prices=False)
    portfolio.setdefault("auto_runner", default_auto_runner())["market_clock"] = market_clock()
    portfolio["auto_runner"]["market_open_now"] = bool(portfolio["auto_runner"]["market_clock"].get("is_open", False))
    performance_snapshot()
    save_state(portfolio)
    return jsonify(portfolio)


@app.route("/paper/market")
def paper_market():
    force = request.args.get("force", "0") in ["1", "true", "yes"]
    market = market_status(force=force)
    portfolio["last_market"] = market
    save_state(portfolio)
    return jsonify(market)


@app.route("/paper/run")
def paper_run():
    if not key_ok():
        return jsonify({"error": "unauthorized", "hint": "set RUN_KEY or pass ?key=YOUR_KEY"}), 401

    force_after_hours = request.args.get("after_hours", "0").lower() in ["1", "true", "yes", "on"]
    allow_after_hours = ALLOW_MANUAL_AFTER_HOURS_TRADING and force_after_hours

    try:
        result = run_cycle(source="manual", allow_after_hours=allow_after_hours)
        return jsonify(result)
    except Exception as exc:
        set_auto_error(exc)
        save_state(portfolio)
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


@app.route("/paper/reset")
def paper_reset():
    if not key_ok():
        return jsonify({"error": "unauthorized", "hint": "set RUN_KEY or pass ?key=YOUR_KEY"}), 401
    cash = float(request.args.get("cash", "10000"))
    reset_state(cash)
    return jsonify({"status": "reset", "cash": cash, "equity": cash})


@app.route("/paper/close_all")
def close_all():
    if not key_ok():
        return jsonify({"error": "unauthorized", "hint": "set RUN_KEY or pass ?key=YOUR_KEY"}), 401

    clock = market_clock()
    if not clock["is_open"] and not ALLOW_MANUAL_AFTER_HOURS_TRADING:
        return jsonify({
            "blocked": True,
            "reason": f"market closed: {clock['reason']}",
            "market_clock": clock
        }), 409

    exits = []
    mode = portfolio.get("last_market", {}).get("market_mode", "manual_close")
    for symbol, pos in list(portfolio.get("positions", {}).items()):
        px = latest_price(symbol) or float(pos.get("last_price", pos.get("entry", 0)))
        result = exit_position(symbol, px, "manual_close_all", market_mode=mode)
        if result:
            exits.append(result)

    calculate_equity(refresh_prices=True)
    save_state(portfolio)
    return jsonify({"closed": exits, "cash": portfolio["cash"], "equity": portfolio["equity"]})



@app.route("/paper/journal")
def paper_journal():
    ensure_auto_thread()
    limit = request.args.get("limit", "20")
    try:
        limit = int(limit)
    except Exception:
        limit = 20
    return jsonify(analyze_trading_journal(limit=limit))


@app.route("/paper/risk-review")
def paper_risk_review():
    ensure_auto_thread()
    return jsonify(portfolio_risk_review())


@app.route("/paper/explain")
def paper_explain():
    ensure_auto_thread()
    force = request.args.get("force", "0").lower() in ["1", "true", "yes", "on"]
    return jsonify(explain_current_system(force_market=force))


@app.route("/paper/daily-plan")
def paper_daily_plan():
    ensure_auto_thread()
    return jsonify(daily_trading_plan())

@app.route("/paper/config")
def paper_config():
    return jsonify({
        "auto_run_enabled": AUTO_RUN_ENABLED,
        "auto_run_interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "auto_run_market_only": AUTO_RUN_MARKET_ONLY,
        "allow_manual_after_hours_trading": ALLOW_MANUAL_AFTER_HOURS_TRADING,
        "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
        "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT,
        "rotation_score_multiplier": ROTATION_SCORE_MULTIPLIER,
        "rotation_min_score_edge": ROTATION_MIN_SCORE_EDGE,
        "rotation_min_hold_seconds": ROTATION_MIN_HOLD_SECONDS,
        "rotation_keep_winner_pct": ROTATION_KEEP_WINNER_PCT,
        "day_profit_pause_new_entries_pct": DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT,
        "day_profit_hard_lock_pct": DAY_PROFIT_HARD_LOCK_PCT,
        "day_profit_giveback_lock_pct": DAY_PROFIT_GIVEBACK_LOCK_PCT
    })


ensure_auto_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
