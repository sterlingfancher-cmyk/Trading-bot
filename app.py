import os, json, time
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"
MARKET_CACHE_TTL = 300

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
def default_state():
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "last_market": {}
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

    return state


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


portfolio = load_state()

# ===== HELPERS =====
def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]


def price_series(df, column="Close"):
    if df is None or df.empty or column not in df:
        return np.array([])
    return clean(df[column].values)


def latest_price(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="5m", progress=False)
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

# ===== MARKET / ECONOMIC RISK ENGINE =====
def market_status(force=False):
    now = time.time()
    if not force and _market_cache["data"] and now - _market_cache["ts"] < MARKET_CACHE_TTL:
        return _market_cache["data"]

    series = {}

    for symbol in MACRO_SYMBOLS:
        try:
            df = yf.download(symbol, period="30d", interval="1d", progress=False)
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
        "growth_leadership": growth_leadership
    }

    _market_cache["ts"] = now
    _market_cache["data"] = result
    portfolio["last_market"] = result

    return result


def risk_parameters(market):
    mode = market.get("market_mode", "neutral")

    if mode == "risk_on":
        return {
            "max_positions": 5,
            "long_alloc_pct": 0.42,
            "short_alloc_pct": 0.12,
            "long_scale_pct": 0.30,
            "short_scale_pct": 0.12,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.02,
            "trail_long": 0.97,
            "trail_short": 1.03
        }

    if mode == "constructive":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.35,
            "short_alloc_pct": 0.15,
            "long_scale_pct": 0.25,
            "short_scale_pct": 0.12,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.02,
            "trail_long": 0.97,
            "trail_short": 1.03
        }

    if mode == "neutral":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.25,
            "short_alloc_pct": 0.15,
            "long_scale_pct": 0.15,
            "short_scale_pct": 0.10,
            "allow_longs": True,
            "allow_shorts": True,
            "stop_loss": -0.018,
            "trail_long": 0.975,
            "trail_short": 1.025
        }

    if mode == "risk_off":
        return {
            "max_positions": 3,
            "long_alloc_pct": 0.15,
            "short_alloc_pct": 0.22,
            "long_scale_pct": 0.00,
            "short_scale_pct": 0.12,
            "allow_longs": False,
            "allow_shorts": True,
            "stop_loss": -0.015,
            "trail_long": 0.98,
            "trail_short": 1.025
        }

    return {
        "max_positions": 2,
        "long_alloc_pct": 0.00,
        "short_alloc_pct": 0.18,
        "long_scale_pct": 0.00,
        "short_scale_pct": 0.00,
        "allow_longs": False,
        "allow_shorts": True,
        "stop_loss": -0.012,
        "trail_long": 0.985,
        "trail_short": 1.02
    }

# ===== SCANNER =====
def pre_scan(symbols, regime):
    scored = []

    for s in symbols:
        try:
            df = yf.download(s, period="5d", interval="15m", progress=False)
            prices = price_series(df)

            if len(prices) < 20:
                continue

            r20 = pct_change(prices, 20)

            if regime == "bear":
                if r20 < -0.003:
                    scored.append((s, abs(r20)))
                elif r20 > 0.006:
                    scored.append((s, r20 * 0.5))
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
            df5 = yf.download(s, period="2d", interval="5m", progress=False)
            df15 = yf.download(s, period="5d", interval="15m", progress=False)

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

            if px > np.mean(p5[-20:]) and p15[-1] > np.mean(p15[-20:]):
                if px >= max(p5[-10:]) * 0.992 and r3 > 0 and score > 0.0025:
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

