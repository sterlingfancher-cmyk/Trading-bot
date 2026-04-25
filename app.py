import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
import random

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True

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
    "regime": "neutral",
    "last_update": None
}

# ================= SAFE DATA LOADER =================
def load_data(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty or len(df) < 25:
                continue

            closes = df["Close"].dropna().values.astype(float)
            lows = df["Low"].dropna().values.astype(float)

            if len(closes) < 20:
                continue

            # Simulation noise
            if SIMULATION_MODE:
                noise = np.random.normal(0, 0.002, size=len(closes))
                closes = closes * (1 + noise)

            data[s] = {"close": closes, "low": lows}

        except Exception as e:
            print(f"[DATA ERROR] {s}: {e}")
            continue

    return data

# ================= SIGNAL ENGINE =================
def generate_signals(data):
    ranked = []

    for s, d in data.items():
        try:
            p = np.array(d["close"])

            if len(p) < 20:
                continue

            ret = (p[-1] / p[-5]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = float(ret + breakout + random.uniform(0, 0.01))
            ranked.append((s, score, vol))

        except Exception as e:
            print(f"[SIGNAL ERROR] {s}: {e}")
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if not spy:
        return "neutral"

    p = spy["close"]

    if len(p) < 20:
        return "neutral"

    if p[-1] > np.mean(p[-20:]):
        return "bull"
    elif p[-1] < np.mean(p[-20:]):
        return "bear"

    return "neutral"

# ================= ENGINE =================
def run_engine():
    global portfolio

    data = load_data(UNIVERSE + ["SPY"])

    if not data or len(data) < 5:
        return {"error": "No usable market data"}

    regime = detect_regime(data)
    portfolio["regime"] = regime

    signals = generate_signals(data)

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
    for s, score, vol in signals:
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
    portfolio["last_update"] = str(datetime.now())

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

<h2>🚀 AI Trading Dashboard</h2>

<div class="card"><canvas id="chart"></canvas></div>
<div class="card"><pre id="data"></pre></div>

<script>
async function refresh(){
 let res = await fetch('/paper/status');
 let d = await res.json();

 document.getElementById('data').innerText =
  JSON.stringify(d,null,2);

 let eq = d.history.length > 1 ? d.history : [10000,10000];

 new Chart(document.getElementById('chart'),{
  type:'line',
  data:{
    labels:eq.map((_,i)=>i),
    datasets:[{label:'Equity',data:eq}]
  }
 });
}

refresh();
setInterval(refresh,3000);
</script>

</body>
</html>
""")

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "SYSTEM LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
