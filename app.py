# app.py
import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
import random
import traceback

app = Flask(__name__)

# ================= CONFIG =================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
SIMULATION_MODE = True

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX",
    "META","AMZN","GOOGL","MSFT",
    "SNOW","PLTR","CRWD","PANW",
    "TSLA","SHOP","ROKU",
    "RKLB","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

MAX_POSITIONS = 4
BASE_RISK = 0.02
TRAIL_STOP = 0.02
DRAWDOWN_LIMIT = -0.06

# ================= STATE =================
portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "regime": "neutral",
    "errors": []
}

# ================= SAFE SCALAR =================
def sf(x):
    try:
        return float(np.asarray(x).flatten()[-1])
    except:
        return 0.0

# ================= DATA =================
def synthetic(n=60):
    base = 100
    steps = np.random.normal(0, 0.002, n)
    p = [base]
    for s in steps:
        p.append(p[-1]*(1+s))
    return np.array(p[1:])

def load_data(symbols):
    data = {}
    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty or len(df) < 25:
                closes = synthetic()
                lows = closes * 0.999
            else:
                closes = df["Close"].dropna().values
                lows = df["Low"].dropna().values

            if SIMULATION_MODE:
                closes = closes * (1 + np.random.normal(0,0.002,len(closes)))

            data[s] = {"close": closes, "low": lows}

        except Exception as e:
            portfolio["errors"].append(str(e))
            closes = synthetic()
            lows = closes * 0.999
            data[s] = {"close": closes, "low": lows}

    return data

# ================= REGIME =================
def regime(data):
    try:
        spy = data.get("SPY")
        if not spy: return "neutral"
        p = spy["close"]
        if len(p) < 20: return "neutral"
        return "bull" if p[-1] > np.mean(p[-20:]) else "bear"
    except:
        return "neutral"

# ================= SIGNAL =================
def signals(data):
    ranked = []
    for s,d in data.items():
        try:
            p = d["close"]
            if len(p)<20: continue

            r = (sf(p[-1])/sf(p[-5]))-1
            b = (sf(p[-1])-np.max(p[-20:]))/np.max(p[-20:])
            v = np.std(np.diff(p[-20:]))+1e-6

            score = r+b+random.uniform(0,0.01)
            ranked.append((s,score,v))
        except:
            continue

    return sorted(ranked,key=lambda x:x[1],reverse=True)

# ================= ENGINE =================
def run_engine():
    global portfolio
    try:
        data = load_data(UNIVERSE+["SPY"])
        sig = signals(data)
        reg = regime(data)
        portfolio["regime"]=reg

        # ===== EQUITY =====
        eq = portfolio["cash"]
        for s,pos in portfolio["positions"].items():
            if s in data:
                eq += pos["shares"]*sf(data[s]["close"][-1])

        portfolio["equity"]=eq
        portfolio["peak"]=max(portfolio["peak"],eq)

        # ===== DRAWDOWN GUARD =====
        dd = (eq-portfolio["peak"])/portfolio["peak"]
        if dd < DRAWDOWN_LIMIT:
            return {"status":"PAUSED - DRAWDOWN"}

        # ===== STOPS =====
        for s,pos in list(portfolio["positions"].items()):
            price = sf(data[s]["close"][-1])
            pos["peak"]=max(pos.get("peak",pos["entry"]),price)

            if (price-pos["peak"])/pos["peak"] < -TRAIL_STOP:
                portfolio["cash"] += pos["shares"]*price
                portfolio["trades"].append((s,"exit"))
                del portfolio["positions"][s]

        # ===== ENTRY =====
        for s,score,vol in sig:
            if s in portfolio["positions"]: continue
            if len(portfolio["positions"])>=MAX_POSITIONS: break
            if reg=="bear" and score>0: continue

            price = sf(data[s]["close"][-1])
            risk = portfolio["equity"]*BASE_RISK
            size = risk/(vol*price+1e-6)

            if portfolio["cash"]>=size:
                shares = size/price
                portfolio["cash"]-=size
                portfolio["positions"][s]={
                    "shares":shares,
                    "entry":price,
                    "peak":price
                }

        portfolio["history"].append(eq)

        return {
            "equity":round(eq,2),
            "positions":list(portfolio["positions"].keys()),
            "regime":reg
        }

    except Exception as e:
        return {"error":str(e),"trace":traceback.format_exc()}

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<body style="background:#0f172a;color:white">
<h2>Stable System Dashboard</h2>
<canvas id="c"></canvas>
<pre id="d"></pre>
<script>
async function r(){
 let p=await fetch('/paper/status').then(r=>r.json());
 document.getElementById('d').innerText=JSON.stringify(p,null,2);
 let eq=p.history.length>1?p.history:[10000,10000];
 new Chart(document.getElementById('c'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{data:eq}]}
 });
}
r(); setInterval(r,3000);
</script>
</body>
</html>
""")

# ================= ROUTES =================
@app.route("/")
def home(): return {"status":"STABLE SYSTEM LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key")!=SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status(): return jsonify(portfolio)

# ================= START =================
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
