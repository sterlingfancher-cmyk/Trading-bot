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
RANDOM_SEED = 42

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

np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

# ================= STATE =================
portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "regime": "neutral",
    "last_update": None,
    "errors": []
}

# ================= SAFE DATA =================
def synthetic_series(n=60, start=100.0):
    # fallback if data provider fails
    steps = np.random.normal(0, 0.002, size=n)
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
                # Fallback synthetic
                closes = synthetic_series()
                lows = closes * (1 - np.abs(np.random.normal(0, 0.001, size=len(closes))))
                data[s] = {"close": closes.astype(float), "low": lows.astype(float)}
                continue

            closes = df["Close"].dropna().values.astype(float)
            lows = df["Low"].dropna().values.astype(float)

            if len(closes) < 20:
                closes = synthetic_series()
                lows = closes * (1 - np.abs(np.random.normal(0, 0.001, size=len(closes))))

            # simulation noise to ensure movement off-hours
            if SIMULATION_MODE:
                noise = np.random.normal(0, 0.002, size=len(closes))
                closes = closes * (1 + noise)

            data[s] = {"close": closes, "low": lows}

        except Exception as e:
            portfolio["errors"].append(f"[DATA ERROR] {s}: {e}")
            # Always fallback to synthetic to avoid crashes
            closes = synthetic_series()
            lows = closes * (1 - np.abs(np.random.normal(0, 0.001, size=len(closes))))
            data[s] = {"close": closes.astype(float), "low": lows.astype(float)}

    return data

# ================= SIGNALS =================
def generate_signals(data):
    ranked = []
    for s, d in data.items():
        try:
            p = np.array(d["close"], dtype=float)
            if len(p) < 20:
                continue

            ret = (p[-1] / p[-5]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = float(ret + breakout + random.uniform(0, 0.01))
            ranked.append((s, score, vol))
        except Exception as e:
            portfolio["errors"].append(f"[SIGNAL ERROR] {s}: {e}")
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= REGIME =================
def detect_regime(data):
    try:
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
    except:
        return "neutral"

# ================= ENGINE =================
def run_engine():
    global portfolio
    try:
        data = load_data(UNIVERSE + ["SPY"])
        if not data or len(data) < 5:
            return {"error": "No usable market data"}

        regime = detect_regime(data)
        portfolio["regime"] = regime

        sig = generate_signals(data)

        # ===== EQUITY =====
        equity = portfolio["cash"]
        for s, pos in portfolio["positions"].items():
            if s in data:
                price = float(data[s]["close"][-1])
                equity += pos["shares"] * price

        portfolio["equity"] = float(equity)
        portfolio["peak"] = max(portfolio["peak"], portfolio["equity"])

        # ===== TRAILING STOP =====
        for s, pos in list(portfolio["positions"].items()):
            if s not in data:
                continue
            price = float(data[s]["close"][-1])
            pos["peak"] = max(pos.get("peak", pos["entry"]), price)
            if (price - pos["peak"]) / pos["peak"] < -TRAIL_STOP:
                portfolio["cash"] += pos["shares"] * price
                portfolio["trades"].append({"sym": s, "type": "stop", "px": price})
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
                portfolio["trades"].append({"sym": s, "type": "scalp", "px": price})

        # ===== ENTRY =====
        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue
            if len(portfolio["positions"]) >= MAX_POSITIONS:
                break

            price = float(data[s]["close"][-1])
            risk = portfolio["equity"] * BASE_RISK
            size = risk / (vol * price + 1e-6)

            if portfolio["cash"] >= size and size > 0:
                shares = size / price
                portfolio["cash"] -= size
                portfolio["positions"][s] = {
                    "shares": float(shares),
                    "entry": float(price),
                    "last_price": float(price),
                    "peak": float(price)
                }
                portfolio["trades"].append({"sym": s, "type": "entry", "px": price})

        # ===== PYRAMID =====
        for s, pos in portfolio["positions"].items():
            if s not in data:
                continue
            price = float(data[s]["close"][-1])
            move = (price - pos["last_price"]) / pos["last_price"]
            if move > PYRAMID_STEP:
                size = portfolio["equity"] * 0.01
                if portfolio["cash"] >= size and size > 0:
                    shares = size / price
                    portfolio["cash"] -= size
                    pos["shares"] += shares
                    pos["last_price"] = price
                    portfolio["trades"].append({"sym": s, "type": "pyramid", "px": price})

        portfolio["history"].append(float(portfolio["equity"]))
        portfolio["last_update"] = str(datetime.utcnow())

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "trades": portfolio["trades"][-5:],
            "regime": portfolio["regime"]
        }

    except Exception as e:
        err = f"[ENGINE ERROR] {e}\n{traceback.format_exc()}"
        portfolio["errors"].append(err)
        return {"error": "engine failure", "detail": str(e)}

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

<h2>📊 AI Trading Dashboard</h2>

<div class="card"><canvas id="chart"></canvas></div>
<div class="card"><pre id="data"></pre></div>

<script>
let chart;
async function refresh(){
  const res = await fetch('/paper/status');
  const d = await res.json();
  document.getElementById('data').innerText = JSON.stringify(d,null,2);

  const eq = d.history.length > 1 ? d.history : [10000,10000];
  const ctx = document.getElementById('chart');

  if (!chart){
    chart = new Chart(ctx,{
      type:'line',
      data:{ labels:eq.map((_,i)=>i), datasets:[{label:'Equity',data:eq}]},
      options:{animation:false}
    });
  } else {
    chart.data.labels = eq.map((_,i)=>i);
    chart.data.datasets[0].data = eq;
    chart.update();
  }
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

@app.route("/health")
def health():
    return {"ok": True, "time": str(datetime.utcnow())}

@app.route("/paper/run")
def run():
    try:
        if request.args.get("key") != SECRET_KEY:
            return {"error": "unauthorized"}
        return jsonify(run_engine())
    except Exception as e:
        return {"error": "route failure", "detail": str(e)}

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/logs")
def logs():
    return jsonify(portfolio["errors"][-20:])

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
