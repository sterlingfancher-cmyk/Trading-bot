import os, json, time, datetime, threading, traceback
import numpy as np
import yfinance as yf
import pytz
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
MARKET_CACHE_TTL = int(os.environ.get("MARKET_CACHE_TTL", "300"))

MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "0.03"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("MAX_INTRADAY_DRAWDOWN_PCT", "0.025"))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "1800"))

# ===== ENTRY FILTER / ROTATION CONFIG =====
# These are intentionally conservative. They are designed to keep the bot from
# buying symbols that are already stretched near the intraday high.
EXTENSION_MAX_ABOVE_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_ABOVE_DAY_OPEN", "0.055"))
EXTENSION_MAX_BELOW_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_BELOW_DAY_OPEN", "0.055"))
EXTENSION_NEAR_HIGH_FACTOR = float(os.environ.get("EXTENSION_NEAR_HIGH_FACTOR", "0.996"))
EXTENSION_NEAR_LOW_FACTOR = float(os.environ.get("EXTENSION_NEAR_LOW_FACTOR", "1.004"))
EXTENSION_BIG_MOVE_CONFIRM = float(os.environ.get("EXTENSION_BIG_MOVE_CONFIRM", "0.035"))
EXTENSION_MAX_FROM_MA20 = float(os.environ.get("EXTENSION_MAX_FROM_MA20", "0.035"))

ROTATION_SCORE_MULTIPLIER = float(os.environ.get("ROTATION_SCORE_MULTIPLIER", "1.25"))
ROTATION_MIN_SCORE_EDGE = float(os.environ.get("ROTATION_MIN_SCORE_EDGE", "0.0020"))
ROTATION_MIN_HOLD_SECONDS = int(os.environ.get("ROTATION_MIN_HOLD_SECONDS", "900"))
ROTATION_KEEP_WINNER_PCT = float(os.environ.get("ROTATION_KEEP_WINNER_PCT", "0.012"))
MIN_TRADE_ALLOC = float(os.environ.get("MIN_TRADE_ALLOC", "50"))

