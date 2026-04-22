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
# STATE
# =========================
portfolio = {
    "cash": 10000,
    "equity": 10000,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None
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
# REGIME FILTER
# =========================
def get_market_regime():
    try:
        df = yf.download("SPY", period="3mo", interval="1d", progress=False)
        prices = np.array(df["Close"])

        ma20 = np.mean(prices[-20:])
        ma50 = np.mean(prices[-50:])

        returns = np.diff(prices[-20:]) / prices[-21:-1]
        vol = np.std(returns)

        if ma20 > ma50 and vol < 0.02:
            return "bull"
        elif ma20 < ma50 and vol > 0.02:
            return "bear"
        else:
            return "neutral"
    except:
        return "neutral"

# =========================
# SIGNALS
# =========================
def generate_signals():
    regime = get_market_regime()

    # Avoid bad environments
    if regime == "bear":
        return []

    data = load_data()

    if len(data) < 5:
        return []

    idx = min(len(p) for p in data.values()) - 1
    scores = []

    for s, prices in data.items():
        window = prices[idx-20:idx]
        mean = np.mean(window)
        std = np.std(window)

        if std < 1e-6:
            continue

        z = (prices[idx] - mean) / std

        if z < -0.7:
            vol = get_vol(prices, idx)
            strength = abs(z) / vol
            scores.append((s, z, strength))

    if len(scores) < 2:
        return []

    scores.sort(key=lambda x: x[1])
    bottom = scores[:3]

    strengths = [(s, strength) for s, _, strength in bottom]
    total = sum(x[1] for x in strengths)
    n = len(strengths)

    signals = []
    for s, strength in strengths:
        base_weight = 0.5*(1/n) + 0.5*(strength/total)

        # controlled volatility scaling
        vol_adj = min(1.2, max(0.8, 1 / strength))

        weight = base_weight * vol_adj

        signals.append({
            "symbol": s,
            "weight": round(weight, 3)
        })

    return signals

# =========================
# EXECUTION
# =========================
def run_paper():
    global portfolio

    data = load_data()
    signals = generate_signals()

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

    # drawdown protection
    capital = portfolio["equity"]

    if len(portfolio["history"]) > 5:
        peak = max(portfolio["history"])
        dd = (portfolio["equity"] - peak) / peak

        if dd < -0.05:
            capital *= 0.5

    if not signals:
        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())
        return {"message":"no trades"}

    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        price = data[s][idx]

        allocation = capital * sig["weight"]
        shares = allocation / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price
        }

    portfolio["positions"] = new_positions

    total = sum(pos["shares"] * data[s][idx] for s, pos in new_positions.items())

    portfolio["equity"] = total
    portfolio["history"].append(total)
    portfolio["last_run"] = str(datetime.utcnow())

    return {"equity": round(total,2), "positions": list(new_positions.keys())}

# =========================
# AUTO SCHEDULER
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
    trades = portfolio["trades"]

    if not trades:
        return {"message":"no trades yet"}

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]

    equity = portfolio["history"]

    peak = equity[0]
    dd = 0

    for e in equity:
        peak = max(peak, e)
        dd = min(dd, (e - peak)/peak)

    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins)/len(trades)*100,2),
        "total_pnl": round(sum(pnls),2),
        "max_drawdown_pct": round(dd*100,2)
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
<title>Pro Trading Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { background:#0f172a; color:white; font-family:Arial; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:15px; }
.card { background:#1e293b; padding:15px; border-radius:10px; }
table { width:100%; border-collapse:collapse; }
td, th { padding:6px; border-bottom:1px solid #334155; }
</style>
</head>
<body>

<h1>📊 Optimized Trading Dashboard</h1>

<div class="grid">

<div class="card"><h2>Equity</h2><canvas id="eq"></canvas></div>
<div class="card"><h2>Drawdown</h2><canvas id="dd"></canvas></div>

<div class="card"><h2>Signals</h2><pre id="signals"></pre></div>
<div class="card"><h2>Positions</h2><pre id="positions"></pre></div>

<div class="card"><h2>Metrics</h2><pre id="metrics"></pre></div>

<div class="card">
<h2>Trades</h2>
<table id="trades"><thead>
<tr><th>Symbol</th><th>Entry</th><th>Exit</th><th>PNL</th></tr>
</thead><tbody></tbody></table>
</div>

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
    let p = await fetch('/paper/status').then(r=>r.json());
    let s = await fetch('/signals').then(r=>r.json());
    let m = await fetch('/paper/metrics').then(r=>r.json());

    document.getElementById('signals').innerText = JSON.stringify(s,null,2);
    document.getElementById('positions').innerText = JSON.stringify(p.positions,null,2);
    document.getElementById('metrics').innerText = JSON.stringify(m,null,2);

    let eq = p.history || [];
    let d = dd(eq);

    if(ec) ec.destroy();
    ec = new Chart(document.getElementById('eq'),{
        type:'line',
        data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
    });

    if(dc) dc.destroy();
    dc = new Chart(document.getElementById('dd'),{
        type:'line',
        data:{labels:d.map((_,i)=>i),datasets:[{label:'Drawdown %',data:d}]}
    });

    let table = document.querySelector('#trades tbody');
    table.innerHTML = "";

    (p.trades || []).slice().reverse().forEach(t=>{
        table.innerHTML += `
        <tr>
        <td>${t.symbol}</td>
        <td>${t.entry.toFixed(2)}</td>
        <td>${t.exit.toFixed(2)}</td>
        <td style="color:${t.pnl>=0?'#22c55e':'#ef4444'}">${t.pnl}</td>
        </tr>`;
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
    return {"status":"OPTIMIZED SYSTEM LIVE"}

@app.route("/health")
def health():
    return {"status":"running"}

@app.route("/signals")
def signals():
    return jsonify({"signals": generate_signals()})

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
