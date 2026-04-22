import os
import time
import threading
from datetime import datetime
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# =========================
# SETTINGS
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

MAX_POSITION_RISK = 0.05
MAX_POSITION_SIZE = 0.4

MAX_DRAWDOWN = -0.10
MAX_DAILY_LOSS = -0.03
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
            if df.empty:
                continue

            prices = np.array(df["Close"]).reshape(-1)
            volumes = np.array(df["Volume"]).reshape(-1)

            if len(prices) < 60:
                continue
            if np.mean(volumes[-20:]) < 1_000_000:
                continue
            if prices[-1] < 10:
                continue

            data[s] = prices
        except:
            continue
    return data

def get_vol(prices, i):
    r = np.diff(prices[i-20:i]) / prices[i-20:i-1]
    return np.std(r) + 1e-6

# =========================
# REGIME
# =========================
def get_regime():
    try:
        df = yf.download("SPY", period="3mo", progress=False)
        p = np.array(df["Close"])
        ma20 = np.mean(p[-20:])
        ma50 = np.mean(p[-50:])
        strength = (ma20 - ma50) / ma50

        if strength > 0.02: return "bull_strong", 0.8
        if strength > 0: return "bull_weak", 0.6
        if strength > -0.02: return "neutral", 0.5
        return "bear", 0
    except:
        return "neutral", 0.5

# =========================
# STRATEGIES
# =========================
def momentum(data, idx):
    scores = []
    for s,p in data.items():
        ret = (p[idx]/p[idx-20])-1
        vol = get_vol(p, idx)
        scores.append((s, ret/vol))
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def mean_reversion(data, idx):
    scores = []
    for s,p in data.items():
        z = (p[idx]-np.mean(p[idx-20:idx]))/np.std(p[idx-20:idx])
        if z < -0.7:
            scores.append((s, abs(z)))
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def short_strategy(data, idx):
    scores = []
    for s,p in data.items():
        ret = (p[idx]/p[idx-20])-1
        scores.append((s, ret))
    return sorted(scores, key=lambda x:x[1])[:3]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals_with_data(data):
    if len(data) < 5:
        return [], "none"

    idx = min(len(p) for p in data.values()) - 1
    regime, w = get_regime()

    if regime == "bear":
        shorts = short_strategy(data, idx)
        total = sum(abs(x[1]) for x in shorts)
        return [{"symbol":s,"weight":abs(v)/total,"side":"short"} for s,v in shorts], "bear_short"

    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}
    for s,v in mom:
        combined[s] = combined.get(s,0)+v*w
    for s,v in mr:
        combined[s] = combined.get(s,0)+v*(1-w)

    top = sorted(combined.items(), key=lambda x:x[1], reverse=True)[:3]
    total = sum(x[1] for x in top)

    return [{"symbol":s,"weight":v/total,"side":"long"} for s,v in top], regime

def generate_signals():
    return generate_signals_with_data(load_data())

# =========================
# RISK
# =========================
def risk_check():
    eq = portfolio["equity"]
    hist = portfolio["history"]

    if len(hist)>5:
        peak=max(hist)
        if (eq-peak)/peak <= MAX_DRAWDOWN:
            return "KILL"

    daily = (eq-portfolio["last_equity"])/portfolio["last_equity"]
    if daily <= MAX_DAILY_LOSS:
        portfolio["cooldown"]=COOLDOWN_CYCLES
        return "STOP"

    if portfolio["cooldown"]>0:
        portfolio["cooldown"]-=1
        return "COOLDOWN"

    return "OK"

