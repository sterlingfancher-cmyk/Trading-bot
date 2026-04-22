import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA","AVGO",
    "JPM","BAC","GS","MS",
    "CAT","DE","GE","HON",
    "COST","WMT","HD","MCD",
    "LLY","JNJ","MRK",
    "XOM","CVX",
    "SPY","QQQ","IWM"
]

TARGET_VOL = 0.02
MAX_POSITIONS = 4
MAX_POSITION_RISK = 0.1

def safe_float(x):
    try:
        return float(np.asarray(x).item())
    except:
        return float(x)

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None,
    "last_signals": [],
    "step": 60
}

# ================= DATA =================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False)
            if df is None or df.empty:
                continue
            prices = np.array(df["Close"], dtype=float)
            if len(prices) < 60:
                continue
            data[s] = prices
        except:
            continue
    return data

# ================= VOL =================
def get_vol(p, idx):
    r = np.diff(p[idx-20:idx]) / p[idx-20:idx-1]
    return safe_float(np.std(r)) + 1e-6

# ================= REGIME =================
def get_regime(data):
    spy = data.get("SPY")
    if spy is None:
        return "neutral"

    ma20 = np.mean(spy[-20:])
    ma50 = np.mean(spy[-50:])
    return "bull" if ma20 > ma50 else "bear"

# ================= SIGNALS =================
def generate_signals(data, idx, regime):
    scores = []

    for s,p in data.items():
        try:
            ret = (p[idx] / p[idx-20]) - 1
            vol = get_vol(p, idx)
            score = ret / vol

            if regime == "bear":
                score = -score

            scores.append((s, safe_float(score), vol))
        except:
            continue

    scores = sorted(scores, key=lambda x:x[1], reverse=True)
    top = scores[:MAX_POSITIONS]

    return [{"symbol":s,"vol":vol} for s,_,vol in top]

# ================= EXECUTION =================
def run_paper():
    global portfolio

    try:
        data = load_data()
        if not data:
            return {"error":"no data"}

        lengths = [len(p) for p in data.values()]
        max_len = min(lengths) - 1

        if portfolio["step"] >= max_len:
            portfolio["step"] = 60

        idx = portfolio["step"]
        portfolio["step"] += 1

        regime = get_regime(data)
        signals = generate_signals(data, idx, regime)

        portfolio["last_signals"] = signals
        portfolio["strategy"] = regime

        # mark to market
        equity = portfolio["cash"]
        for s,pos in portfolio["positions"].items():
            if s in data:
                price = safe_float(data[s][idx])
                if pos["side"] == "long":
                    equity += pos["shares"] * price
                else:
                    equity += pos["shares"] * (pos["entry"] - price)

        portfolio["equity"] = safe_float(equity)

        # close removed
        current = set(portfolio["positions"].keys())
        target = set(s["symbol"] for s in signals)

        for s in list(current - target):
            pos = portfolio["positions"][s]
            price = safe_float(data[s][idx])

            pnl = (price - pos["entry"]) * pos["shares"]
            if pos["side"] == "short":
                pnl = (pos["entry"] - price) * pos["shares"]

            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append({"symbol": s, "pnl": round(pnl,2)})

            del portfolio["positions"][s]

        # open new
        for sig in signals:
            s = sig["symbol"]
            price = safe_float(data[s][idx])
            vol = sig["vol"]

            risk_weight = TARGET_VOL / vol
            alloc = portfolio["equity"] * min(risk_weight, MAX_POSITION_RISK)

            shares = alloc / price
            side = "long" if regime == "bull" else "short"

            if s not in portfolio["positions"] and portfolio["cash"] >= alloc:
                portfolio["cash"] -= alloc
                portfolio["positions"][s] = {
                    "shares": shares,
                    "entry": price,
                    "side": side
                }

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())

        return {"equity": round(portfolio["equity"],2), "regime": regime}

    except Exception as e:
        return {"error": str(e)}

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

<h2>📊 Institutional Dashboard</h2>

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

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status":"INSTITUTIONAL SYSTEM LIVE"}

@app.route("/paper/run")
def run():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/paper/metrics")
def metrics():
    eq = portfolio["history"]
    if len(eq) < 5:
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

# ================= START =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
