import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string
import random

app = Flask(__name__)

# ================= CONFIG =================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

SIMULATION_MODE = True

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

MAX_POSITIONS = 4
BASE_RISK = 0.03
TRAIL_STOP = 0.015
SCALP_STEP = 0.004
PYRAMID_STEP = 0.003

# ================= STATE =================
portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "regime": "neutral"
}

# ================= DATA =================
def load(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty or len(df) < 20:
                continue

            closes = df["Close"].values.astype(float)

            # ===== SIMULATION BOOST =====
            if SIMULATION_MODE:
                noise = np.random.normal(0, 0.002, size=len(closes))
                closes = closes * (1 + noise)

            data[s] = {
                "close": closes,
                "low": df["Low"].values.astype(float)
            }

        except:
            continue

    return data

# ================= SIGNAL =================
def signals(data):
    scored = []

    for s, d in data.items():
        p = d["close"]

        if len(p) < 20:
            continue

        ret = (p[-1] / p[-5]) - 1
        breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
        vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

        score = float(ret + breakout + random.uniform(0, 0.01))  # boost activity
        scored.append((s, score, vol))

    return sorted(scored, key=lambda x: x[1], reverse=True)

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if not spy:
        return "neutral"

    p = spy["close"]

    if p[-1] > np.mean(p[-20:]):
        return "bull"
    elif p[-1] < np.mean(p[-20:]):
        return "bear"

    return "neutral"

# ================= ENGINE =================
def run_engine():
    global portfolio

    data = load(UNIVERSE + ["SPY"])

    if len(data) < 5:
        return {"error": "no data"}

    regime = detect_regime(data)
    portfolio["regime"] = regime

    sig = signals(data)

    # ===== EQUITY =====
    equity = portfolio["cash"]

    for s, pos in portfolio["positions"].items():
        if s in data:
            price = float(data[s]["close"][-1])
            equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # ===== TRAILING STOP =====
    for s, pos in list(portfolio["positions"].items()):
        if s not in data:
            continue

        price = float(data[s]["close"][-1])
        pos["peak"] = max(pos.get("peak", pos["entry"]), price)

        if (price - pos["peak"]) / pos["peak"] < -TRAIL_STOP:
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append((s, "stop"))
            del portfolio["positions"][s]

    # ===== SCALP =====
    for s, pos in list(portfolio["positions"].items()):
        if s not in data:
            continue

        price = float(data[s]["close"][-1])
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

        price = float(data[s]["close"][-1])
        risk = portfolio["equity"] * BASE_RISK
        size = risk / (vol * price + 1e-6)

        if portfolio["cash"] >= size:
            shares = size / price
            portfolio["cash"] -= size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price,
                "last_price": price,
                "peak": price
            }

    # ===== PYRAMID =====
    for s, pos in portfolio["positions"].items():
        if s not in data:
            continue

        price = float(data[s]["close"][-1])
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
        "equity": round(portfolio["equity"], 2),
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
.card {background:#1e293b;padding:15px;border-radius:10px;margin:10px}
</style>
</head>
<body>

<h2>🚀 AI Trading Dashboard (Simulation Mode)</h2>

<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><pre id="info"></pre></div>

<script>
async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());

 document.getElementById('info').innerText =
  JSON.stringify(p,null,2);

 let eq = p.history.length > 1 ? p.history : [10000,10000];

 new Chart(document.getElementById('eq'),{
  type:'line',
  data:{
    labels:eq.map((_,i)=>i),
    datasets:[{label:'Equity',data:eq}]
  }
 });
}

load();
setInterval(load,3000);
</script>

</body>
</html>
""")

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "SIMULATION SYSTEM LIVE"}

@app.route("/paper/run")
def run_api():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

# ================= START =================
if __name__ == "__main__":
    print("Starting server...")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