AUTO_RUN_ENABLED = os.environ.get("AUTO_RUN_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
AUTO_RUN_INTERVAL_SECONDS = int(os.environ.get("AUTO_RUN_INTERVAL_SECONDS", "300"))
AUTO_RUN_MARKET_ONLY = os.environ.get("AUTO_RUN_MARKET_ONLY", "true").lower() not in ["0", "false", "no", "off"]
MARKET_TZ = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
RUN_LOCK = threading.Lock()
AUTO_THREAD_STARTED = False

# ===== UNIVERSE =====
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

# ===== STATE =====
def today_key():
    return datetime.datetime.now(MARKET_TZ).strftime("%Y-%m-%d")


def default_risk_controls():
    return {
        "date": today_key(),
        "day_start_equity": 10000.0,
        "day_peak_equity": 10000.0,
        "daily_drawdown_pct": 0.0,
        "intraday_drawdown_pct": 0.0,
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
        "open_positions": {}
    }


def default_auto_runner():
    return {
        "enabled": AUTO_RUN_ENABLED,
        "market_only": AUTO_RUN_MARKET_ONLY,
        "interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "market_open_now": False,
        "market_clock": {},

        # Compatibility fields already used by previous dashboard/status JSON.
        "last_run_ts": None,
        "last_run_local": None,
        "last_run_source": None,
        "last_result": None,

        # Cleaner separated fields.
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

    # Backfill newer position metadata so existing paper positions survive deploy.
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
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


portfolio = load_state()

# ===== HELPERS =====
def key_ok():
    supplied = request.args.get("key") or request.headers.get("X-Run-Key")
    return SECRET_KEY == "changeme" or supplied == SECRET_KEY


def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]


def _series_from_df(df, column):
    if df is None or df.empty:
        return np.array([])

    try:
        # yfinance sometimes returns MultiIndex columns, especially with grouped downloads.
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


def latest_price(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="5m", progress=False, auto_adjust=True)
        prices = price_series(df, "Close")
        if len(prices) == 0:
            return None
        return float(prices[-1])
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
    entry = float(pos["entry"])
    if entry <= 0:
        return 0.0
    side = pos.get("side", "long")

    if side == "short":
        return (entry - float(px)) / entry

    return (float(px) - entry) / entry


def position_pnl_dollars(pos, px):
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry", 0))
    side = pos.get("side", "long")

    if side == "short":
        return (entry - float(px)) * shares

    return (float(px) - entry) * shares


def position_value(pos, px):
    shares = float(pos.get("shares", 0))
    side = pos.get("side", "long")

    if side == "short":
        margin = float(pos.get("margin", float(pos.get("entry", 0)) * shares))
        pnl_dollars = (float(pos.get("entry", 0)) - float(px)) * shares
        return margin + pnl_dollars

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
    portfolio["trades"] = portfolio["trades"][-300:]


def get_realized_pnl():
    rp = portfolio.setdefault("realized_pnl", default_realized_pnl())

    if rp.get("date") != today_key():
        rp["date"] = today_key()
        rp["today"] = 0.0
        rp["wins_today"] = 0
        rp["losses_today"] = 0

    rp.setdefault("total", 0.0)
    rp.setdefault("today", 0.0)
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
            "entry_time": pos.get("entry_time")
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


def get_risk_controls():
    rc = portfolio.setdefault("risk_controls", default_risk_controls())
    today = today_key()

    if rc.get("date") != today:
        current_equity = float(portfolio.get("equity", 10000.0))
        rc.clear()
        rc.update({
            "date": today,
            "day_start_equity": current_equity,
            "day_peak_equity": current_equity,
            "daily_drawdown_pct": 0.0,
            "intraday_drawdown_pct": 0.0,
            "halted": False,
            "halt_reason": "",
            "cooldowns": {}
        })

    rc.setdefault("cooldowns", {})
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
    peak = max(float(rc.get("day_peak_equity", equity)), equity, 0.01)

    rc["day_peak_equity"] = peak
    rc["daily_drawdown_pct"] = round(((start - equity) / start) * 100, 3)
    rc["intraday_drawdown_pct"] = round(((peak - equity) / peak) * 100, 3)

    daily_loss_triggered = equity <= start * (1 - MAX_DAILY_LOSS_PCT)
    intraday_dd_triggered = equity <= peak * (1 - MAX_INTRADAY_DRAWDOWN_PCT)

    if daily_loss_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"daily loss limit hit ({MAX_DAILY_LOSS_PCT * 100:.1f}%)"
    elif intraday_dd_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"intraday drawdown limit hit ({MAX_INTRADAY_DRAWDOWN_PCT * 100:.1f}%)"

    return rc


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

# ===== MARKET / ECONOMIC RISK ENGINE =====
def market_status(force=False):
    now = time.time()
    if not force and _market_cache["data"] and now - _market_cache["ts"] < MARKET_CACHE_TTL:
        return _market_cache["data"]

    series = {}
    for symbol in MACRO_SYMBOLS:
        try:
            df = yf.download(symbol, period="30d", interval="1d", progress=False, auto_adjust=True)
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
            "stop_loss": -0.01,
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
            "allow_shorts": True,
            "stop_loss": -0.01,
            "trail_long": 0.985,
            "trail_short": 1.02
        }

    # Defensive rotation and crash-warning both protect capital first.
    return {
        "max_positions": 2,
        "long_alloc_pct": 0.04,
        "short_alloc_pct": 0.08,
        "long_scale_pct": 0.0,
        "short_scale_pct": 0.04,
        "allow_longs": False,
        "allow_shorts": mode == "crash_warning",
        "stop_loss": -0.008,
        "trail_long": 0.987,
        "trail_short": 1.018
    }

