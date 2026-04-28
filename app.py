import os, json
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"

# ===== EXPANDED UNIVERSE =====
UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","ARM",
    "MSFT","AMZN","GOOGL","META","PLTR","SNOW","NET","CRWD","PANW",
    "SHOP","ROKU","COIN",
    "XOM","CVX",
    "WDC","STX","GLW","TER","CIEN",
    "SPY","QQQ"
]

# ===== STATE =====
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass

    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": []
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

portfolio = load_state()

# ===== HELPERS =====
def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]

# ===== SCANNER =====
def pre_scan(symbols):
    scored = []

    for s in symbols:
        try:
            df = yf.download(s, period="5d", interval="15m", progress=False)
            if df.empty:
                continue

            prices = clean(df["Close"].values)
            if len(prices) < 20:
                continue

            r = (prices[-1] / prices[-20]) - 1

            if r > 0.01:
                scored.append((s, r))

        except:
            continue

    return [s for s,_ in sorted(scored, key=lambda x: x[1], reverse=True)[:20]]

# ===== DATA =====
def load_data(symbols):
    data5, data15 = {}, {}

    for s in symbols:
        try:
            df5 = yf.download(s, period="2d", interval="5m", progress=False)
            df15 = yf.download(s, period="5d", interval="15m", progress=False)

            if df5.empty or df15.empty:
                continue

            c5 = clean(df5["Close"].values)
            c15 = clean(df15["Close"].values)

            if len(c5) > 20 and len(c15) > 20:
                data5[s] = c5
                data15[s] = c15
        except:
            continue

    return data5, data15

# ===== REGIME =====
def get_regime():
    try:
        df = yf.download("SPY", period="5d", interval="15m", progress=False)
        prices = clean(df["Close"].values)

        if prices[-1] < np.mean(prices[-20:]):
            return "bear"
        else:
            return "bull"
    except:
        return "neutral"

# ===== SIGNALS =====
def generate_signals(data5, data15, regime):
    longs, shorts = [], []

    for s in data5:
        try:
            p5 = data5[s]
            p15 = data15[s]
            px = p5[-1]

            r3 = (px / p5[-3]) - 1
            r12 = (px / p5[-12]) - 1

            score = r3*0.6 + r12*0.4

            # ===== LONG =====
            if px > np.mean(p5[-20:]) and p15[-1] > np.mean(p15[-20:]):
                if px >= max(p5[-10:]) * 0.995 and r3 > 0 and score > 0.0025:
                    longs.append((s, score))

            # ===== SHORT =====
            if regime == "bear":
                if px < np.mean(p5[-20:]) and p15[-1] < np.mean(p15[-20:]):
                    if px <= min(p5[-10:]) * 1.005 and r3 < 0:
                        shorts.append((s, abs(score)))

        except:
            continue

    longs = sorted(longs, key=lambda x: x[1], reverse=True)[:5]
    shorts = sorted(shorts, key=lambda x: x[1], reverse=True)[:3]

    return longs, shorts

# ===== ENGINE =====
def run_engine():
    regime = get_regime()

    scan_list = pre_scan(UNIVERSE)
    data5, data15 = load_data(scan_list)

    if not data5:
        return {"error": "no data"}

    equity = portfolio["cash"]

    # MARK TO MARKET
    for s, pos in portfolio["positions"].items():
        if s not in data5:
            continue

        px = float(data5[s][-1])
        pos["last_price"] = px
        pos["peak"] = max(pos["peak"], px)

        equity += pos["shares"] * px

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # SCALE (SMART)
    for s, pos in portfolio["positions"].items():
        pnl = (pos["last_price"] - pos["entry"]) / pos["entry"]

        pullback_ok = pos["last_price"] >= pos["peak"] * 0.985

        if pnl > 0.0035 and pullback_ok and pos.get("adds", 0) < 3:
            alloc = portfolio["cash"] * 0.3

            if alloc > 0:
                shares = alloc / pos["last_price"]
                portfolio["cash"] -= alloc
                pos["shares"] += shares
                pos["adds"] = pos.get("adds", 0) + 1

    # EXITS
    for s in list(portfolio["positions"].keys()):
        pos = portfolio["positions"][s]
        px = pos["last_price"]

        pnl = (px - pos["entry"]) / pos["entry"]

        if pnl < -0.02 or px < pos["peak"] * 0.97 or pnl > 0.20:
            portfolio["cash"] += px * pos["shares"]
            del portfolio["positions"][s]

    # SIGNALS
    longs, shorts = generate_signals(data5, data15, regime)

    # ENTRIES
    for s, score in longs:
        if s in portfolio["positions"]:
            continue

        if len(portfolio["positions"]) >= 4:
            break

        px = data5[s][-1]

        alloc = portfolio["cash"] * 0.4
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

    # SHORTS (HALF SIZE)
    for s, score in shorts:
        if s in portfolio["positions"]:
            continue

        if len(portfolio["positions"]) >= 5:
            break

        px = data5[s][-1]

        alloc = portfolio["cash"] * 0.2
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
            "side": "short"
        }

    portfolio["history"].append(portfolio["equity"])
    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"],2),
        "cash": round(portfolio["cash"],2),
        "regime": regime,
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(longs) + len(shorts)
    }

# ===== ROUTES =====
@app.route("/")
def home():
    return {"status":"LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>📊 Hedge System (Long/Short + Scanner)</h2>

    <canvas id="chart"></canvas>
    <pre id="data"></pre>

    <script>
    let chart;

    async function load(){
        const res = await fetch('/paper/status');
        const d = await res.json();

        document.getElementById('data').innerText = JSON.stringify(d,null,2);

        let hist = d.history.length > 1 ? d.history : [10000,10000];

        if(!chart){
            chart = new Chart(document.getElementById('chart'),{
                type:'line',
                data:{
                    labels: hist.map((_,i)=>i),
                    datasets:[{label:'Equity', data:hist}]
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
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port)
