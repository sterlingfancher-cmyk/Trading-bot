import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

CORE = [
    "NVDA","AMD","AVGO","MU","LRCX","TER","TSM",
    "GEV","HWM","CAT","BWXT",
    "RKLB","KTOS","PLTR","COHR","NBIS","IREN",
    "AMZN","MSFT","GOOGL"
]

CRYPTO = ["IBIT","ETHA","GDLC"]

EXPANSION = [
    "SMCI","CRWD","PANW","ZS","NET",
    "TSLA","META","SHOP","SNOW",
    "XOM","CVX","LLY"
]

BASE_RISK = 0.01
MAX_HEAT = 0.20
STOP_LOSS = 0.05
MAX_POSITIONS = 3

portfolio = {
    "cash":10000,
    "equity":10000,
    "peak":10000,
    "positions":{},
    "history":[],
    "trades":[],
    "step":80,
    "universe":[],
    "last_run":None,
    "regime":None,
    "ai_recommendations":[]
}

def sf(x): return float(np.asarray(x).item())

# ================= AI SUPERVISOR =================
def ai_supervisor():
    eq = portfolio["history"]
    trades = portfolio["trades"]

    if len(eq) < 10:
        return ["Collecting data..."]

    rec = []

    # returns
    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    # drawdown
    peak = eq[0]
    dd = 0
    for e in eq:
        peak = max(peak,e)
        dd = min(dd,(e-peak)/peak)

    # win rate
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    win_rate = len(wins)/len(pnls) if pnls else 0

    # ===== DIAGNOSTICS =====
    if sharpe < 0.5:
        rec.append("⚠️ Low Sharpe → tighten signal filter or reduce trades")

    if dd < -0.08:
        rec.append("⚠️ Drawdown high → reduce BASE_RISK or MAX_HEAT")

    if win_rate < 0.45 and len(pnls) > 10:
        rec.append("⚠️ Low win rate → signals too loose")

    if len(pnls) > 50 and sharpe < 1:
        rec.append("⚠️ Overtrading detected → increase MIN_SCORE")

    if sharpe > 2 and dd > -0.03:
        rec.append("✅ Strong system → consider increasing capital allocation")

    if not rec:
        rec.append("✅ System stable")

    portfolio["ai_recommendations"] = rec
    return rec

# ================= UNIVERSE =================
def build_universe():
    pool = CORE + CRYPTO + EXPANSION
    scores=[]

    for s in pool:
        try:
            df=yf.download(s,period="3mo",progress=False)
            if df.empty: continue

            p=np.array(df["Close"],float)
            ret=(p[-1]/p[-20])-1
            vol=np.std(np.diff(p[-20:])/p[-20:-1])
            score=ret/(vol+1e-6)

            scores.append((s,score))
        except:
            continue

    scores=sorted(scores,key=lambda x:x[1],reverse=True)
    selected=[s for s,_ in scores[:20]]

    portfolio["universe"]=selected
    return selected

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

    if ma20>ma50*1.01:
        return "bull"
    elif ma20<ma50*0.99:
        return "bear"
    return "neutral"

# ================= SIGNAL =================
def signals(data, idx, reg):
    raw=[]

    for s,p in data.items():
        try:
            price=p[idx]
            ma50=np.mean(p[idx-50:idx])
            ret=(p[idx]/p[idx-20])-1
            vol=np.std(np.diff(p[idx-20:idx])/p[idx-20:idx-1])+1e-6

            score=ret/vol

            if reg=="bull" and price>ma50 and ret>0.02:
                raw.append((s,score,vol))
            elif reg=="bear" and price<ma50 and ret<-0.02:
                raw.append((s,-score,vol))
            else:
                mean=np.mean(p[idx-20:idx])
                std=np.std(p[idx-20:idx])+1e-6
                z=(price-mean)/std
                if abs(z)>1:
                    raw.append((s,abs(z),vol))

        except:
            continue

    raw=sorted(raw,key=lambda x:x[1],reverse=True)

    if not raw:
        syms=list(data.keys())
        np.random.shuffle(syms)
        return [(s,0.5,0.02) for s in syms[:MAX_POSITIONS]]

    return raw[:MAX_POSITIONS]

# ================= EXECUTION =================
def run_engine():
    global portfolio

    universe=build_universe()+["SPY","QQQ"]
    data=load(universe)

    if not data:
        return {"error":"no data"}

    idx=portfolio["step"]
    portfolio["step"]+=1

    reg=regime(data)
    portfolio["regime"]=reg

    sig=signals(data,idx,reg)

    equity=portfolio["cash"]

    for s,pos in portfolio["positions"].items():
        if s in data:
            price=sf(data[s][idx])
            if pos["side"]=="long":
                equity+=pos["shares"]*price
            else:
                pnl=(pos["entry"]-price)*pos["shares"]
                equity+=pos["shares"]*pos["entry"]+pnl

    portfolio["equity"]=equity
    portfolio["peak"]=max(portfolio["peak"],equity)

    total_exposure=sum(
        pos["shares"]*data[s][idx]
        for s,pos in portfolio["positions"].items()
        if s in data
    )

    max_allowed=portfolio["equity"]*MAX_HEAT

    # STOP LOSS
    for s,pos in list(portfolio["positions"].items()):
        price=sf(data[s][idx])
        loss=(price-pos["entry"])/pos["entry"]
        if pos["side"]=="short":
            loss=(pos["entry"]-price)/pos["entry"]

        if loss<-STOP_LOSS:
            portfolio["cash"]+=pos["shares"]*price
            portfolio["trades"].append({"symbol":s,"pnl":round(loss*100,2)})
            del portfolio["positions"][s]

    # ROTATION
    current=set(portfolio["positions"].keys())
    target=set(s[0] for s in sig)

    for s in list(current):
        if s not in target:
            pos=portfolio["positions"][s]
            price=sf(data[s][idx])

            pnl=(price-pos["entry"])*pos["shares"]
            if pos["side"]=="short":
                pnl=(pos["entry"]-price)*pos["shares"]

            portfolio["cash"]+=pos["shares"]*price
            portfolio["trades"].append({"symbol":s,"pnl":round(pnl,2)})
            del portfolio["positions"][s]

    # ENTRY
    for s,score,vol in sig:
        if s in portfolio["positions"]:
            continue

        price=sf(data[s][idx])
        size=portfolio["equity"]*BASE_RISK/(vol*5)

        if total_exposure+size>max_allowed:
            continue

        shares=size/price
        side="long" if reg!="bear" else "short"

        if portfolio["cash"]>=size:
            portfolio["cash"]-=size
            portfolio["positions"][s]={
                "shares":shares,
                "entry":price,
                "side":side
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"]=str(datetime.utcnow())

    # RUN AI SUPERVISOR
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

<h2>🤖 AI Supervised Trading Dashboard</h2>

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
    return {"status":"AI SUPERVISED SYSTEM LIVE"}

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
