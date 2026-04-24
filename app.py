import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

UNIVERSE = [
    "NVDA","AMD","META","TSLA","AVGO",
    "ARM","PANW","CRWD","PLTR","SNOW"
]

BASE_RISK = 0.01
MAX_POSITIONS = 4

portfolio = {
    "cash": 10000,
    "equity": 10000,
    "positions": {},
    "history": [],
    "last_run": None,
    "symbols_loaded": []
}

def sf(x):
    return float(np.asarray(x).item())

# ================= DATA =================
def load(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="3mo", progress=False)

            if df is None or df.empty:
                continue

            prices = df["Close"].values

            if len(prices) < 50:
                continue

            data[s] = prices

        except Exception as e:
            print("DATA FAIL:", s)

    return data

# ================= SIGNALS =================
def signals(data):
    scored = []

    for s, p in data.items():
        try:
            ret20 = (p[-1] / p[-20]) - 1
            ret5 = (p[-1] / p[-5]) - 1

            score = ret20 + ret5

            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            scored.append((s, score, vol))

        except:
            continue

    if not scored:
        return []

    scored = sorted(scored, key=lambda x: x[1], reverse=True)

    return scored[:MAX_POSITIONS]

# ================= ENGINE =================
def run_engine():
    global portfolio

    symbols = UNIVERSE + ["SPY"]
    data = load(symbols)

    portfolio["symbols_loaded"] = list(data.keys())

    if len(data) < 3:
        return {
            "error": "DATA FAILURE",
            "symbols_loaded": portfolio["symbols_loaded"]
        }

    sig = signals(data)

    if not sig:
        return {
            "error": "NO SIGNALS",
            "symbols_loaded": portfolio["symbols_loaded"]
        }

    equity = portfolio["cash"]

    # VALUE
    for s, pos in portfolio["positions"].items():
        if s in data:
            equity += pos["shares"] * sf(data[s][-1])

    portfolio["equity"] = equity

    # CLEAR (simple rotation)
    for s in list(portfolio["positions"].keys()):
        price = sf(data[s][-1])
        portfolio["cash"] += portfolio["positions"][s]["shares"] * price
        del portfolio["positions"][s]

    # ENTRY
    for s, score, vol in sig:
        price = sf(data[s][-1])
        size = portfolio["equity"] * BASE_RISK / max(vol, 0.01)

        if portfolio["cash"] >= size:
            shares = size / price
            portfolio["cash"] -= size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    return {
        "equity": round(portfolio["equity"], 2),
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(sig),
        "symbols_loaded": portfolio["symbols_loaded"]
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

<h2>📊 Trading Dashboard</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><pre id="positions"></pre></div>
<div class="card"><pre id="symbols"></pre></div>
</div>

<script>
async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());

 document.getElementById('positions').innerText =
  JSON.stringify(p.positions,null,2);

 document.getElementById('symbols').innerText =
  "Loaded Symbols:\\n" + JSON.stringify(p.symbols_loaded,null,2);

 let eq = (p.history.length>1) ? p.history : [10000,10000];

 new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
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
    return {"status":"SYSTEM LIVE"}

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
