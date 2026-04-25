import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

# ================= CONFIG =================
UNIVERSE = [
    "NVDA","AMD","META","TSLA","AVGO",
    "ARM","PANW","CRWD","PLTR","SNOW"
]

BASE_RISK = 0.02
MAX_POSITIONS = 4
STOP_LOSS = 0.05

portfolio = {
    "cash": 10000,
    "equity": 10000,
    "peak": 10000,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "symbols_loaded": [],
    "ai_notes": []
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
            print(f"DATA FAIL: {s} -> {e}")

    return data

# ================= SIGNAL ENGINE (GUARANTEED) =================
def signals(data):
    scored = []

    for s, p in data.items():
        try:
            p = np.array(p, dtype=float)

            if len(p) < 30:
                continue

            ret20 = (p[-1] / p[-20]) - 1
            ret5 = (p[-1] / p[-5]) - 1

            if not np.isfinite(ret20) or not np.isfinite(ret5):
                continue

            vol = np.std(np.diff(p[-20:]) / p[-20:-1])

            if not np.isfinite(vol) or vol == 0:
                vol = 0.02

            score = float(ret20 + ret5)

            scored.append((s, score, vol))

        except Exception as e:
            print(f"SIGNAL FAIL: {s} -> {e}")

    # 🚨 FALLBACK (never allow empty)
    if not scored:
        print("⚠️ FALLBACK SIGNAL ACTIVATED")
        for s, p in data.items():
            try:
                score = (p[-1] - p[-2]) / p[-2]
                scored.append((s, score, 0.02))
            except:
                continue

    scored = sorted(scored, key=lambda x: x[1], reverse=True)

    return scored[:MAX_POSITIONS]

# ================= AI SUPERVISOR =================
def ai_supervisor():
    eq = portfolio["history"]

    if len(eq) < 10:
        portfolio["ai_notes"] = ["Collecting data..."]
        return

    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak = eq[0]
    dd = 0
    for e in eq:
        peak = max(peak,e)
        dd = min(dd,(e-peak)/peak)

    notes = []

    if sharpe < 0.5:
        notes.append("⚠️ Weak edge")
    if dd < -0.1:
        notes.append("⚠️ High drawdown")
    if sharpe > 2:
        notes.append("✅ Strong system")

    if not notes:
        notes.append("Stable")

    portfolio["ai_notes"] = notes

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

    equity = portfolio["cash"]

    # VALUE POSITIONS
    for s, pos in portfolio["positions"].items():
        if s in data:
            price = sf(data[s][-1])
            equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # STOP LOSS + CLOSE
    for s, pos in list(portfolio["positions"].items()):
        price = sf(data[s][-1])
        pnl = (price - pos["entry"]) / pos["entry"]

        if pnl < -STOP_LOSS:
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append(pnl)
            del portfolio["positions"][s]

    # FULL ROTATION
    for s in list(portfolio["positions"].keys()):
        price = sf(data[s][-1])
        portfolio["cash"] += portfolio["positions"][s]["shares"] * price
        del portfolio["positions"][s]

    # ENTRY
    for s, score, vol in sig:
        price = sf(data[s][-1])
        size = portfolio["equity"] * BASE_RISK / max(vol, 0.02)

        if portfolio["cash"] >= size:
            shares = size / price
            portfolio["cash"] -= size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    ai_supervisor()

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

<h2>📊 AI Trading Dashboard</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><pre id="positions"></pre></div>
<div class="card"><pre id="symbols"></pre></div>
<div class="card"><pre id="ai"></pre></div>
</div>

<script>
async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());

 document.getElementById('positions').innerText =
  JSON.stringify(p.positions,null,2);

 document.getElementById('symbols').innerText =
  "Loaded:\\n" + JSON.stringify(p.symbols_loaded,null,2);

 document.getElementById('ai').innerText =
  JSON.stringify(p.ai_notes,null,2);

 let eq = (p.history.length>1) ? p.history : [10000,10000];

 new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),
  datasets:[{label:'Equity',data:eq}]}
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
