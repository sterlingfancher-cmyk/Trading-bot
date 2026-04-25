import os, json, traceback
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

# ================= STATE =================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "errors": [],
        "regime": "neutral"
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

portfolio = load_state()

# ================= CLEAN =================
def clean(arr):
    arr = np.asarray(arr)
    if arr.ndim > 1:
        arr = arr[:, -1]
    arr = arr.astype(float)
    arr = arr[~np.isnan(arr)]
    return arr

# ================= DATA =================
def load_data(symbols):
    out = {}
    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)
            if df is None or df.empty:
                continue
            c = clean(df["Close"].values)
            if len(c) < 20:
                continue
            out[s] = c
        except:
            continue
    return out

# ================= SIMULATION =================
def simulate_price(last_price):
    shock = np.random.normal(0, 0.002)
    return float(last_price * (1 + shock))

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if spy is None or len(spy) < 20:
        return "neutral"

    ma = np.mean(spy[-20:])
    px = spy[-1]

    if px > ma * 1.002:
        return "bull"
    elif px < ma * 0.998:
        return "bear"
    return "neutral"

# ================= SIGNAL =================
def generate_signals(data):
    ranked = []

    for s, p in data.items():
        try:
            if len(p) < 20:
                continue

            r5 = (p[-1] / p[-5]) - 1
            r20 = (p[-1] / p[-20]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = r5*0.4 + r20*0.4 + breakout*0.2

            ranked.append((s, float(score), float(vol)))

        except:
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    try:
        data = load_data(UNIVERSE + ["SPY"])

        if not data:
            return {"error": "no data"}

        portfolio["regime"] = detect_regime(data)

        # ===== DETECT MARKET CLOSED =====
        market_closed = True
        for p in data.values():
            if len(p) > 1 and abs(p[-1] - p[-2]) > 1e-6:
                market_closed = False
                break

        # ===== MARK TO MARKET =====
        eq = portfolio["cash"]

        for s, pos in portfolio["positions"].items():

            if s in data:
                real_px = data[s][-1]
            else:
                real_px = pos["last_price"]

            px = simulate_price(pos["last_price"]) if market_closed else real_px

            pos["last_price"] = px
            pos["peak"] = max(pos.get("peak", px), px)

            eq += pos["shares"] * px

        portfolio["equity"] = eq
        portfolio["peak"] = max(portfolio["peak"], eq)

        # ===== RISK ENGINE =====
        dd = (portfolio["equity"] - portfolio["peak"]) / portfolio["peak"]

        if dd < -0.10:
            portfolio["positions"] = {}
            portfolio["cash"] = portfolio["equity"]
            portfolio["trades"].append({"type": "kill_switch"})
            return {"risk": "portfolio liquidated"}

        # ===== POSITION MANAGEMENT =====
        for s in list(portfolio["positions"].keys()):
            pos = portfolio["positions"][s]
            px = pos["last_price"]
            entry = pos["entry"]

            pnl = (px - entry) / entry

            if pnl < -0.05 or px < pos["peak"] * 0.95 or pnl > 0.12:
                portfolio["cash"] += px * pos["shares"]
                del portfolio["positions"][s]

        # ===== SIGNALS =====
        sig = generate_signals(data)

        max_positions = 5 if portfolio["regime"] == "bull" else 3

        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= max_positions:
                break

            px = data[s][-1]

            risk_adj = min(0.2, 0.05 / (vol + 1e-6))
            alloc = portfolio["equity"] * risk_adj

            if portfolio["cash"] < alloc:
                continue

            shares = alloc / px

            portfolio["cash"] -= alloc
            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares,
                "last_price": px,
                "peak": px
            }

            portfolio["trades"].append({
                "sym": s,
                "type": "entry",
                "px": px
            })

        portfolio["history"].append(portfolio["equity"])
        save_state(portfolio)

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig),
            "market_closed": market_closed
        }

    except Exception as e:
        portfolio["errors"].append(traceback.format_exc())
        return {"error": "engine failure", "detail": str(e)}

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "APP LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>🚀 AI Trading Dashboard (Final Stable)</h2>

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

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