# =========================
# EXECUTION
# =========================
def run_paper():
    global portfolio

    if risk_check() != "OK":
        portfolio["history"].append(portfolio["equity"])
        return {"status":"risk_pause"}

    data = load_data()
    signals, regime = generate_signals_with_data(data)
    idx = min(len(p) for p in data.values()) - 1

    # log trades
    for s,pos in portfolio["positions"].items():
        if s in data:
            price = data[s][idx]
            pnl = (price-pos["entry_price"])*pos["shares"] if pos["side"]=="long" else (pos["entry_price"]-price)*pos["shares"]
            portfolio["trades"].append({"symbol":s,"side":pos["side"],"entry":pos["entry_price"],"exit":price,"pnl":round(pnl,2)})

    # reset to cash
    portfolio["cash"]=portfolio["equity"]
    portfolio["positions"]={}

    new_pos={}
    for sig in signals:
        s=sig["symbol"]
        price=data[s][idx]

        alloc = portfolio["cash"] * min(sig["weight"], MAX_POSITION_SIZE)
        alloc = min(alloc, portfolio["equity"]*MAX_POSITION_RISK)

        shares=alloc/price

        new_pos[s]={"shares":shares,"entry_price":price,"side":sig["side"]}

    # value
    val=0
    for s,pos in new_pos.items():
        price=data[s][idx]
        val += pos["shares"]*price if pos["side"]=="long" else pos["shares"]*(pos["entry_price"]-price)

    used=sum(pos["shares"]*pos["entry_price"] for pos in new_pos.values())

    portfolio["cash"]=portfolio["cash"]-used
    portfolio["positions"]=new_pos
    portfolio["equity"]=portfolio["cash"]+val

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"]=str(datetime.utcnow())
    portfolio["last_equity"]=portfolio["equity"]
    portfolio["strategy"]=regime

    return {"equity":round(portfolio["equity"],2),"strategy":regime}

# =========================
# METRICS
# =========================
def get_metrics():
    eq = portfolio["history"]
    if len(eq)<5:
        return {"message":"not enough data"}

    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak=eq[0]; dd=0
    for e in eq:
        peak=max(peak,e)
        dd=min(dd,(e-peak)/peak)

    pnls=[t["pnl"] for t in portfolio["trades"]]
    wins=[p for p in pnls if p>0]

    return {
        "sharpe":round(sharpe,2),
        "drawdown_pct":round(dd*100,2),
        "trades":len(pnls),
        "win_rate":round(len(wins)/len(pnls)*100,2) if pnls else 0,
        "total_pnl":round(sum(pnls),2)
    }

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html><head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{background:#0f172a;color:white;font-family:Arial}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}
.card{background:#1e293b;padding:15px;border-radius:10px}
</style></head>
<body>

<h1>📊 Institutional Dashboard</h1>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><canvas id="dd"></canvas></div>

<div class="card"><pre id="signals"></pre></div>
<div class="card"><pre id="portfolio"></pre></div>

<div class="card"><pre id="risk"></pre></div>
<div class="card"><pre id="metrics"></pre></div>
</div>

<script>
let ec,dc;

function dd(eq){
 let peak=eq[0];
 return eq.map(e=>{peak=Math.max(peak,e);return (e-peak)/peak*100});
}

async function load(){
 let p=await fetch('/paper/status').then(r=>r.json());
 let s=await fetch('/signals').then(r=>r.json());
 let m=await fetch('/paper/metrics').then(r=>r.json());

 document.getElementById('signals').innerText=JSON.stringify(s,null,2);
 document.getElementById('portfolio').innerText=JSON.stringify(p,null,2);
 document.getElementById('risk').innerText=JSON.stringify({cooldown:p.cooldown,equity:p.equity},null,2);
 document.getElementById('metrics').innerText=JSON.stringify(m,null,2);

 let eq=(p.history&&p.history.length>1)?p.history:[10000,10000];
 let d=dd(eq);

 if(ec) ec.destroy();
 ec=new Chart(document.getElementById('eq'),{type:'line',data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}});

 if(dc) dc.destroy();
 dc=new Chart(document.getElementById('dd'),{type:'line',data:{labels:d.map((_,i)=>i),datasets:[{label:'DD',data:d}]}});

}
load();
setInterval(load,10000);
</script>

</body></html>
""")

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"LIVE SYSTEM"}

@app.route("/signals")
def signals():
    s,r=generate_signals()
    return jsonify({"regime":r,"signals":s})

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
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
