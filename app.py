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

SECTOR_MAP = {
    "NVDA":"semis","AMD":"semis","TSM":"semis","AVGO":"semis","ARM":"semis",
    "META":"tech","GOOGL":"tech","MSFT":"tech","AMZN":"tech",
    "SNOW":"cloud","CRWD":"cloud","PANW":"cloud","NET":"cloud","PLTR":"cloud",
    "TSLA":"auto","SHOP":"ecom","ROKU":"media",
    "COIN":"crypto","IBIT":"crypto","ETHA":"crypto","GDLC":"crypto",
    "XOM":"energy","CVX":"energy",
    "RKLB":"defense","KTOS":"defense","LHX":"defense","NOC":"defense"
}

MAX_POSITIONS = 4
STOP_LOSS = 0.02
PYRAMID_STEP = 0.001
SCALP_STEP = 0.005
TRAIL_STOP = 0.01

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
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

    latest_time = max(timestamps) if timestamps else None
    return data, latest_time

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if not spy:
        return "neutral"

    p = np.array(spy["close"], dtype=float)
    if len(p) < 50:
        return "neutral"

    ma20 = np.mean(p[-20:])
    ma50 = np.mean(p[-50:])

    if p[-1] > ma20 > ma50:
        return "bull"
    elif p[-1] < ma20 < ma50:
        return "bear"
    return "neutral"

# ================= SIGNALS =================
def signals(data):
    scored = []

    for s, d in data.items():
        try:
            p = np.array(d["close"], dtype=float)

            ret3 = (p[-1] / p[-3]) - 1
            ret10 = (p[-1] / p[-10]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])

            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = float(ret3 + ret10 + breakout)
            scored.append((s, score, vol))
        except:
            continue

    return sorted(scored, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    global portfolio

    data, timestamp = load(UNIVERSE + ["SPY"])

    # 🚨 EXECUTION GUARD
    if timestamp == portfolio["last_timestamp"]:
        return {
            "message": "No new market data",
            "equity": portfolio["equity"]
        }

    portfolio["last_timestamp"] = timestamp

    if len(data) < 5:
        return {"error": "DATA FAILURE"}

    portfolio["regime"] = detect_regime(data)
    sig = signals(data)

    # ===== EQUITY =====
    equity = portfolio["cash"]
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # ===== TRAILING STOP =====
    for s, pos in list(portfolio["positions"].items()):
        price = sf(data[s]["close"][-1])
        pos["peak"] = max(pos.get("peak", pos["entry"]), price)

        if (price - pos["peak"]) / pos["peak"] < -TRAIL_STOP:
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append((s, "trail_stop"))
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
    used = set()
    capital = portfolio["equity"] / MAX_POSITIONS

    for s, score, vol in sig:
        sector = SECTOR_MAP.get(s, "other")

        if s in portfolio["positions"] or sector in used:
            continue

        if len(portfolio["positions"]) >= MAX_POSITIONS:
            break

        price = sf(data[s]["close"][-1])
        size = capital / (1 + vol * 5)

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

            used.add(sector)

    # ===== PYRAMID =====
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        move = (price - pos["last_price"]) / pos["last_price"]

        if move > PYRAMID_STEP:
            size = (portfolio["equity"] / MAX_POSITIONS) * 0.3

            if portfolio["cash"] >= size:
                shares = size / price
                portfolio["cash"] -= size

                pos["shares"] += shares
                pos["last_price"] = price
                pos["adds"] += 1
                portfolio["trades"].append((s, "pyramid"))

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    return {
        "equity": round(portfolio["equity"],2),
        "positions": list(portfolio["positions"].keys()),
        "trades": portfolio["trades"][-5:],
        "regime": portfolio["regime"]
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

<h2>📊 Live Trading Dashboard (1m Engine)</h2>

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
    return {"status":"1M ENGINE LIVE"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
