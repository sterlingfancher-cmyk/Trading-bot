import os, json, time, datetime, threading, traceback
import numpy as np
import yfinance as yf
import pytz
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"
MARKET_CACHE_TTL = 300

MAX_DAILY_LOSS_PCT = 0.03
MAX_INTRADAY_DRAWDOWN_PCT = 0.025
COOLDOWN_SECONDS = 1800

AUTO_RUN_ENABLED = os.environ.get("AUTO_RUN_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
AUTO_RUN_INTERVAL_SECONDS = int(os.environ.get("AUTO_RUN_INTERVAL_SECONDS", "300"))
AUTO_RUN_MARKET_ONLY = os.environ.get("AUTO_RUN_MARKET_ONLY", "true").lower() not in ["0", "false", "no", "off"]
MARKET_TZ = pytz.timezone("America/Chicago")
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

_market_cache = {"ts": 0, "data": None}

# ===== STATE =====
def today_key():
    return time.strftime("%Y-%m-%d", time.gmtime())


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


def default_auto_runner():
    return {
        "enabled": AUTO_RUN_ENABLED,
        "market_only": AUTO_RUN_MARKET_ONLY,
        "interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "market_open_now": False,
        "last_run_ts": None,
        "last_run_local": None,
        "last_run_source": None,
        "last_result": None,
        "last_error": None,
        "last_skip_reason": None,
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
        "auto_runner": default_auto_runner()
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


def price_series(df, column="Close"):
    if df is None or df.empty or column not in df:
        return np.array([])
    return clean(df[column].values)


def latest_price(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="5m", progress=False, auto_adjust=True)
        prices = price_series(df)
        if len(prices) == 0:
            return None
        return float(prices[-1])
    except Exception:
        return None


def pct_change(prices, bars):
    if len(prices) <= bars or prices[-bars] == 0:
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
    side = pos.get("side", "long")

    if side == "short":
        return (entry - px) / entry

    return (px - entry) / entry


def position_value(pos, px):
    shares = float(pos["shares"])
    side = pos.get("side", "long")

    if side == "short":
        margin = float(pos.get("margin", float(pos["entry"]) * shares))
        pnl_dollars = (float(pos["entry"]) - px) * shares
        return margin + pnl_dollars

    return shares * px


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

    portfolio["trades"].append(trade)
    portfolio["trades"] = portfolio["trades"][-150:]


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
            prices = price_series(df)
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
    defensive_leadership = any(s in sector_leaders for s in ["XLU", "XLV", "XLP"])
    growth_leadership = any(s in sector_leaders for s in ["XLK", "XLY"])

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

    defensive_rotation = defensive_leadership and not growth_leadership
    broad_market_soft = spy_5d <= 0 or qqq_5d <= 0
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
        "defensive_rotation": defensive_rotation,
        "broad_market_soft": broad_market_soft,
        "bear_confirmed": bear_confirmed
    }

    _market_cache["ts"] = now
    _market_cache["data"] = result
    portfolio["last_market"] = result

    return result


def risk_parameters(market):
    mode = market.get("market_mode", "neutral")

    if mode == "risk_on":
        return {
            "max_positions": 4, "long_alloc_pct": 0.15, "short_alloc_pct": 0.10,
            "long_scale_pct": 0.00, "short_scale_pct": 0.08,
            "allow_longs": True, "allow_shorts": False,
            "stop_loss": -0.012, "trail_long": 0.98, "trail_short": 1.02
        }

    if mode == "constructive":
        return {
            "max_positions": 4, "long_alloc_pct": 0.10, "short_alloc_pct": 0.15,
            "long_scale_pct": 0.00, "short_scale_pct": 0.12,
            "allow_longs": True, "allow_shorts": False,
            "stop_loss": -0.012, "trail_long": 0.98, "trail_short": 1.03
        }

    if mode == "defensive_rotation":
        return {
            "max_positions": 3, "long_alloc_pct": 0.00, "short_alloc_pct": 0.00,
            "long_scale_pct": 0.00, "short_scale_pct": 0.00,
            "allow_longs": False, "allow_shorts": False,
            "stop_loss": -0.015, "trail_long": 0.98, "trail_short": 1.025
        }

    if mode == "neutral":
        return {
            "max_positions": 4, "long_alloc_pct": 0.15, "short_alloc_pct": 0.00,
            "long_scale_pct": 0.00, "short_scale_pct": 0.00,
            "allow_longs": False, "allow_shorts": False,
            "stop_loss": -0.018, "trail_long": 0.975, "trail_short": 1.025
        }

    if mode == "risk_off":
        bear_confirmed = bool(market.get("bear_confirmed", False))
        return {
            "max_positions": 3, "long_alloc_pct": 0.00, "short_alloc_pct": 0.22 if bear_confirmed else 0.00,
            "long_scale_pct": 0.00, "short_scale_pct": 0.12 if bear_confirmed else 0.00,
            "allow_longs": False, "allow_shorts": bear_confirmed,
            "stop_loss": -0.015, "trail_long": 0.98, "trail_short": 1.025
        }

    return {
        "max_positions": 2, "long_alloc_pct": 0.00, "short_alloc_pct": 0.18,
        "long_scale_pct": 0.00, "short_scale_pct": 0.00,
        "allow_longs": False, "allow_shorts": True,
        "stop_loss": -0.012, "trail_long": 0.985, "trail_short": 1.02
    }

# ===== SCANNER =====
def pre_scan(symbols, regime):
    scored = []

    for s in symbols:
        try:
            df = yf.download(s, period="5d", interval="15m", progress=False, auto_adjust=True)
            prices = price_series(df)

            if len(prices) < 20:
                continue

            r20 = pct_change(prices, 20)

            if regime == "bear":
                if r20 < -0.003:
                    scored.append((s, abs(r20)))
                elif r20 > 0.006:
                    scored.append((s, r20 * 0.5))
            elif regime == "defensive":
                if r20 > 0.008:
                    scored.append((s, r20 * 0.25))
            else:
                if r20 > 0.005:
                    scored.append((s, r20))

        except Exception:
            continue

    return [s for s, _ in sorted(scored, key=lambda x: x[1], reverse=True)[:30]]

# ===== DATA =====
def load_data(symbols):
    data5, data15 = {}, {}

    for s in symbols:
        try:
            df5 = yf.download(s, period="2d", interval="5m", progress=False, auto_adjust=True)
            df15 = yf.download(s, period="5d", interval="15m", progress=False, auto_adjust=True)

            c5 = price_series(df5)
            c15 = price_series(df15)

            if len(c5) > 20 and len(c15) > 20:
                data5[s] = c5
                data15[s] = c15
        except Exception:
            continue

    return data5, data15

# ===== REGIME =====
def get_regime():
    try:
        return market_status().get("regime", "neutral")
    except Exception:
        return "neutral"

# ===== SIGNALS =====
def generate_signals(data5, data15, regime):
    longs, shorts = [], []

    for s in data5:
        try:
            p5 = data5[s]
            p15 = data15[s]

            if len(p5) < 20 or len(p15) < 20:
                continue

            px = float(p5[-1])
            r3 = pct_change(p5, 3)
            r12 = pct_change(p5, 12)
            score = r3 * 0.6 + r12 * 0.4

            if regime in ["bull"]:
                if px > np.mean(p5[-20:]) and p15[-1] > np.mean(p15[-20:]):
                    if px >= max(p5[-10:]) * 0.992 and r3 > 0 and score > 0.0035:
                        longs.append((s, float(score)))

            if regime == "bear":
                if px < np.mean(p5[-20:]) and p15[-1] < np.mean(p15[-20:]):
                    if px <= min(p5[-10:]) * 1.005 and r3 < 0 and score < -0.0015:
                        shorts.append((s, float(abs(score))))

        except Exception:
            continue

    longs = sorted(longs, key=lambda x: x[1], reverse=True)[:5]
    shorts = sorted(shorts, key=lambda x: x[1], reverse=True)[:3]

    return longs, shorts

# ===== HALT LIQUIDATION =====
def liquidate_all_positions(reason, market, data5=None):
    closed = []

    for s, pos in list(portfolio["positions"].items()):
        px = None

        try:
            if data5 and s in data5 and len(data5[s]) > 0:
                px = float(data5[s][-1])
        except Exception:
            px = None

        if px is None:
            px = latest_price(s)

        if px is None:
            px = float(pos.get("last_price", pos["entry"]))

        side = pos.get("side", "long")
        shares = float(pos["shares"])
        pnl = position_pnl_pct(pos, px)

        portfolio["cash"] += position_value(pos, px)
        record_trade("halt_exit", s, side, px, shares, {
            "pnl_pct": round(float(pnl * 100), 2),
            "market_mode": market.get("market_mode", "unknown"),
            "halt_reason": reason,
            "cooldown_seconds": COOLDOWN_SECONDS
        })
        set_cooldown(s)
        closed.append(s)
        del portfolio["positions"][s]

    return closed


def refresh_equity_from_positions():
    equity = float(portfolio["cash"])

    for _, pos in portfolio["positions"].items():
        px = float(pos.get("last_price", pos["entry"]))
        equity += position_value(pos, px)

    portfolio["equity"] = equity
    portfolio["peak"] = max(float(portfolio.get("peak", equity)), equity)
    return equity

# ===== ENGINE =====
def run_engine():
    market = market_status(force=True)
    params = risk_parameters(market)
    regime = market.get("regime", "neutral")
    halted_exits = []

    if market.get("regime") in ["defensive", "neutral", "chop"] or market.get("defensive_rotation"):
        params["long_scale_pct"] = 0.00

    scan_list = pre_scan(UNIVERSE, regime)

    if len(scan_list) < 5:
        scan_list = UNIVERSE

    data5, data15 = load_data(scan_list)

    if not data5:
        return {"error": "no data", "market": market}

    # MARK TO MARKET
    equity = float(portfolio["cash"])

    for s, pos in list(portfolio["positions"].items()):
        px = float(data5[s][-1]) if s in data5 else latest_price(s)

        if px is None:
            continue

        pos["last_price"] = px
        side = pos.get("side", "long")

        if side == "short":
            pos["trough"] = min(float(pos.get("trough", px)), px)
            pos.setdefault("margin", float(pos["entry"]) * float(pos["shares"]))
        else:
            pos["peak"] = max(float(pos.get("peak", px)), px)

        equity += position_value(pos, px)

    portfolio["equity"] = equity
    portfolio["peak"] = max(float(portfolio.get("peak", equity)), equity)
    risk_controls = update_daily_risk_controls(equity)
    prune_cooldowns()

    if risk_controls.get("halted", False) and portfolio.get("positions"):
        halted_exits.extend(liquidate_all_positions(risk_controls.get("halt_reason", "risk halt"), market, data5))
        equity = refresh_equity_from_positions()
        risk_controls = update_daily_risk_controls(equity)

    # SCALE WINNERS
    if not risk_controls.get("halted", False):
        for s, pos in list(portfolio["positions"].items()):
            px = float(pos.get("last_price", pos["entry"]))
            side = pos.get("side", "long")
            pnl = position_pnl_pct(pos, px)

            if side == "short":
                trend_ok = px <= float(pos.get("trough", px)) * 1.015
                alloc_pct = params["short_scale_pct"]
            else:
                trend_ok = px >= float(pos.get("peak", px)) * 0.985
                alloc_pct = params["long_scale_pct"]

            if alloc_pct > 0 and pnl > 0.0035 and trend_ok and pos.get("adds", 0) < 3:
                alloc = float(portfolio["cash"]) * alloc_pct

                if alloc <= 0:
                    continue

                new_shares = alloc / px
                old_shares = float(pos["shares"])
                total_shares = old_shares + new_shares
                old_entry = float(pos["entry"])

                pos["entry"] = ((old_entry * old_shares) + (px * new_shares)) / total_shares
                pos["shares"] = total_shares
                pos["adds"] = pos.get("adds", 0) + 1
                portfolio["cash"] -= alloc

                if side == "short":
                    pos["margin"] = float(pos.get("margin", 0)) + alloc

                record_trade("scale", s, side, px, new_shares, {
                    "alloc": round(float(alloc), 2),
                    "market_mode": market["market_mode"]
                })

    # EXITS
    for s in list(portfolio["positions"].keys()):
        pos = portfolio["positions"][s]
        px = float(pos.get("last_price", pos["entry"]))
        side = pos.get("side", "long")
        pnl = position_pnl_pct(pos, px)
        shares = float(pos["shares"])

        if side == "short":
            trailing_stop = px > float(pos.get("trough", px)) * params["trail_short"]
            should_exit = pnl < params["stop_loss"] or trailing_stop or pnl > 0.20
        else:
            trailing_stop = px < float(pos.get("peak", px)) * params["trail_long"]
            risk_exit = (
                market["market_mode"] in ["crash_warning", "risk_off"] and pnl < 0.005
            ) or (
                market["market_mode"] in ["defensive_rotation", "neutral"] and pnl < 0
            )
            should_exit = pnl < params["stop_loss"] or trailing_stop or pnl > 0.20 or risk_exit

        if should_exit:
            portfolio["cash"] += position_value(pos, px)
            record_trade("exit", s, side, px, shares, {
                "pnl_pct": round(float(pnl * 100), 2),
                "market_mode": market["market_mode"],
                "cooldown_seconds": COOLDOWN_SECONDS
            })
            set_cooldown(s)
            del portfolio["positions"][s]

    interim_equity = float(portfolio["cash"])
    for s, pos in portfolio["positions"].items():
        interim_equity += position_value(pos, float(pos.get("last_price", pos["entry"])))
    portfolio["equity"] = interim_equity
    risk_controls = update_daily_risk_controls(interim_equity)

    if risk_controls.get("halted", False) and portfolio.get("positions"):
        halted_exits.extend(liquidate_all_positions(risk_controls.get("halt_reason", "risk halt"), market, data5))
        interim_equity = refresh_equity_from_positions()
        risk_controls = update_daily_risk_controls(interim_equity)

    longs, shorts = generate_signals(data5, data15, regime)

    new_entries_allowed = not risk_controls.get("halted", False)

    # LONG ENTRIES
    if new_entries_allowed and params["allow_longs"]:
        for s, score in longs:
            if s in portfolio["positions"] or is_in_cooldown(s):
                continue
            if len(portfolio["positions"]) >= params["max_positions"]:
                break

            px = float(data5[s][-1])
            alloc = float(portfolio["cash"]) * params["long_alloc_pct"]

            if alloc <= 0:
                continue

            shares = alloc / px
            portfolio["cash"] -= alloc

            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares,
                "last_price": px,
                "peak": px,
                "adds": 0,
                "side": "long"
            }

            record_trade("entry", s, "long", px, shares, {
                "score": round(float(score), 6),
                "alloc": round(float(alloc), 2),
                "market_mode": market["market_mode"]
            })

    # SHORT ENTRIES
    if new_entries_allowed and params["allow_shorts"]:
        for s, score in shorts:
            if s in portfolio["positions"] or is_in_cooldown(s):
                continue
            if len(portfolio["positions"]) >= params["max_positions"]:
                break

            px = float(data5[s][-1])
            alloc = float(portfolio["cash"]) * params["short_alloc_pct"]

            if alloc <= 0:
                continue

            shares = alloc / px
            portfolio["cash"] -= alloc

            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares,
                "last_price": px,
                "trough": px,
                "margin": alloc,
                "adds": 0,
                "side": "short"
            }

            record_trade("entry", s, "short", px, shares, {
                "score": round(float(score), 6),
                "alloc": round(float(alloc), 2),
                "market_mode": market["market_mode"]
            })

    final_equity = float(portfolio["cash"])

    for s, pos in portfolio["positions"].items():
        px = float(pos.get("last_price", pos["entry"]))
        final_equity += position_value(pos, px)

    portfolio["equity"] = final_equity
    portfolio["peak"] = max(float(portfolio.get("peak", final_equity)), final_equity)
    portfolio["history"].append(portfolio["equity"])
    portfolio["history"] = portfolio["history"][-500:]
    portfolio["last_market"] = market
    risk_controls = update_daily_risk_controls(final_equity)

    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"], 2),
        "cash": round(portfolio["cash"], 2),
        "regime": regime,
        "market_mode": market["market_mode"],
        "risk_score": market["risk_score"],
        "trade_permission": market["trade_permission"],
        "positions": list(portfolio["positions"].keys()),
        "halted_exits": halted_exits,
        "signals_found": len(longs) + len(shorts),
        "long_signals": [s for s, _ in longs],
        "short_signals": [s for s, _ in shorts],
        "new_entries_allowed": new_entries_allowed,
        "risk_controls": risk_controls,
        "risk_parameters": params,
        "sector_leaders": market["sector_leaders"],
        "defensive_rotation": market.get("defensive_rotation", False),
        "broad_market_soft": market.get("broad_market_soft", False),
        "bear_confirmed": market.get("bear_confirmed", False)
    }

