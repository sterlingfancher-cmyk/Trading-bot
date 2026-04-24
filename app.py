import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

UNIVERSE = [
    "NVDA","AMD","AVGO","MU","LRCX","TER","TSM",
    "ARM","PANW","CRWD","SNOW","PLTR",
    "RKLB","KTOS","COHR","NBIS",
    "META","TSLA","SHOP","NET",
    "IBIT","ETHA","GDLC"
]

BASE_RISK = 0.01
MAX_HEAT = 0.25
STOP_LOSS = 0.05
MAX_POSITIONS = 4
MIN_SCORE = 1.2

portfolio = {
    "cash":10000,
    "equity":10000,
    "peak":10000,
    "positions":{},
    "history":[],
    "trades":[],
    "step":80,
    "last_run":None,
    "regime":None,
    "ai_recommendations":[]
}

def sf(x): return float(np.asarray(x).item())

# ================= DATA =================
def load(symbols):
    data={}
    for s in symbols:
        try:
            df=yf.download(s,period="6mo",progress=False)
            if df.empty: continue
            p=np.array(df["Close"],float)
            if len(p)>80:
                data[s]=p
        except:
            continue
    return data

# ================= REGIME =================
def regime(data):
    spy=data.get("SPY")
    if spy is None:
        return "neutral"

    ma20=np.mean(spy[-20:])
    ma50=np.mean(spy[-50:])

    if ma20>ma50: return "bull"
    elif ma20<ma50: return "bear"
    return "neutral"

# ================= SIGNAL EDGE V2 =================
def signals(data, idx, reg):
    spy = data.get("SPY")
    if spy is None:
        return []

    spy_ret = (spy[idx]/spy[idx-20])-1

    scored=[]

    for s,p in data.items():
        if s in ["SPY","QQQ"]:
            continue

        try:
            price = p[idx]

            # momentum
            ret20 = (p[idx]/p[idx-20])-1
            ret10 = (p[idx]/p[idx-10])-1

            # acceleration
            accel = ret10 - ret20/2

            # relative strength
            rs = ret20 - spy_ret

            # breakout
            high20 = max(p[idx-20:idx])
            breakout = price > high20 * 0.99

            # volatility compression
            vol = np.std(np.diff(p[idx-20:idx])/p[idx-20:idx-1])
            vol_long = np.std(np.diff(p[idx-60:idx])/p[idx-60:idx-1])
            compression = vol < vol_long

            score = rs*2 + accel

            if reg == "bull":
                if rs > 0 and accel > 0 and breakout:
                    if compression:
                        score *= 1.5
                    scored.append((s,score,vol))

            elif reg == "bear":
                if rs < 0 and accel < 0:
                    scored.append((s,abs(score),vol))

            else:
                if abs(rs) > 0.02:
                    scored.append((s,abs(score),vol))

        except:
            continue

    scored = sorted(scored,key=lambda x:x[1],reverse=True)

    # HIGH CONVICTION ONLY
    scored = [s for s in scored if s[1] > MIN_SCORE]

    return scored[:MAX_POSITIONS]

# ================= AI SUPERVISOR =================
def ai_supervisor():
    eq = portfolio["history"]
    trades = portfolio["trades"]

    if len(eq) < 10:
        portfolio["ai_recommendations"] = ["Collecting data..."]
        return

    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak = eq[0]
    dd = 0
    for e in eq:
        peak=max(peak,e)
        dd=min(dd,(e-peak)/peak)

    rec=[]

    if sharpe < 0.5:
        rec.append("⚠️ Weak edge → increase MIN_SCORE or tighten breakout rules")

    if dd < -0.1:
        rec.append("⚠️ Drawdown high → reduce BASE_RISK")

    if sharpe > 2:
        rec.append("✅ Strong performance → consider scaling capital")

    if not rec:
        rec.append("✅ System stable")

    portfolio["ai_recommendations"]=rec

# ================= ENGINE =================
def run_engine():
    global portfolio

    universe = UNIVERSE + ["SPY","QQQ"]
    data = load(universe)

    if not data:
        return {"error":"no data"}

    idx = portfolio["step"]
    portfolio["step"] += 1

    reg = regime(data)
    portfolio["regime"]=reg

    sig = signals(data,idx,reg)

    equity = portfolio["cash"]

    for s,pos in portfolio["positions"].items():
        if s in data:
            price=sf(data[s][idx])
            if pos["side"]=="long":
                equity += pos["shares"]*price
            else:
                equity += pos["shares"]*(pos["entry"]-price)

    portfolio["equity"]=equity
    portfolio["peak"]=max(portfolio["peak"],equity)

    # STOP LOSS
    for s,pos in list(portfolio["positions"].items()):
        price=sf(data[s][idx])
        loss=(price-pos["entry"])/pos["entry"]
        if loss < -STOP_LOSS:
            portfolio["cash"] += pos["shares"]*price
            del portfolio["positions"][s]

    # ROTATE
    current=set(portfolio["positions"].keys())
    target=set(s[0] for s in sig)

    for s in list(current):
        if s not in target:
            pos=portfolio["positions"][s]
            price=sf(data[s][idx])
            portfolio["cash"] += pos["shares"]*price
            del portfolio["positions"][s]

    # ENTRY
    for s,score,vol in sig:
        if s in portfolio["positions"]:
            continue

        price=sf(data[s][idx])
        size = portfolio["equity"]*BASE_RISK/(vol*5)

        if portfolio["cash"] >= size:
            shares=size/price
            portfolio["cash"] -= size
            portfolio["positions"][s]={
                "shares":shares,
                "entry":price,
                "side":"long"
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"]=str(datetime.utcnow())

    ai_supervisor()

    return {
        "equity":round(portfolio["equity"],2),
        "regime":reg,
        "positions":list(portfolio["positions"].keys())
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

<h2>🚀 Signal Edge v2 Dashboard</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><canvas id="dd"></canvas></div>
<div class="card"><pre id="positions"></pre></div>
<div class="card"><pre id="metrics"></pre></div>
<div class="card"><pre id="ai"></pre></div>
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

 document.getElementById('positions').innerText =
  JSON.stringify(p.positions,null,2);

 document.getElementById('metrics').innerText =
  JSON.stringify(m,null,2);

 document.getElementById('ai').innerText =
  JSON.stringify(p.ai_recommendations,null,2);

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
    return {"status":"SIGNAL EDGE V2 LIVE"}

@app.route("/paper/run")
def run_api():
    if request.args.get("key")!=SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/paper/metrics")
def metrics():
    eq=portfolio["history"]
    if len(eq)<10:
        return {"message":"not enough data"}

    r=np.diff(eq)/eq[:-1]
    sharpe=np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak=eq[0]
    dd=0
    for e in eq:
        peak=max(peak,e)
        dd=min(dd,(e-peak)/peak)

    return {
        "sharpe":round(sharpe,2),
        "drawdown_pct":round(dd*100,2),
        "trades":len(portfolio["trades"])
    }

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
