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
# PORTFOLIO SETTINGS
# =========================
MAX_POSITION_SIZE = 0.4
TARGET_VOL = 0.15

# =========================
# RISK ENGINE SETTINGS
# =========================
MAX_DRAWDOWN = -0.10
MAX_DAILY_LOSS = -0.03
MAX_POSITION_RISK = 0.02
COOLDOWN_CYCLES = 2

# =========================
# STATE
# =========================
portfolio = {
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
# REGIME STRENGTH
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
        window = prices[idx-20:idx]
        std = np.std(window)
        if std < 1e-6:
            continue

        z = (prices[idx] - np.mean(window)) / std
        if z < -0.7:
            vol = get_vol(prices, idx)
            strength = abs(z)/vol
            scores.append((s, strength))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [{"symbol": s, "weight": w} for s, w in scores[:3]]

def momentum(data, idx):
    scores = []
    for s, prices in data.items():
        ret = (prices[idx] / prices[idx-20]) - 1
        vol = get_vol(prices, idx)
        score = ret / vol
        scores.append((s, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [{"symbol": s, "weight": w} for s, w in scores[:3]]

# =========================
# BLENDED SIGNAL ENGINE
# =========================
def generate_signals():
    data = load_data()
    if len(data) < 5:
        return [], "none"

    idx = min(len(p) for p in data.values()) - 1

    regime, mom_w = get_regime_strength()
    mr_w = 1 - mom_w

    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}

    for s in mom:
        combined[s["symbol"]] = combined.get(s["symbol"], 0) + s["weight"] * mom_w

    for s in mr:
        combined[s["symbol"]] = combined.get(s["symbol"], 0) + s["weight"] * mr_w

    if not combined:
        return [], regime

    sorted_syms = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:3]
    total = sum(x[1] for x in sorted_syms)

    signals = [{"symbol": s, "weight": w/total} for s, w in sorted_syms]
    return signals, regime

# =========================
# PORTFOLIO VOL
# =========================
def compute_portfolio_vol(history):
    if len(history) < 10:
        return 0.1
    returns = np.diff(history) / history[:-1]
    return np.std(returns) * np.sqrt(252)

# =========================
# RISK ENGINE
# =========================
def risk_check():
    equity = portfolio["equity"]
    history = portfolio["history"]

    if len(history) > 5:
        peak = max(history)
        dd = (equity - peak) / peak
        if dd <= MAX_DRAWDOWN:
            return "KILL_SWITCH"

    last = portfolio["last_equity"]
    daily = (equity - last) / last

    if daily <= MAX_DAILY_LOSS:
        portfolio["cooldown"] = COOLDOWN_CYCLES
        return "DAILY_STOP"

    if portfolio["cooldown"] > 0:
        portfolio["cooldown"] -= 1
        return "COOLDOWN"

    return "OK"

# =========================
# EXECUTION
# =========================
def run_paper():
    global portfolio

    risk = risk_check()
    if risk == "KILL_SWITCH":
        return {"status":"stopped - drawdown"}
    if risk in ["DAILY_STOP","COOLDOWN"]:
        portfolio["history"].append(portfolio["equity"])
        return {"status":risk}

    data = load_data()
    signals, regime = generate_signals()

    if not data:
        return {"error":"no data"}

    idx = min(len(p) for p in data.values()) - 1

    # close trades
    for s, pos in portfolio["positions"].items():
        if s in data:
            price = data[s][idx]
            pnl = (price - pos["entry_price"]) * pos["shares"]
            portfolio["trades"].append({
                "symbol": s,
                "entry": pos["entry_price"],
                "exit": price,
                "pnl": round(pnl,2)
            })

    capital = portfolio["equity"]

    # volatility scaling
    vol = compute_portfolio_vol(portfolio["history"])
    scale = min(1.5, max(0.5, TARGET_VOL / (vol+1e-6)))
    capital *= scale

    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        price = data[s][idx]

        alloc = capital * min(sig["weight"], MAX_POSITION_SIZE)
        alloc = min(alloc, portfolio["equity"] * MAX_POSITION_RISK)

        shares = alloc / price

        new_positions[s] = {"shares":shares,"entry_price":price}

    portfolio["positions"] = new_positions

    total = sum(pos["shares"] * data[s][idx] for s,pos in new_positions.items())

    portfolio["equity"] = total
    portfolio["history"].append(total)
    portfolio["last_run"] = str(datetime.utcnow())
    portfolio["strategy"] = regime
    portfolio["last_equity"] = total

    return {"equity":round(total,2),"regime":regime}

# =========================
# AUTO RUN
# =========================
def scheduler():
    while True:
        now = datetime.utcnow()
        if now.hour == 21 and now.minute == 0:
            run_paper()
            time.sleep(60)
        time.sleep(30)

def start_scheduler():
    t = threading.Thread(target=scheduler)
    t.daemon = True
    t.start()

# =========================
# METRICS
# =========================
def get_metrics():
    equity = portfolio["history"]
    if len(equity) < 10:
        return {"message":"not enough data"}

    returns = np.diff(equity)/equity[:-1]
    sharpe = np.mean(returns)/(np.std(returns)+1e-6)*np.sqrt(252)

    peak = equity[0]
    dd = 0
    for e in equity:
        peak = max(peak,e)
        dd = min(dd,(e-peak)/peak)

    return {
        "sharpe":round(sharpe,2),
        "drawdown_pct":round(dd*100,2)
    }

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

<h1>📊 Institutional Trading Dashboard</h1>

<div class="grid">
<div class="card"><h3>Equity</h3><canvas id="eq"></canvas></div>
<div class="card"><h3>Drawdown</h3><canvas id="dd"></canvas></div>

<div class="card"><h3>Signals</h3><pre id="signals"></pre></div>
<div class="card"><h3>Risk</h3><pre id="risk"></pre></div>

<div class="card"><h3>Metrics</h3><pre id="metrics"></pre></div>
<div class="card"><h3>Positions</h3><pre id="positions"></pre></div>
</div>

<script>
let ec, dc;

function drawdown(eq){
 let peak=eq[0];
 return eq.map(e=>{
  peak=Math.max(peak,e);
  return (e-peak)/peak*100;
 });
}

async function load(){
 let p=await fetch('/paper/status').then(r=>r.json());
 let s=await fetch('/signals').then(r=>r.json());
 let m=await fetch('/paper/metrics').then(r=>r.json());

 document.getElementById('signals').innerText=JSON.stringify(s,null,2);
 document.getElementById('positions').innerText=JSON.stringify(p.positions,null,2);
 document.getElementById('metrics').innerText=JSON.stringify(m,null,2);
 document.getElementById('risk').innerText=JSON.stringify({
   cooldown:p.cooldown,
   equity:p.equity,
   strategy:p.strategy
 },null,2);

 let eq=p.history||[];
 let dd=drawdown(eq);

 if(ec) ec.destroy();
 ec=new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
 });

 if(dc) dc.destroy();
 dc=new Chart(document.getElementById('dd'),{
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

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"INSTITUTIONAL SYSTEM LIVE"}

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

@app.route("/paper/metrics")
def metrics():
    return jsonify(get_metrics())

# =========================
# START
# =========================
start_scheduler()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=PORT)