# ===== ENGINE =====
def run_engine():
    market = market_status(force=True)
    params = risk_parameters(market)
    regime = market.get("regime", "neutral")
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

    # SCALE WINNERS, but disable or reduce scaling when the market engine says to de-risk.
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

            record_trade("scale", s, side, px, new_shares, {"alloc": round(float(alloc), 2), "market_mode": market["market_mode"]})

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
            risk_exit = market["market_mode"] == "crash_warning" and pnl < 0.005
            should_exit = pnl < params["stop_loss"] or trailing_stop or pnl > 0.20 or risk_exit

        if should_exit:
            portfolio["cash"] += position_value(pos, px)
            record_trade("exit", s, side, px, shares, {"pnl_pct": round(float(pnl * 100), 2), "market_mode": market["market_mode"]})
            del portfolio["positions"][s]

    # SIGNALS
    longs, shorts = generate_signals(data5, data15, regime)

    # LONG ENTRIES
    if params["allow_longs"]:
        for s, score in longs:
            if s in portfolio["positions"]:
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

            record_trade("entry", s, "long", px, shares, {"score": round(float(score), 6), "alloc": round(float(alloc), 2), "market_mode": market["market_mode"]})

    # SHORT ENTRIES
    if params["allow_shorts"]:
        for s, score in shorts:
            if s in portfolio["positions"]:
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

            record_trade("entry", s, "short", px, shares, {"score": round(float(score), 6), "alloc": round(float(alloc), 2), "market_mode": market["market_mode"]})

    # FINAL EQUITY SNAPSHOT
    final_equity = float(portfolio["cash"])

    for s, pos in portfolio["positions"].items():
        px = float(pos.get("last_price", pos["entry"]))
        final_equity += position_value(pos, px)

    portfolio["equity"] = final_equity
    portfolio["peak"] = max(float(portfolio.get("peak", final_equity)), final_equity)
    portfolio["history"].append(portfolio["equity"])
    portfolio["history"] = portfolio["history"][-500:]
    portfolio["last_market"] = market

    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"], 2),
        "cash": round(portfolio["cash"], 2),
        "regime": regime,
        "market_mode": market["market_mode"],
        "risk_score": market["risk_score"],
        "trade_permission": market["trade_permission"],
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(longs) + len(shorts),
        "long_signals": [s for s, _ in longs],
        "short_signals": [s for s, _ in shorts],
        "risk_parameters": params,
        "sector_leaders": market["sector_leaders"]
    }

# ===== ROUTES =====
@app.route("/")
def home():
    return {"status": "LIVE"}


@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())


@app.route("/paper/status")
def status():
    return jsonify(portfolio)


@app.route("/market/status")
def market_route():
    force = request.args.get("force") == "1"
    return jsonify(market_status(force=force))


@app.route("/risk/params")
def risk_route():
    m = market_status(force=request.args.get("force") == "1")
    return jsonify({"market": m, "params": risk_parameters(m)})

# ===== DASHBOARD =====
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
    <title>Trading Bot Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;font-family:Arial;padding:20px;">
    <h2>📊 Scanner + Long/Short Paper System</h2>
    <h3 id="market"></h3>

    <canvas id="chart" style="max-height:420px;"></canvas>
    <pre id="data" style="background:#020617;padding:15px;border-radius:8px;overflow:auto;"></pre>

    <script>
    let chart;

    async function load(){
        const statusRes = await fetch('/paper/status');
        const d = await statusRes.json();

        document.getElementById('data').innerText = JSON.stringify(d,null,2);

        const m = d.last_market || {};
        document.getElementById('market').innerText =
            `Market: ${m.market_mode || 'unknown'} | Risk: ${m.risk_score ?? 'n/a'} | Regime: ${m.regime || 'n/a'} | Leaders: ${(m.sector_leaders || []).join(', ')}`;

        let hist = d.history && d.history.length > 1 ? d.history : [10000,10000];

        if(!chart){
            chart = new Chart(document.getElementById('chart'),{
                type:'line',
                data:{
                    labels: hist.map((_,i)=>i),
                    datasets:[{label:'Equity', data:hist}]
                },
                options:{
                    responsive:true,
                    plugins:{legend:{labels:{color:'white'}}},
                    scales:{
                        x:{ticks:{color:'white'}},
                        y:{ticks:{color:'white'}}
                    }
                }
            });
        } else {
            chart.data.labels = hist.map((_,i)=>i);
            chart.data.datasets[0].data = hist;
            chart.update();
        }
    }

    load();
    setInterval(load,3000);
    </script>
    </body>
    </html>
    """)

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
