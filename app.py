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
    "NVDA":"semis","AMD":"semis","TSM":"semis","AVGO":"semis","ARM":"semis","MU":"semis","LRCX":"semis",
    "META":"tech","GOOGL":"tech","MSFT":"tech","AMZN":"tech",
    "SNOW":"cloud","CRWD":"cloud","PANW":"cloud","NET":"cloud","PLTR":"cloud",
    "TSLA":"auto","SHOP":"ecom","ROKU":"media",
    "COIN":"crypto","IBIT":"crypto","ETHA":"crypto","GDLC":"crypto",
    "XOM":"energy","CVX":"energy",
    "RKLB":"defense","KTOS":"defense","LHX":"defense","NOC":"defense"
}

MAX_POSITIONS = 4
STOP_LOSS = 0.02          # 🔥 tighter
PYRAMID_THRESHOLD = 0.0015  # 🔥 intraday tuned
PYRAMID_LIMIT = 2

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "symbols_loaded": [],
    "ai_notes": [],
    "regime": "neutral"
}

def sf(x):
    return float(np.asarray(x).item())

# ================= DATA =================
def load(symbols):
    data = {}
    for s in symbols:
        try:
            df = yf.download(s, period="5d", interval="5m", progress=False)
            if df is None or df.empty or len(df) < 50:
                continue

            data[s] = {
                "close": df["Close"].values,
                "low": df["Low"].values
            }
        except:
            continue
    return data

# ================= REGIME ENGINE =================
def detect_regime(data):
    spy = data.get("SPY")
    if not spy:
        return "neutral"

    p = np.array(spy["close"], dtype=float)

    ma20 = np.mean(p[-20:])
    ma50 = np.mean(p[-50:]) if len(p) >= 50 else ma20

    if p[-1] > ma20 > ma50:
        return "bull"
    elif p[-1] < ma20 < ma50:
        return "bear"
    else:
        return "neutral"

# ================= SIGNAL ENGINE =================
def signals(data):
    scored = []

    for s, d in data.items():
        try:
            p = np.array(d["close"], dtype=float)

            ret3 = (p[-1] / p[-3]) - 1 if len(p) >= 3 else 0
            ret10 = (p[-1] / p[-10]) - 1 if len(p) >= 10 else 0

            high20 = np.max(p[-20:]) if len(p) >= 20 else p[-1]
            breakout = (p[-1] - high20) / (high20 + 1e-6)

            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) if len(p) >= 20 else 0.02
            vol = vol if np.isfinite(vol) else 0.02

            score = float(ret3 + ret10 + breakout)

            scored.append((s, score, vol))

        except:
            continue

    if not scored:
        for s, d in data.items():
            try:
                p = d["close"]
                score = (p[-1] - p[-2]) / p[-2]
                scored.append((s, score, 0.02))
            except:
                continue

    return sorted(scored, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    global portfolio

    data = load(UNIVERSE + ["SPY"])
    portfolio["symbols_loaded"] = list(data.keys())

    if len(data) < 5:
        return {"error": "DATA FAILURE"}

    # ===== REGIME =====
    regime = detect_regime(data)
    portfolio["regime"] = regime

    sig = signals(data)

    # ===== EQUITY =====
    equity = portfolio["cash"]
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # ===== STOP LOSS =====
    for s, pos in list(portfolio["positions"].items()):
        low = sf(data[s]["low"][-1])
        entry = pos["entry"]

        if (low - entry)/entry < -STOP_LOSS:
            price = sf(data[s]["close"][-1])
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append((s, "stop"))
            del portfolio["positions"][s]

    # ===== MICRO TAKE PROFIT =====
    for s, pos in list(portfolio["positions"].items()):
        price = sf(data[s]["close"][-1])
        gain = (price - pos["entry"]) / pos["entry"]

        if gain > 0.01:
            sell = pos["shares"] * 0.3
            portfolio["cash"] += sell * price
            pos["shares"] -= sell
            portfolio["trades"].append((s, "take_profit"))

    # ===== TARGET BUILD =====
    used_sectors = set()
    targets = []

    for s, score, vol in sig:
        if regime == "bear" and score > 0:
            continue  # avoid longs in bear

        sector = SECTOR_MAP.get(s, "other")

        if sector in used_sectors:
            continue

        targets.append((s, score, vol))
        used_sectors.add(sector)

        if len(targets) >= MAX_POSITIONS:
            break

    # ===== ENTRY =====
    capital_per_trade = portfolio["equity"] / MAX_POSITIONS

    for s, score, vol in targets:
        if s in portfolio["positions"]:
            continue

        price = sf(data[s]["close"][-1])
        size = capital_per_trade * (1/(1+vol*5))

        if portfolio["cash"] >= size * 0.95:
            shares = size / price
            portfolio["cash"] -= size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price,
                "adds": 0
            }

    # ===== PYRAMIDING =====
    for s, pos in portfolio["positions"].items():
        price = sf(data[s]["close"][-1])
        gain = (price - pos["entry"]) / pos["entry"]

        if gain > PYRAMID_THRESHOLD and pos["adds"] < PYRAMID_LIMIT:
            size = (portfolio["equity"] / MAX_POSITIONS) * 0.5

            if portfolio["cash"] >= size:
                shares = size / price
                portfolio["cash"] -= size

                pos["shares"] += shares
                pos["adds"] += 1

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    return {
        "equity": round(portfolio["equity"],2),
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(sig),
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

<h2>📊 AI Trading Dashboard (Regime Aware)</h2>

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

 let eq = (p.history.length>1) ? p.history : [10000,10000];

 new Chart(document.getElementById('eq'),{
  type:'line',
  data:{
    labels:eq.map((_,i)=>i),
    datasets:[{label:'Equity',data:eq}]
  }
 });
}

load();
setInterval(load,10000);
</script>

</body>
</html>
""")

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status":"REGIME SYSTEM LIVE"}

@app.route("/paper/run")
def run_api():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
