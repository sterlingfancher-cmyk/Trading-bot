import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
import traceback
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
    "errors": []
}

# ================= 🔥 SAFE SCALAR =================
def sf(x):
    try:
        if isinstance(x, (list, tuple, np.ndarray)):
            return float(np.asarray(x).flatten()[-1])
        return float(x)
    except:
        return 0.0

# ================= DATA =================
def synthetic_series(n=60, start=100):
    steps = np.random.normal(0, 0.002, n)
    prices = [start]
    for s in steps:
        prices.append(prices[-1] * (1 + s))
    return np.array(prices[1:])

def load_data(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty or len(df) < 25:
                closes = synthetic_series()
                lows = closes * 0.999
            else:
                closes = df["Close"].dropna().values
                lows = df["Low"].dropna().values

            if SIMULATION_MODE:
                closes = closes * (1 + np.random.normal(0, 0.002, len(closes)))

            data[s] = {
                "close": np.array(closes),
                "low": np.array(lows)
            }

        except Exception as e:
            portfolio["errors"].append(f"{s}:{e}")
            closes = synthetic_series()
            lows = closes * 0.999
            data[s] = {"close": closes, "low": lows}

    return data

# ================= SIGNAL =================
def generate_signals(data):
    ranked = []

    for s, d in data.items():
        try:
            p = d["close"]

            if len(p) < 20:
                continue

            ret = (sf(p[-1]) / sf(p[-5])) - 1
            breakout = (sf(p[-1]) - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = ret + breakout + random.uniform(0, 0.01)
            ranked.append((s, score, vol))

        except Exception as e:
            portfolio["errors"].append(f"signal {s}:{e}")

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    global portfolio

    try:
        data = load_data(UNIVERSE + ["SPY"])
        sig = generate_signals(data)

        equity = portfolio["cash"]

        # ===== UPDATE EQUITY =====
        for s, pos in portfolio["positions"].items():
            if s in data:
                price = sf(data[s]["close"][-1])
                equity += pos["shares"] * price

        portfolio["equity"] = equity
        portfolio["peak"] = max(portfolio["peak"], equity)

        # ===== STOP =====
        for s, pos in list(portfolio["positions"].items()):
            if s not in data:
                continue

            price = sf(data[s]["close"][-1])
            pos["peak"] = max(pos.get("peak", pos["entry"]), price)

            if (price - pos["peak"]) / pos["peak"] < -TRAIL_STOP:
                portfolio["cash"] += pos["shares"] * price
                del portfolio["positions"][s]

        # ===== ENTRY =====
        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= MAX_POSITIONS:
                break

            price = sf(data[s]["close"][-1])
            risk = portfolio["equity"] * BASE_RISK
            size = risk / (vol * price + 1e-6)

            if portfolio["cash"] >= size:
                shares = size / price
                portfolio["cash"] -= size

                portfolio["positions"][s] = {
                    "shares": shares,
                    "entry": price,
                    "peak": price
                }

        portfolio["history"].append(portfolio["equity"])

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig)
        }

    except Exception as e:
        return {
            "error": "engine failure",
            "detail": str(e),
            "trace": traceback.format_exc()
        }

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body style="background:#0f172a;color:white">

<h2>Trading Dashboard</h2>

<canvas id="c"></canvas>
<pre id="d"></pre>

<script>
async function r(){
 let p=await fetch('/paper/status').then(r=>r.json());
 document.getElementById('d').innerText=JSON.stringify(p,null,2);

 let eq=p.history.length>1?p.history:[10000,10000];

 new Chart(document.getElementById('c'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{data:eq}]}
 });
}
r();
setInterval(r,3000);
</script>
</body>
</html>
""")

# ================= ROUTES =================
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

@app.route("/logs")
def logs():
    return jsonify(portfolio["errors"][-10:])

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
