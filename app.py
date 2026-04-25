import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

# ================= CONFIG =================
UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

MAX_POSITIONS = 4
BASE_RISK = 0.02
TRAIL_STOP = 0.01
SCALP_STEP = 0.005
PYRAMID_STEP = 0.001

SIMULATION_MODE = False

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_timestamp": None,
    "regime": "neutral"
}

def sf(x):
    return float(np.asarray(x).item())

# ================= DATA =================
def load(symbols):
    data = {}
    timestamps = []

    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty or len(df) < 30:
                continue

            data[s] = {
                "close": df["Close"].values,
                "low": df["Low"].values
            }

            timestamps.append(df.index[-1])

        except:
            continue

    return data, max(timestamps) if timestamps else None

# ================= SIGNAL =================
def signals(data):
    scored = []

    for s, d in data.items():
        try:
            p = np.array(d["close"])

            ret = (p[-1] / p[-5]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = float(ret + breakout)
            scored.append((s, score, vol))
        except:
            continue

    return sorted(scored, key=lambda x: x[1], reverse=True)

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if not spy:
        return "neutral"

    p = np.array(spy["close"])

    if len(p) < 50:
        return "neutral"

    if p[-1] > np.mean(p[-20:]):
        return "bull"
    elif p[-1] < np.mean(p[-20:]):
        return "bear"

    return "neutral"

# ================= ENGINE =================
def run_engine():
    global portfolio

    if datetime.utcnow().weekday() >= 5:
        return {"status": "Market Closed"}

    data, timestamp = load(UNIVERSE + ["SPY"])

    if timestamp == portfolio["last_timestamp"]:
        return {"message": "No new data", "equity": portfolio["equity"]}

    portfolio["last_timestamp"] = timestamp

    if len(data) < 5:
        return {"error": "DATA FAIL"}

    regime = detect_regime(data)
    portfolio["regime"] = regime

    sig = signals(data)

    # ===== EQUITY =====
    equity = portfolio["cash"]
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        if SIMULATION_MODE:
            price *= (1 + np.random.uniform(-0.001, 0.001))
        equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # ===== DRAWDOWN STOP =====
    dd = (equity - portfolio["peak"]) / portfolio["peak"]
    if dd < -0.05:
        return {"status": "PAUSED - DRAWDOWN"}

    # ===== TRAILING STOP =====
    for s, pos in list(portfolio["positions"].items()):
        price = sf(data[s]["close"][-1])

        pos["peak"] = max(pos.get("peak", pos["entry"]), price)

        if (price - pos["peak"]) / pos["peak"] < -TRAIL_STOP:
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append((s, "exit"))
            del portfolio["positions"][s]

    # ===== SCALP =====
    for s, pos in list(portfolio["positions"].items()):
        price = sf(data[s]["close"][-1])
        move = (price - pos["last_price"]) / pos["last_price"]

        if move > SCALP_STEP:
            sell = pos["shares"] * 0.3
            portfolio["cash"] += sell * price
            pos["shares"] -= sell
            pos["last_price"] = price
            portfolio["trades"].append((s, "scalp"))

    # ===== ENTRY =====
    for s, score, vol in sig:
        if s in portfolio["positions"]:
            continue

        if len(portfolio["positions"]) >= MAX_POSITIONS:
            break

        if regime == "bear" and score > 0:
            continue

        price = sf(data[s]["close"][-1])
        risk = portfolio["equity"] * BASE_RISK
        size = risk / (vol * price + 1e-6)

        if portfolio["cash"] >= size:
            shares = size / price
            portfolio["cash"] -= size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price,
                "last_price": price,
                "peak": price,
                "adds": 0
            }

    # ===== PYRAMID =====
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        move = (price - pos["last_price"]) / pos["last_price"]

        if move > PYRAMID_STEP:
            size = portfolio["equity"] * 0.01

            if portfolio["cash"] >= size:
                shares = size / price
                portfolio["cash"] -= size

                pos["shares"] += shares
                pos["last_price"] = price
                portfolio["trades"].append((s, "pyramid"))

    portfolio["history"].append(portfolio["equity"])

    return {
        "equity": round(portfolio["equity"],2),
        "positions": list(portfolio["positions"].keys()),
        "trades": portfolio["trades"][-5:],
        "regime": regime
    }

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {background:#0f172a;color:white;font-family:Arial}
.grid {display:grid;grid-template-columns:1fr 1fr;gap:15px}
.card {background:#1e293b;padding:15px;border-radius:10px}
</style>
</head>
<body>

<h2>📊 Institutional Trading Dashboard</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><pre id="positions"></pre></div>
<div class="card"><pre id="regime"></pre></div>
<div class="card"><pre id="trades"></pre></div>
</div>

<script>
async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());

 document.getElementById('positions').innerText =
  JSON.stringify(p.positions,null,2);

 document.getElementById('regime').innerText =
  "Regime: " + p.regime;

 document.getElementById('trades').innerText =
  JSON.stringify(p.trades,null,2);

 let eq = p.history.length>1 ? p.history : [10000,10000];

 new Chart(document.getElementById('eq'),{
  type:'line',
  data:{
    labels:eq.map((_,i)=>i),
    datasets:[{label:'Equity',data:eq}]
  }
 });
}

load();
setInterval(load,5000);
</script>

</body>
</html>
""")

# ================= ROUTES =================
@app.route("/paper/run")
def run_api():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/")
def home():
    return {"status":"FINAL SYSTEM WITH DASHBOARD LIVE"}