# ===== DATA / SIGNALS =====
def fetch_intraday(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None


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
        # Avoid shorting the strongest sectors unless the chart is very weak.
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

    # Use current session stats from the most recent intraday bars. With 5m bars,
    # 78 bars roughly equals one full regular U.S. equity session.
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

    # Short side: avoid shorting after the move is already very stretched lower.
    if from_open < -EXTENSION_MAX_BELOW_DAY_OPEN:
        return False, "extended_below_day_open"
    if from_open < -EXTENSION_BIG_MOVE_CONFIRM and session_low > 0 and px <= session_low * EXTENSION_NEAR_LOW_FACTOR:
        return False, "too_close_to_intraday_low_after_big_move"
    if ma20 and ma20 > 0 and (ma20 / px - 1) > EXTENSION_MAX_FROM_MA20:
        return False, "extended_below_5m_ma20"
    return True, "ok"


def effective_position_score(symbol, pos, px, market):
    score = float(pos.get("score", 0.0))
    sector = pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))

    if sector in market.get("sector_leaders", []):
        score += 0.003

    pnl_pct = position_pnl_pct(pos, px)
    # Reward profitable holdings slightly, punish laggards slightly.
    score += max(min(pnl_pct * 0.15, 0.004), -0.006)
    return float(score)


def choose_rotation_exit(new_symbol, side, new_score, latest_prices, market):
    if len(portfolio.get("positions", {})) == 0:
        return None, "no_positions"

    now = time.time()
    candidates = []

    for symbol, pos in portfolio.get("positions", {}).items():
        if symbol == new_symbol:
            continue

        # Prefer replacing same-side positions. Opposite-side positions can be replaced
        # when the market regime has made them inappropriate.
        pos_side = pos.get("side", "long")
        if pos_side != side:
            if side == "long" and market.get("market_mode") not in ["risk_on", "constructive"]:
                continue
            if side == "short" and market.get("market_mode") not in ["risk_off", "crash_warning"]:
                continue

        px = float(latest_prices.get(symbol, pos.get("last_price", pos.get("entry", 0))))
        pnl_pct = position_pnl_pct(pos, px)
        held_seconds = now - float(pos.get("entry_time", now))

        # Do not churn fresh positions unless they are already losing.
        if held_seconds < ROTATION_MIN_HOLD_SECONDS and pnl_pct > -0.004:
            continue

        # Do not rotate out a healthy winner too quickly.
        if pnl_pct >= ROTATION_KEEP_WINNER_PCT:
            continue

        eff_score = effective_position_score(symbol, pos, px, market)
        candidates.append((eff_score, symbol, px, pnl_pct, held_seconds))

    if not candidates:
        return None, "no_rotation_candidate"

    candidates.sort(key=lambda x: x[0])
    weakest_score, weakest_symbol, weakest_px, weakest_pnl, held_seconds = candidates[0]

    sector = SYMBOL_SECTOR.get(new_symbol, "UNKNOWN")
    sector_edge = sector in market.get("sector_leaders", [])
    required = max(weakest_score * ROTATION_SCORE_MULTIPLIER, weakest_score + ROTATION_MIN_SCORE_EDGE)
    if sector_edge:
        required -= 0.001

    if float(new_score) >= required:
        return weakest_symbol, {
            "reason": "rotation_to_stronger_signal",
            "weakest_score": round(float(weakest_score), 6),
            "new_score": round(float(new_score), 6),
            "weakest_pnl_pct": round(float(weakest_pnl * 100), 2),
            "held_seconds": int(held_seconds),
            "sector_aligned": sector_edge
        }

    return None, {
        "reason": "rotation_threshold_not_met",
        "weakest_symbol": weakest_symbol,
        "weakest_score": round(float(weakest_score), 6),
        "new_score": round(float(new_score), 6),
        "required_score": round(float(required), 6),
        "sector_aligned": sector_edge
    }

# ===== POSITION MANAGEMENT =====
def exit_position(symbol, px, action, market, extra=None):
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        return None

    side = pos.get("side", "long")
    shares = float(pos.get("shares", 0))
    pnl_pct = position_pnl_pct(pos, px)
    pnl_dollars = position_pnl_dollars(pos, px)

    portfolio["cash"] = float(portfolio.get("cash", 0)) + position_value(pos, px)
    add_realized_pnl(pnl_dollars)

    details = {
        "pnl_pct": round(float(pnl_pct * 100), 2),
        "pnl_dollars": round(float(pnl_dollars), 2),
        "market_mode": market.get("market_mode", "unknown"),
        "cooldown_seconds": COOLDOWN_SECONDS
    }
    if extra:
        details.update(extra)

    record_trade(action, symbol, side, px, shares, details)
    set_cooldown(symbol)
    del portfolio["positions"][symbol]
    return {"symbol": symbol, "action": action, **details}