# ===== AUTO-RUNNER =====
def local_now():
    return datetime.datetime.now(MARKET_TZ)


def market_open_now():
    now = local_now()

    if now.weekday() >= 5:
        return False

    regular_open = now.replace(hour=8, minute=30, second=0, microsecond=0)
    regular_close = now.replace(hour=15, minute=0, second=0, microsecond=0)

    return regular_open <= now <= regular_close


def update_auto_runner_status(extra=None):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ar["enabled"] = AUTO_RUN_ENABLED
    ar["market_only"] = AUTO_RUN_MARKET_ONLY
    ar["interval_seconds"] = AUTO_RUN_INTERVAL_SECONDS
    ar["market_open_now"] = market_open_now()
    ar["thread_started"] = AUTO_THREAD_STARTED

    if extra:
        ar.update(extra)

    try:
        save_state(portfolio)
    except Exception:
        pass

    return ar


def run_engine_locked(source="manual"):
    if not RUN_LOCK.acquire(blocking=False):
        update_auto_runner_status({
            "last_skip_reason": "engine already running",
            "last_run_source": source
        })
        return {"error": "engine already running", "source": source}

    try:
        result = run_engine()
        now = local_now()
        update_auto_runner_status({
            "last_run_ts": int(time.time()),
            "last_run_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "last_run_source": source,
            "last_result": result,
            "last_error": None,
            "last_skip_reason": None
        })
        return result
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}"
        update_auto_runner_status({
            "last_error": err,
            "last_error_trace": traceback.format_exc()[-2000:],
            "last_run_source": source
        })
        return {"error": err, "source": source}
    finally:
        RUN_LOCK.release()


