import os
import time
import threading
from datetime import datetime
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# =========================
# UNIVERSE
# =========================
SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA","AVGO","CRM",
    "PANW","SNOW","NOW","ZS","CRWD","MDB","NET","SHOP",
    "JPM","BAC","GS","MS","C","WFC",
    "CAT","DE","GE","BA","HON","UPS","FDX",
    "COST","WMT","HD","MCD","NKE","SBUX",
    "LLY","JNJ","PFE","MRK","ABBV","TMO",
    "XOM","CVX","SLB",
    "SPY","QQQ","IWM"
]

# =========================
# SETTINGS
# =========================
MAX_POSITION_SIZE = 0.4
TARGET_VOL = 0.15

MAX_DRAWDOWN = -0.10
MAX_DAILY_LOSS = -0.03
MAX_POSITION_RISK = 0.02
COOLDOWN_CYCLES = 2

# =========================
# STATE
# =========================
portfolio = {
    "cash": 10000,
    "equity": 10000,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None,
    "cooldown": 0,
    "last_equity": 10000
}

# =========================
# DATA
# =========================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False)
            if df is None or df.empty:
                continue

            prices = np.array(df["Close"]).reshape(-1)
            volumes = np.array(df["Volume"]).reshape(-1)

            if len(prices) < 60:
                continue
            if np.mean(volumes[-20:]) < 1_000_000:
                continue
            if prices[-1] < 10:
                continue

            data[s] = prices.astype(float)
        except:
            continue
    return data

def get_vol(prices, i):
    returns = np.diff(prices[i-20:i]) / prices[i-20:i-1]
    return np.std(returns) + 1e-6

# =========================
# REGIME
# =========================
def get_regime_strength():
    try:
        df = yf.download("SPY", period="3mo", interval="1d", progress=False)
        prices = np.array(df["Close"])

        ma20 = np.mean(prices[-20:])
        ma50 = np.mean(prices[-50:])
        strength = (ma20 - ma50) / ma50

        if strength > 0.02:
            return "bull_strong", 0.8
        elif strength > 0:
            return "bull_weak", 0.6
        elif strength > -0.02:
            return "neutral", 0.5
        else:
            return "bear", 0.0
    except:
        return "neutral", 0.5

# =========================
# STRATEGIES
# =========================
def mean_reversion(data, idx):
    scores = []
    for s, prices in data.items():
        z = (prices[idx] - np.mean(prices[idx-20:idx])) / np.std(prices[idx-20:idx])
        if z < -0.7:
            scores.append((s, abs(z)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:3]

def momentum(data, idx):
    scores = []
    for s, prices in data.items():
        ret = (prices[idx] / prices[idx-20]) - 1
        vol = get_vol(prices, idx)
        scores.append((s, ret/vol))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:3]

def short_strategy(data, idx):
    scores = []
    for s, prices in data.items():
        ret = (prices[idx] / prices[idx-20]) - 1
        scores.append((s, ret))
    scores.sort(key=lambda x: x[1])  # worst performers
    return scores[:3]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals():
    data = load_data()
    if len(data) < 5:
        return [], "none"

    idx = min(len(p) for p in data.values()) - 1
    regime, w = get_regime_strength()

    if regime == "bear":
        shorts = short_strategy(data, idx)
        total = sum(abs(x[1]) for x in shorts)
        return [
            {"symbol": s, "weight": abs(v)/total, "side": "short"}
            for s, v in shorts
        ], "bear_short"

    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}
    for s, v in mom:
        combined[s] = combined.get(s, 0) + v*w
    for s, v in mr:
        combined[s] = combined.get(s, 0) + v*(1-w)

    top = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:3]
    total = sum(x[1] for x in top)

    return [
        {"symbol": s, "weight": v/total, "side": "long"}
        for s, v in top
    ], regime