def enter_position(symbol, side, px, alloc, score, market):
    if px is None or float(px) <= 0:
        return None

    alloc = float(max(0.0, alloc))
    cash = float(portfolio.get("cash", 0.0))
    alloc = min(alloc, cash)
    if alloc < MIN_TRADE_ALLOC:
        return None

    shares = alloc / float(px)
    portfolio["cash"] = cash - alloc

    pos = {
        "side": side,
        "entry": float(px),
        "last_price": float(px),
        "shares": float(shares),
        "adds": 0,
        "entry_time": int(time.time()),
        "score": float(score),
        "sector": SYMBOL_SECTOR.get(symbol, "UNKNOWN")
    }

    if side == "short":
        pos["margin"] = alloc
        pos["trough"] = float(px)
    else:
        pos["peak"] = float(px)

    portfolio.setdefault("positions", {})[symbol] = pos
    record_trade("entry", symbol, side, px, shares, {
        "score": round(float(score), 6),
        "alloc": round(float(alloc), 2),
        "market_mode": market.get("market_mode", "unknown"),
        "sector": pos["sector"]
    })
    return pos


def refresh_equity_from_positions():
    equity = float(portfolio.get("cash", 0.0))

    for _, pos in portfolio.get("positions", {}).items():
        px = float(pos.get("last_price", pos.get("entry", 0)))
        equity += position_value(pos, px)

    portfolio["equity"] = equity
    portfolio["peak"] = max(float(portfolio.get("peak", equity)), equity)
    return equity


def liquidate_all_positions(reason, market, data_arrays=None):
    closed = []
    latest_prices = {}

    for s, arrays in (data_arrays or {}).items():
        closes = arrays.get("close", np.array([])) if isinstance(arrays, dict) else np.array([])
        if len(closes) > 0:
            latest_prices[s] = float(closes[-1])

    for s in list(portfolio.get("positions", {}).keys()):
        pos = portfolio["positions"].get(s)
        px = latest_prices.get(s)
        if px is None:
            px = latest_price(s)
        if px is None:
            px = float(pos.get("last_price", pos.get("entry", 0)))

        result = exit_position(s, px, "halt_exit", market, {"halt_reason": reason})
        if result:
            closed.append(result)

    return closed