def auto_runner_loop():
    update_auto_runner_status({"last_skip_reason": "auto runner started"})

    while True:
        try:
            is_open = market_open_now()

            if not AUTO_RUN_ENABLED:
                update_auto_runner_status({"last_skip_reason": "AUTO_RUN_ENABLED is false"})
            elif AUTO_RUN_MARKET_ONLY and not is_open:
                update_auto_runner_status({"last_skip_reason": "market closed"})
            else:
                run_engine_locked(source="auto")
        except Exception as e:
            update_auto_runner_status({
                "last_error": f"auto loop error: {type(e).__name__}: {str(e)}",
                "last_error_trace": traceback.format_exc()[-2000:]
            })

        time.sleep(max(60, AUTO_RUN_INTERVAL_SECONDS))


def start_auto_runner_once():
    global AUTO_THREAD_STARTED

    if AUTO_THREAD_STARTED:
        return

    AUTO_THREAD_STARTED = True
    t = threading.Thread(target=auto_runner_loop, daemon=True)
    t.start()
    update_auto_runner_status({"thread_started": True})

# ===== ROUTES =====
@app.route("/")
@app.route("/paper")
@app.route("/paper/dashboard")
def dashboard():
    market = portfolio.get("last_market") or market_status()
    ar = update_auto_runner_status()
    history = portfolio.get("history", [])[-200:]

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
    .line { font-size: 26px; font-weight: 800; line-height: 1.45; margin: 8px 0; }
    .small { color: #cbd5e1; font-size: 15px; margin-top: 16px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 20px; }
    .card { background: #111c33; border: 1px solid #1e293b; border-radius: 12px; padding: 14px; }
    .label { color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .value { font-size: 20px; font-weight: 800; margin-top: 6px; }
    canvas { margin-top: 24px; background: #111827; border-radius: 10px; padding: 10px; }
    a { color: #38bdf8; }
  </style>
</head>
<body>
  <h1>📊 Scanner + Long/Short Paper System</h1>
  <div class="line">Market: {{ market.market_mode }} | Risk: {{ market.risk_score }} | Regime: {{ market.regime }} | Leaders: {{ leaders }}</div>
  <div class="line">Trading Halted: {{ halted }} | Daily DD: {{ daily_dd }}% | Intraday DD: {{ intraday_dd }}% | Cooldowns: {{ cooldowns }}</div>
  <div class="line">Auto Runner: {{ auto_on }} | Thread: {{ thread }} | Market Open: {{ market_open }} | Last Run: {{ last_run }} | Skip: {{ skip }} | Error: {{ error }}</div>
  <div class="line">Defensive Rotation: {{ defensive_rotation }} | Broad Soft: {{ broad_market_soft }} | Bear Confirmed: {{ bear_confirmed }}</div>

  <canvas id="equityChart" height="120"></canvas>

  <div class="grid">
    <div class="card"><div class="label">Equity</div><div class="value">${{ equity }}</div></div>
    <div class="card"><div class="label">Cash</div><div class="value">${{ cash }}</div></div>
    <div class="card"><div class="label">Positions</div><div class="value">{{ positions }}</div></div>
    <div class="card"><div class="label">Trade Permission</div><div class="value">{{ market.trade_permission }}</div></div>
  </div>

  <p class="small">
    JSON: <a href="/paper/status">/paper/status</a> · Run once: <a href="/paper/run">/paper/run</a>
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
    rc = portfolio.get("risk_controls", default_risk_controls())
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
        last_run=ar.get("last_run_local") or "never",
        skip=ar.get("last_skip_reason") or "none",
        error=ar.get("last_error") or "none",
        defensive_rotation=market.get("defensive_rotation", False),
        broad_market_soft=market.get("broad_market_soft", False),
        bear_confirmed=market.get("bear_confirmed", False),
        equity=round(float(portfolio.get("equity", 0)), 2),
        cash=round(float(portfolio.get("cash", 0)), 2),
        positions=", ".join(portfolio.get("positions", {}).keys()) or "none",
        history_json=json.dumps(history if history else [portfolio.get("equity", 10000.0)])
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "market_open_now": market_open_now(),
        "auto_runner_started": AUTO_THREAD_STARTED
    })


@app.route("/paper/status")
def status():
    update_auto_runner_status()
    return jsonify(portfolio)


@app.route("/paper/market")
def market():
    return jsonify(market_status(force=request.args.get("force") == "1"))


@app.route("/paper/run")
def run():
    if not key_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(run_engine_locked(source="manual"))


@app.route("/paper/reset")
def reset():
    if not key_ok():
        return jsonify({"error": "unauthorized"}), 401
    cash = float(request.args.get("cash", 10000.0))
    return jsonify(reset_state(cash))


start_auto_runner_once()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
