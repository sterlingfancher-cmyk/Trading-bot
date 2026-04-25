import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

# ================= UNIVERSE =================
UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

# ================= SECTOR MAP =================
SECTOR_MAP = {
    "NVDA":"semis","AMD":"semis","TSM":"semis","AVGO":"semis","ARM":"semis","MU":"semis","LRCX":"semis",
    "META":"tech","GOOGL":"tech","MSFT":"tech","AMZN":"tech",
    "SNOW":"cloud","CRWD":"cloud","PANW":"cloud","NET":"cloud","PLTR":"cloud",
    "TSLA":"auto","SHOP":"ecom","ROKU":"media",
    "COIN":"crypto","IBIT":"crypto","ETHA":"crypto","GDLC":"crypto",
    "XOM":"energy","CVX":"energy",
    "RKLB":"defense","KTOS":"defense","LHX":"defense","NOC":"defense"
}

BASE_RISK = 0.02
MAX_POSITIONS = 4
STOP_LOSS = 0.05
SIGNAL_THRESHOLD = 0.01  # 🔥 reduces weak trades

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

            if df is None or df.empty or len(df) < 50:
                continue

            data[s] = {
                "close": df["Close"].values,
                "low": df["Low"].values
            }

        except:
            continue

    return data

# ================= SIGNAL ENGINE =================
def signals(data):
    scored = []

    for s, d in data.items():
        try:
            p = np.array(d["close"], dtype=float)

            ret20 = (p[-1] / p[-20]) - 1
            ret5 = (p[-1] / p[-5]) - 1
            vol = np.std(np.diff(p[-20:]) / p[-20:-1]) + 1e-6

            score = float(ret20 + ret5)

            if score > SIGNAL_THRESHOLD:  # 🔥 filter weak signals
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

    scored = sorted(scored, key=lambda x: x[1], reverse=True)

    return scored[:MAX_POSITIONS * 2]  # allow filtering later

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

    data = load(UNIVERSE + ["SPY"])
    portfolio["symbols_loaded"] = list(data.keys())

    if len(data) < 5:
        return {"error": "DATA FAILURE"}

    sig = signals(data)

    # ================= EQUITY =================
    equity = portfolio["cash"]
    for s, pos in portfolio["positions"].items():
        if s in data:
            price = sf(data[s]["close"][-1])
            equity += pos["shares"] * price

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # ================= STOP LOSS (INTRADAY) =================
    for s, pos in list(portfolio["positions"].items()):
        if s not in data:
            continue

        low = sf(data[s]["low"][-1])
        entry = pos["entry"]

        if (low - entry)/entry < -STOP_LOSS:
            price = sf(data[s]["close"][-1])
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append((low-entry)/entry)
            del portfolio["positions"][s]

    # ================= BUILD NEW TARGET =================
    used_sectors = set()
    targets = []

    for s, score, vol in sig:
        sector = SECTOR_MAP.get(s, "other")

        if sector in used_sectors:
            continue

        targets.append((s, score, vol))
        used_sectors.add(sector)

        if len(targets) >= MAX_POSITIONS:
            break

    # ================= REBALANCE =================
    capital_per_trade = portfolio["equity"] / MAX_POSITIONS

    for s, score, vol in targets:
        price = sf(data[s]["close"][-1])
        target_size = capital_per_trade * (1 / (1 + vol * 10))

        if s in portfolio["positions"]:
            continue  # hold winners 🔥

        if portfolio["cash"] >= target_size:
            shares = target_size / price
            portfolio["cash"] -= target_size

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price
            }

    # ================= TRIM NON-TARGETS =================
    for s in list(portfolio["positions"].keys()):
        if s not in [t[0] for t in targets]:
            price = sf(data[s]["close"][-1])
            portfolio["cash"] += portfolio["positions"][s]["shares"] * price
            del portfolio["positions"][s]

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    ai_supervisor()

    return {
        "equity": round(portfolio["equity"], 2),
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(sig)
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

<h2>📊 AI Trading Dashboard (Optimized)</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><pre id="positions"></pre></div>
<div class="card"><pre id="ai"></pre></div>
<div class="card"><pre id="trades"></pre></div>
</div>

<script>
async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());

 document.getElementById('positions').innerText =
  JSON.stringify(p.positions,null,2);

 document.getElementById('ai').innerText =
  JSON.stringify(p.ai_notes,null,2);

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
    return {"status":"OPTIMIZED SYSTEM LIVE"}

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