# ===== ENGINE =====
def run_engine():
    market = market_status(force=True)
    params = risk_parameters(market)
    regime = market.get("regime", "neutral")
    risk_controls = get_risk_controls()
    halted_exits = []
    blocked_entries = []
    rotations = []

    data_arrays = {}
    latest_prices = {}

    for symbol in UNIVERSE:
        df = fetch_intraday(symbol)
        if df is None:
            continue
        arrays = intraday_arrays(df)
        closes = arrays.get("close", np.array([]))
        if len(closes) == 0:
            continue
        data_arrays[symbol] = arrays
        latest_prices[symbol] = float(closes[-1])

    # Mark open positions to market and update peaks/troughs.
    for s, pos in list(portfolio.get("positions", {}).items()):
        px = latest_prices.get(s)
        if px is None:
            px = latest_price(s)
        if px is None:
            px = float(pos.get("last_price", pos.get("entry", 0)))

        pos["last_price"] = float(px)
        if pos.get("side", "long") == "short":
            pos["trough"] = min(float(pos.get("trough", px)), float(px))
        else:
            pos["peak"] = max(float(pos.get("peak", px)), float(px))

    equity = refresh_equity_from_positions()
    risk_controls = update_daily_risk_controls(equity)
    prune_cooldowns()

    if risk_controls.get("halted", False) and portfolio.get("positions"):
        halted_exits.extend(liquidate_all_positions(risk_controls.get("halt_reason", "risk halt"), market, data_arrays))
        equity = refresh_equity_from_positions()
        risk_controls = update_daily_risk_controls(equity)

    # Exit logic: stop loss, trailing stops, and regime mismatch exits.
    if not risk_controls.get("halted", False):
        for s, pos in list(portfolio.get("positions", {}).items()):
            px = latest_prices.get(s, float(pos.get("last_price", pos.get("entry", 0))))
            side = pos.get("side", "long")
            pnl = position_pnl_pct(pos, px)
            exit_reason = None

            if pnl <= float(params.get("stop_loss", -0.012)):
                exit_reason = "stop_loss"
            elif side == "long":
                peak = float(pos.get("peak", px))
                if peak > 0 and px <= peak * float(params.get("trail_long", 0.98)):
                    exit_reason = "trailing_stop_long"
                elif not params.get("allow_longs", True) and market.get("market_mode") in ["risk_off", "crash_warning", "defensive_rotation"]:
                    exit_reason = "regime_exit_long"
            else:
                trough = float(pos.get("trough", px))
                if trough > 0 and px >= trough * float(params.get("trail_short", 1.02)):
                    exit_reason = "trailing_stop_short"
                elif not params.get("allow_shorts", False) and market.get("market_mode") in ["risk_on", "constructive"]:
                    exit_reason = "regime_exit_short"

            if exit_reason:
                exit_position(s, px, "exit", market, {"exit_reason": exit_reason})

    interim_equity = refresh_equity_from_positions()
    risk_controls = update_daily_risk_controls(interim_equity)

    if risk_controls.get("halted", False) and portfolio.get("positions"):
        halted_exits.extend(liquidate_all_positions(risk_controls.get("halt_reason", "risk halt"), market, data_arrays))
        interim_equity = refresh_equity_from_positions()
        risk_controls = update_daily_risk_controls(interim_equity)

    longs = []
    shorts = []
    for s, arrays in data_arrays.items():
        if s in ["SPY", "QQQ"]:
            # Keep SPY/QQQ as macro inputs. Avoid using them as individual trades.
            continue
        if s in portfolio.get("positions", {}) or is_in_cooldown(s):
            continue

        closes = arrays.get("close", np.array([]))
        long_score = signal_score(s, closes, market, "long")
        short_score = signal_score(s, closes, market, "short")

        if long_score >= 0.0045:
            longs.append((s, long_score))
        if short_score >= 0.0050:
            shorts.append((s, short_score))

    longs = sorted(longs, key=lambda x: x[1], reverse=True)
    shorts = sorted(shorts, key=lambda x: x[1], reverse=True)

    new_entries_allowed = (
        not risk_controls.get("halted", False)
        and market.get("trade_permission") not in ["protective", "defensive_pause"]
    )

    def maybe_enter(symbol, side, score):
        nonlocal risk_controls
        if not new_entries_allowed:
            return
        if symbol in portfolio.get("positions", {}):
            return
        if is_in_cooldown(symbol):
            return
        if side == "long" and not params.get("allow_longs", False):
            return
        if side == "short" and not params.get("allow_shorts", False):
            return

        arrays = data_arrays.get(symbol)
        if not arrays:
            return
        closes = arrays.get("close", np.array([]))
        if len(closes) == 0:
            return
        px = float(closes[-1])

        ok, reason = entry_extension_check(symbol, side, arrays)
        if not ok:
            blocked_entries.append({
                "symbol": symbol,
                "side": side,
                "reason": reason,
                "score": round(float(score), 6),
                "price": round(float(px), 4)
            })
            return

        max_positions = int(params.get("max_positions", 4))
        if len(portfolio.get("positions", {})) >= max_positions:
            rotate_symbol, rotate_info = choose_rotation_exit(symbol, side, score, latest_prices, market)
            if not rotate_symbol:
                blocked_entries.append({
                    "symbol": symbol,
                    "side": side,
                    "reason": "max_positions_full_no_rotation",
                    "score": round(float(score), 6),
                    "rotation_info": rotate_info
                })
                return

            rotate_pos = portfolio["positions"].get(rotate_symbol)
            rotate_px = latest_prices.get(rotate_symbol, float(rotate_pos.get("last_price", rotate_pos.get("entry", 0))))
            result = exit_position(rotate_symbol, rotate_px, "rotation_exit", market, rotate_info if isinstance(rotate_info, dict) else {"rotation_reason": rotate_info})
            rotations.append({"out": rotate_symbol, "in": symbol, "exit": result, "info": rotate_info})
            risk_controls = update_daily_risk_controls(refresh_equity_from_positions())
            if risk_controls.get("halted", False):
                return

        alloc_pct = float(params.get("long_alloc_pct" if side == "long" else "short_alloc_pct", 0.1))
        alloc = float(portfolio.get("cash", 0.0)) * alloc_pct
        enter_position(symbol, side, px, alloc, score, market)

    if new_entries_allowed:
        for s, score in longs:
            if not params.get("allow_longs", False):
                break
            maybe_enter(s, "long", score)
            if risk_controls.get("halted", False):
                break

        for s, score in shorts:
            if not params.get("allow_shorts", False):
                break
            maybe_enter(s, "short", score)
            if risk_controls.get("halted", False):
                break

    final_equity = refresh_equity_from_positions()
    portfolio["history"].append(float(final_equity))
    portfolio["history"] = portfolio["history"][-500:]
    portfolio["last_market"] = market
    risk_controls = update_daily_risk_controls(final_equity)
    perf = performance_snapshot()
    save_state(portfolio)

    return {
        "equity": round(float(portfolio["equity"]), 2),
        "cash": round(float(portfolio["cash"]), 2),
        "regime": regime,
        "market_mode": market.get("market_mode"),
        "risk_score": market.get("risk_score"),
        "trade_permission": market.get("trade_permission"),
        "positions": list(portfolio.get("positions", {}).keys()),
        "halted_exits": halted_exits,
        "rotations": rotations,
        "blocked_entries": blocked_entries[-20:],
        "signals_found": len(longs) + len(shorts),
        "long_signals": [s for s, _ in longs],
        "short_signals": [s for s, _ in shorts],
        "new_entries_allowed": new_entries_allowed,
        "risk_controls": risk_controls,
        "risk_parameters": params,
        "performance": perf,
        "sector_leaders": market.get("sector_leaders", []),
        "defensive_leadership": market.get("defensive_leadership", False),
        "growth_leadership": market.get("growth_leadership", False),
        "defensive_count": market.get("defensive_count", 0),
        "risk_on_sector_count": market.get("risk_on_sector_count", 0),
        "defensive_rotation": market.get("defensive_rotation", False),
        "broad_market_soft": market.get("broad_market_soft", False),
        "bear_confirmed": market.get("bear_confirmed", False)
    }

