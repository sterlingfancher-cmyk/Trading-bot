import os, json
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"

# ===== UNIVERSE =====
UNIVERSE = [
    "NVDA", "AMD", "AVGO", "TSM", "MU", "ARM",
    "MSFT", "AMZN", "GOOGL", "META", "PLTR", "SNOW", "NET", "CRWD", "PANW",
    "SHOP", "ROKU", "COIN",
    "XOM", "CVX",
    "WDC", "STX", "GLW", "TER", "CIEN",
    "SPY", "QQQ"
]

# ===== STATE =====
def default_state():
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": []
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
    portfolio["trades"] = portfolio["trades"][-100:]

# ===== SCANNER =====
def pre_scan(symbols, regime):
    scored = []

    for s in symbols:
        try:
            df = yf.download(s, period="5d", interval="15m", progress=False)
            prices = price_series(df)

            if len(prices) < 20:
                continue

            r20 = (prices[-1] / prices[-20]) - 1

            # In bear regimes, include downside momentum candidates for shorts.
            # In bull/neutral regimes, favor upside momentum candidates for longs.
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
        df = yf.download("SPY", period="5d", interval="15m", progress=False)
        prices = price_series(df)

        if len(prices) < 20:
            return "neutral"

        fast = np.mean(prices[-8:])
        slow = np.mean(prices[-20:])

        if prices[-1] < slow and fast < slow:
            return "bear"
        if prices[-1] > slow and fast > slow:
            return "bull"

        return "neutral"
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
            r3 = (px / p5[-3]) - 1
            r12 = (px / p5[-12]) - 1
            score = r3 * 0.6 + r12 * 0.4

            # LONG: price above short-term and 15m trend with breakout/momentum confirmation.
            if px > np.mean(p5[-20:]) and p15[-1] > np.mean(p15[-20:]):
                if px >= max(p5[-10:]) * 0.992 and r3 > 0 and score > 0.0025:
                    longs.append((s, float(score)))

            # SHORT: only in bear regime; downside trend and downside momentum.
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
    regime = get_regime()
    scan_list = pre_scan(UNIVERSE, regime)

    # Fallback if scanner is too strict or data is thin.
    if len(scan_list) < 5:
        scan_list = UNIVERSE

    data5, data15 = load_data(scan_list)

    if not data5:
        return {"error": "no data"}

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

    # SCALE WINNERS
    for s, pos in list(portfolio["positions"].items()):
        px = float(pos.get("last_price", pos["entry"]))
        side = pos.get("side", "long")
        pnl = position_pnl_pct(pos, px)

        if side == "short":
            trend_ok = px <= float(pos.get("trough", px)) * 1.015
            alloc_pct = 0.15
        else:
            trend_ok = px >= float(pos.get("peak", px)) * 0.985
            alloc_pct = 0.30

        if pnl > 0.0035 and trend_ok and pos.get("adds", 0) < 3:
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

            record_trade("scale", s, side, px, new_shares, {"alloc": round(float(alloc), 2)})

    # EXITS
    for s in list(portfolio["positions"].keys()):
        pos = portfolio["positions"][s]
        px = float(pos.get("last_price", pos["entry"]))
        side = pos.get("side", "long")
        pnl = position_pnl_pct(pos, px)
        shares = float(pos["shares"])

        if side == "short":
            trailing_stop = px > float(pos.get("trough", px)) * 1.03
            should_exit = pnl < -0.02 or trailing_stop or pnl > 0.20
        else:
            trailing_stop = px < float(pos.get("peak", px)) * 0.97
            should_exit = pnl < -0.02 or trailing_stop or pnl > 0.20

        if should_exit:
            portfolio["cash"] += position_value(pos, px)
            record_trade("exit", s, side, px, shares, {"pnl_pct": round(float(pnl * 100), 2)})
            del portfolio["positions"][s]

    # SIGNALS
    longs, shorts = generate_signals(data5, data15, regime)

    # LONG ENTRIES
    for s, score in longs:
        if s in portfolio["positions"]:
            continue
        if len(portfolio["positions"]) >= 4:
            break

        px = float(data5[s][-1])
        alloc = float(portfolio["cash"]) * 0.40

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

        record_trade("entry", s, "long", px, shares, {"score": round(float(score), 6), "alloc": round(float(alloc), 2)})

    # SHORT ENTRIES
    for s, score in shorts:
        if s in portfolio["positions"]:
            continue
        if len(portfolio["positions"]) >= 5:
            break

        px = float(data5[s][-1])
        alloc = float(portfolio["cash"]) * 0.20

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

        record_trade("entry", s, "short", px, shares, {"score": round(float(score), 6), "alloc": round(float(alloc), 2)})

    # FINAL EQUITY SNAPSHOT
    final_equity = float(portfolio["cash"])

    for s, pos in portfolio["positions"].items():
        px = float(pos.get("last_price", pos["entry"]))
        final_equity += position_value(pos, px)

    portfolio["equity"] = final_equity
    portfolio["peak"] = max(float(portfolio.get("peak", final_equity)), final_equity)
    portfolio["history"].append(portfolio["equity"])
    portfolio["history"] = portfolio["history"][-500:]

    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"], 2),
        "cash": round(portfolio["cash"], 2),
        "regime": regime,
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(longs) + len(shorts),
        "long_signals": [s for s, _ in longs],
        "short_signals": [s for s, _ in shorts]
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

    <canvas id="chart" style="max-height:420px;"></canvas>
    <pre id="data" style="background:#020617;padding:15px;border-radius:8px;overflow:auto;"></pre>

    <script>
    let chart;

    async function load(){
        const res = await fetch('/paper/status');
        const d = await res.json();

        document.getElementById('data').innerText = JSON.stringify(d,null,2);

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