# =========================
# RISK
# =========================
def risk_check():
    eq = portfolio["equity"]
    hist = portfolio["history"]

    if len(hist) > 5:
        peak = max(hist)
        dd = (eq - peak) / peak
        if dd <= MAX_DRAWDOWN:
            return "KILL"

    daily = (eq - portfolio["last_equity"]) / portfolio["last_equity"]
    if daily <= MAX_DAILY_LOSS:
        portfolio["cooldown"] = COOLDOWN_CYCLES
        return "STOP"

    if portfolio["cooldown"] > 0:
        portfolio["cooldown"] -= 1
        return "COOLDOWN"

    return "OK"

# =========================
# EXECUTION (FIXED CASH MODEL)
# =========================
def run_paper():
    global portfolio

    if risk_check() != "OK":
        portfolio["history"].append(portfolio["equity"])
        return {"status": "risk_pause"}

    data = load_data()
    signals, regime = generate_signals()

    if not data:
        return {"error":"no data"}

    idx = min(len(p) for p in data.values()) - 1

    # close all → cash
    portfolio["cash"] = portfolio["equity"]
    portfolio["positions"] = {}

    capital = portfolio["cash"]

    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        price = data[s][idx]

        alloc = capital * min(sig["weight"], MAX_POSITION_SIZE)
        alloc = min(alloc, portfolio["equity"] * MAX_POSITION_RISK)

        shares = alloc / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price,
            "side": sig["side"]
        }

    # compute value
    position_value = 0
    for s, pos in new_positions.items():
        price = data[s][idx]

        if pos["side"] == "long":
            position_value += pos["shares"] * price
        else:
            position_value += pos["shares"] * (pos["entry_price"] - price)

    used = sum(pos["shares"] * pos["entry_price"] for pos in new_positions.values())

    portfolio["cash"] = capital - used
    portfolio["positions"] = new_positions
    portfolio["equity"] = portfolio["cash"] + position_value

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"] = str(datetime.utcnow())
    portfolio["last_equity"] = portfolio["equity"]
    portfolio["strategy"] = regime

    return {"equity": round(portfolio["equity"],2), "strategy": regime}

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { background:#0f172a; color:white; font-family:Arial; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:15px; }
.card { background:#1e293b; padding:15px; border-radius:10px; }
</style>
</head>
<body>

<h1>📊 Full Trading System</h1>

<div class="grid">
<div class="card"><h3>Equity</h3><canvas id="eq"></canvas></div>
<div class="card"><h3>Drawdown</h3><canvas id="dd"></canvas></div>

<div class="card"><h3>Signals</h3><pre id="signals"></pre></div>
<div class="card"><h3>Portfolio</h3><pre id="portfolio"></pre></div>

<div class="card"><h3>Risk</h3><pre id="risk"></pre></div>
<div class="card"><h3>Strategy</h3><pre id="strategy"></pre></div>
</div>

<script>
let ec, dc;

function dd(eq){
 let peak=eq[0];
 return eq.map(e=>{
  peak=Math.max(peak,e);
  return (e-peak)/peak*100;
 });
}

async function load(){
 let p=await fetch('/paper/status').then(r=>r.json());
 let s=await fetch('/signals').then(r=>r.json());

 document.getElementById('signals').innerText=JSON.stringify(s,null,2);
 document.getElementById('portfolio').innerText=JSON.stringify(p,null,2);
 document.getElementById('strategy').innerText=p.strategy;

 document.getElementById('risk').innerText=JSON.stringify({
  cooldown:p.cooldown,
  equity:p.equity
 },null,2);

 let eq=p.history||[];
 let d=dd(eq);

 if(ec) ec.destroy();
 ec=new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
 });

 if(dc) dc.destroy();
 dc=new Chart(document.getElementById('dd'),{
  type:'line',
  data:{labels:d.map((_,i)=>i),datasets:[{label:'Drawdown',data:d}]}
 });
}

load();
setInterval(load,10000);
</script>

</body>
</html>
""")

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"LIVE SYSTEM"}

@app.route("/signals")
def signals():
    sigs, reg = generate_signals()
    return jsonify({"regime":reg,"signals":sigs})

@app.route("/paper/run")
def run():
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

# =========================
# START
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=PORT)