# ===== AUTO-RUNNER =====
def local_now():
    return datetime.datetime.now(MARKET_TZ)


def market_clock_status():
    now = local_now()
    regular_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
    regular_close = now.replace(hour=15, minute=0, second=0, microsecond=0)

    if now.weekday() >= 5:
        is_open = False
        reason = "weekend"
    elif now < regular_open:
        is_open = False
        reason = "before_regular_session"
    elif now > regular_close:
        is_open = False
        reason = "after_regular_session"
    else:
        is_open = True
        reason = "regular_session_open"

    return {
        "is_open": is_open,
        "reason": reason,
        "timezone": str(MARKET_TZ),
        "now_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_open_local": regular_open.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_close_local": regular_close.strftime("%Y-%m-%d %H:%M:%S %Z")
    }


def market_open_now():
    return market_clock_status()["is_open"]


def update_auto_runner_status(extra=None):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    clock = market_clock_status()
    ar["enabled"] = AUTO_RUN_ENABLED
    ar["market_only"] = AUTO_RUN_MARKET_ONLY
    ar["interval_seconds"] = AUTO_RUN_INTERVAL_SECONDS
    ar["market_open_now"] = clock["is_open"]
    ar["market_clock"] = clock
    ar["thread_started"] = AUTO_THREAD_STARTED

    if extra:
        ar.update(extra)

    try:
        save_state(portfolio)
    except Exception:
        pass

    return ar


