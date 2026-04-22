import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA",
    "JPM","BAC","GS","MS","CAT","DE","GE",
    "COST","WMT","HD","LLY","JNJ","XOM","CVX","SPY","QQQ"
]

BASE_RISK = 0.015
MAX_HEAT = 0.20
MAX_POSITIONS = 3
STOP_LOSS = 0.05
REBALANCE_EVERY = 10
DECAY_RATE = 0.5
PYRAMID_THRESHOLD = 0.03

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "step": 80,
    "last_signals": [],
    "strategy": None
}

def safe_float(x):
    try:
        return float(np.asarray(x).item())
    except:
        return float(x)

# ================= DATA =================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", progress=False)
            if df.empty:
                continue
            prices = np.array(df["Close"], dtype=float)
            if len(prices) > 80:
                data[s] = prices
        except:
            continue
    return data

# ================= REGIME =================
def get_regime(data):
    spy = data.get("SPY")
    if spy is None:
        return "neutral"

    ma20 = np.mean(spy[-20:])
    ma50 = np.mean(spy[-50:])

    if ma20 > ma50 * 1.01:
        return "bull"
    elif ma20 < ma50 * 0.99:
        return "bear"
    return "neutral"

# ================= VOL =================
def get_vol(p, idx):
    r = np.diff(p[idx-20:idx]) / p[idx-20:idx-1]
    return np.std(r) + 1e-6

# ================= SIGNALS =================
def generate_signals(data, idx, regime):
    momentum, mean_rev = [], []

    for s,p in data.items():
        try:
            price = p[idx]
            ma50 = np.mean(p[idx-50:idx])
            ret20 = (p[idx]/p[idx-20]) - 1
            vol = get_vol(p, idx)

            if regime == "bull" and price > ma50 and ret20 > 0.03:
                momentum.append((s, ret20/vol, vol))

            elif regime == "bear" and price < ma50 and ret20 < -0.03:
                momentum.append((s, -ret20/vol, vol))

            z = (price - np.mean(p[idx-20:idx])) / (np.std(p[idx-20:idx])+1e-6)
            if regime == "neutral" and z < -1:
                mean_rev.append((s, abs(z), vol))

        except:
            continue

    combined = sorted(momentum + mean_rev, key=lambda x:x[1], reverse=True)

    if not combined:
        syms = list(data.keys())
        np.random.shuffle(syms)
        return [(s,0.01,0.02) for s in syms[:MAX_POSITIONS]]

    return combined[:MAX_POSITIONS]

# ================= EXECUTION =================
def run_paper():
    global portfolio

    data = load_data()
    if not data:
        return {"error":"no data"}

    idx = portfolio["step"]
    portfolio["step"] += 1

    regime = get_regime(data)
    signals = generate_signals(data, idx, regime)

    portfolio["last_signals"] = signals
    portfolio["strategy"] = regime

    # ===== MARK TO MARKET =====
    equity = portfolio["cash"]
    for s,pos in portfolio["positions"].items():
        if s in data:
            price = safe_float(data[s][idx])
            if pos["side"] == "long":
                equity += pos["shares"] * price
            else:
                pnl = (pos["entry"] - price) * pos["shares"]
                equity += pos["shares"] * pos["entry"] + pnl

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    total_exposure = sum(
        pos["shares"] * data[s][idx]
        for s,pos in portfolio["positions"].items()
        if s in data
    )

    max_allowed = portfolio["equity"] * MAX_HEAT

    # ===== STOP LOSS =====
    for s,pos in list(portfolio["positions"].items()):
        price = safe_float(data[s][idx])

        if pos["side"] == "long":
            loss = (price - pos["entry"]) / pos["entry"]
        else:
            loss = (pos["entry"] - price) / pos["entry"]

        if loss < -STOP_LOSS:
            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append({"symbol": s, "pnl": round(loss*100,2)})
            del portfolio["positions"][s]

    # ===== ROTATION + DECAY =====
    current = set(portfolio["positions"].keys())
    target = set(s[0] for s in signals)
    rebalance = portfolio["step"] % REBALANCE_EVERY == 0

    for s in list(current):
        if s not in target or rebalance:
            pos = portfolio["positions"][s]
            price = safe_float(data[s][idx])

            sell = pos["shares"] * DECAY_RATE
            remain = pos["shares"] - sell

            pnl = (price - pos["entry"]) * sell
            if pos["side"] == "short":
                pnl = (pos["entry"] - price) * sell

            portfolio["cash"] += sell * price
            portfolio["trades"].append({"symbol": s, "pnl": round(pnl,2)})

            if remain <= 0.01:
                del portfolio["positions"][s]
            else:
                pos["shares"] = remain

    # ===== ENTRY + PYRAMID =====
    for s,score,vol in signals:
        price = safe_float(data[s][idx])

        if s in portfolio["positions"]:
            pos = portfolio["positions"][s]

            if pos["side"] == "long":
                gain = (price - pos["entry"]) / pos["entry"]
            else:
                gain = (pos["entry"] - price) / pos["entry"]

            if gain > PYRAMID_THRESHOLD:
                add = portfolio["equity"] * 0.01
                if total_exposure + add < max_allowed:
                    pos["shares"] += add / price
                    portfolio["cash"] -= add

        else:
            size = portfolio["equity"] * BASE_RISK
            if total_exposure + size > max_allowed:
                continue

            shares = size / price
            side = "long" if regime == "bull" else "short"

            portfolio["cash"] -= size
            portfolio["positions"][s] = {
                "shares": shares,
                "entry": price,
                "side": side
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())

    return {"equity": round(portfolio["equity"],2), "regime": regime}

# ================= METRICS =================
@app.route("/paper/metrics")
def metrics():
    eq = portfolio["history"]
    if len(eq) < 10:
        return {"message":"not enough data"}

    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak = eq[0]
    dd = 0
    for e in eq:
        peak = max(peak,e)
        dd = min(dd,(e-peak)/peak)

    pnls = [t["pnl"] for t in portfolio["trades"]]
    wins = [p for p in pnls if p > 0]

    return {
        "sharpe": round(sharpe,2),
        "drawdown_pct": round(dd*100,2),
        "trades": len(pnls),
        "win_rate": round(len(wins)/len(pnls)*100,2) if pnls else 0,
        "total_pnl": round(sum(pnls),2)
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
<div class="card"><canvas id="dd"></canvas></div>
<div class="card"><pre id="signals"></pre></div>
<div class="card"><pre id="metrics"></pre></div>
</div>

<script>
let eqChart, ddChart;

function calcDD(eq){
 let peak=eq[0];
 return eq.map(e=>{
  peak=Math.max(peak,e);
  return (e-peak)/peak*100;
 });
}

async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());
 let m = await fetch('/paper/metrics').then(r=>r.json());

 document.getElementById('signals').innerText =
  JSON.stringify(p.last_signals,null,2);

 document.getElementById('metrics').innerText =
  JSON.stringify(m,null,2);

 let eq = (p.history.length>1) ? p.history : [10000,10000];
 let dd = calcDD(eq);

 if(eqChart) eqChart.destroy();
 eqChart = new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
 });

 if(ddChart) ddChart.destroy();
 ddChart = new Chart(document.getElementById('dd'),{
  type:'line',
  data:{labels:dd.map((_,i)=>i),datasets:[{label:'Drawdown %',data:dd}]}
 });
}

load();
setInterval(load,10000);
</script>

</body>
</html>
""")

@app.route("/")
def home():
    return {"status":"FINAL SYSTEM LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