def run_engine_locked(source="manual"):
    now = local_now()
    update_auto_runner_status({
        "last_attempt_ts": int(time.time()),
        "last_attempt_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "last_attempt_source": source
    })

    if not RUN_LOCK.acquire(blocking=False):
        skip_now = local_now()
        update_auto_runner_status({
            "last_skip_ts": int(time.time()),
            "last_skip_local": skip_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "last_skip_reason": "engine already running",
            "last_run_source": source
        })
        return {"error": "engine already running", "source": source}

    try:
        result = run_engine()
        done = local_now()
        update_auto_runner_status({
            # Compatibility fields
            "last_run_ts": int(time.time()),
            "last_run_local": done.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "last_run_source": source,
            "last_result": result,

            # Cleaner fields
            "last_successful_run_ts": int(time.time()),
            "last_successful_run_local": done.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "last_successful_run_source": source,

            "last_error": None,
            "last_error_trace": None,
            "last_skip_reason": None
        })
        return result
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}"
        update_auto_runner_status({
            "last_error": err,
            "last_error_trace": traceback.format_exc()[-3000:],
            "last_run_source": source
        })
        return {"error": err, "source": source}
    finally:
        RUN_LOCK.release()


def auto_runner_loop():
    update_auto_runner_status({"last_skip_reason": "auto runner started"})

    while True:
        try:
            clock = market_clock_status()
            if AUTO_RUN_MARKET_ONLY and not clock["is_open"]:
                now = local_now()
                update_auto_runner_status({
                    "last_skip_ts": int(time.time()),
                    "last_skip_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    "last_skip_reason": f"market closed: {clock['reason']}"
                })
            else:
                run_engine_locked(source="auto")
        except Exception:
            update_auto_runner_status({
                "last_error": "auto loop error",
                "last_error_trace": traceback.format_exc()[-3000:]
            })

        time.sleep(max(30, AUTO_RUN_INTERVAL_SECONDS))


def start_auto_runner_once():
    global AUTO_THREAD_STARTED
    if AUTO_THREAD_STARTED or not AUTO_RUN_ENABLED:
        update_auto_runner_status()
        return

    AUTO_THREAD_STARTED = True
    t = threading.Thread(target=auto_runner_loop, daemon=True)
    t.start()
    update_auto_runner_status({"thread_started": True})

# ===== ROUTES =====
@app.route("/health")
def health():
    ar = update_auto_runner_status()
    return jsonify({
        "ok": True,
        "time_local": local_now().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "auto_runner": ar,
        "equity": round(float(portfolio.get("equity", 0)), 2),
        "positions": list(portfolio.get("positions", {}).keys())
    })


@app.route("/paper/market")
def paper_market():
    force = request.args.get("force", "0") in ["1", "true", "yes"]
    return jsonify(market_status(force=force))


@app.route("/paper/status")
def paper_status():
    update_auto_runner_status()
    perf = performance_snapshot()
    save_state(portfolio)
    return jsonify({
        "cash": float(portfolio.get("cash", 0)),
        "equity": float(portfolio.get("equity", 0)),
        "peak": float(portfolio.get("peak", 0)),
        "history": portfolio.get("history", []),
        "positions": portfolio.get("positions", {}),
        "trades": portfolio.get("trades", []),
        "last_market": portfolio.get("last_market", {}),
        "risk_controls": get_risk_controls(),
        "performance": perf,
        "auto_runner": portfolio.get("auto_runner", default_auto_runner())
    })


@app.route("/paper/run")
def paper_run():
    if not key_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(run_engine_locked(source=request.args.get("source", "manual")))


@app.route("/paper/reset")
def paper_reset():
    if not key_ok():
        return jsonify({"error": "unauthorized"}), 401
    cash = float(request.args.get("cash", "10000"))
    reset_state(cash)
    return jsonify({"ok": True, "cash": cash, "state": portfolio})


@app.route("/")
def dashboard():
    market = portfolio.get("last_market") or market_status(force=False)
    ar = update_auto_runner_status()
    rc = get_risk_controls()
    perf = performance_snapshot()
    history = portfolio.get("history", [])

    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Scanner + Long/Short Paper System</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { margin: 0; padding: 28px; font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; }
    h1 { font-size: 24px; margin: 0 0 24px; }
    .line { font-size: 22px; font-weight: 800; line-height: 1.45; margin: 8px 0; }
    .small { color: #cbd5e1; font-size: 15px; margin-top: 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 20px; }
    .card { background: #111c33; border: 1px solid #1e293b; border-radius: 12px; padding: 14px; }
    .label { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .value { font-size: 20px; font-weight: 800; margin-top: 6px; }
    canvas { margin-top: 24px; background: #111827; border-radius: 10px; padding: 10px; }
    a { color: #38bdf8; }
    pre { white-space: pre-wrap; background: #0b1220; padding: 12px; border-radius: 10px; border: 1px solid #1e293b; }
  </style>
</head>
<body>
  <h1>ð Scanner + Long/Short Paper System</h1>
  <div class="line">Market: {{ market.market_mode }} | Risk: {{ market.risk_score }} | Regime: {{ market.regime }} | Leaders: {{ leaders }}</div>
  <div class="line">Trading Halted: {{ halted }} | Daily DD: {{ daily_dd }}% | Intraday DD: {{ intraday_dd }}% | Cooldowns: {{ cooldowns }}</div>
  <div class="line">Auto Runner: {{ auto_on }} | Thread: {{ thread }} | Market Open: {{ market_open }} | Last Run: {{ last_run }} | Skip: {{ skip }} | Error: {{ error }}</div>
  <div class="line">Realized Today: ${{ realized_today }} | Unrealized: ${{ unrealized }} | Open Positions: {{ positions }}</div>

  <canvas id="equityChart" height="120"></canvas>

  <div class="grid">
    <div class="card"><div class="label">Equity</div><div class="value">${{ equity }}</div></div>
    <div class="card"><div class="label">Cash</div><div class="value">${{ cash }}</div></div>
    <div class="card"><div class="label">Trade Permission</div><div class="value">{{ market.trade_permission }}</div></div>
    <div class="card"><div class="label">Clock</div><div class="value">{{ clock_reason }}</div></div>
  </div>

  <p class="small">
    JSON: <a href="/paper/status">/paper/status</a> Â· Market: <a href="/paper/market?force=1">/paper/market?force=1</a> Â· Run once: <a href="/paper/run">/paper/run</a>
  </p>

<script>
const historyData = {{ history_json | safe }};
const labels = historyData.map((_, i) => i);
new Chart(document.getElementById('equityChart'), {
  type: 'line',
  data: {
    labels,
    datasets: [{ label: 'Equity', data: historyData, borderWidth: 3, pointRadius: 2, tension: 0.15 }]
  },
  options: {
    responsive: true,
    plugins: { legend: { labels: { color: '#e5e7eb' } } },
    scales: {
      x: { ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(148,163,184,0.08)' } },
      y: { ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(148,163,184,0.08)' } }
    }
  }
});
</script>
</body>
</html>
"""

    return render_template_string(
        html,
        market=market,
        leaders=", ".join(market.get("sector_leaders", [])),
        halted="YES" if rc.get("halted") else "NO",
        daily_dd=rc.get("daily_drawdown_pct", 0),
        intraday_dd=rc.get("intraday_drawdown_pct", 0),
        cooldowns=len(rc.get("cooldowns", {})),
        auto_on="ON" if ar.get("enabled") else "OFF",
        thread="RUNNING" if ar.get("thread_started") else "STOPPED",
        market_open="YES" if ar.get("market_open_now") else "NO",
        last_run=ar.get("last_successful_run_local") or ar.get("last_run_local") or "never",
        skip=ar.get("last_skip_reason") or "none",
        error=ar.get("last_error") or "none",
        realized_today=round(float(perf.get("realized_pnl_today", 0)), 2),
        unrealized=round(float(perf.get("unrealized_pnl", 0)), 2),
        equity=round(float(portfolio.get("equity", 0)), 2),
        cash=round(float(portfolio.get("cash", 0)), 2),
        positions=", ".join(portfolio.get("positions", {}).keys()) or "none",
        clock_reason=ar.get("market_clock", {}).get("reason", "unknown"),
        history_json=json.dumps(history if history else [portfolio.get("equity", 10000.0)])
    )


# Start the auto runner at import time. This avoids Flask before_first_request,
# which is unavailable in newer Flask versions and caused prior deployment crashes.
try:
    start_auto_runner_once()
except Exception:
    pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
