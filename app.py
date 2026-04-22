import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

# ===== CORE + CRYPTO =====
CORE = [
    "NVDA","AMD","AVGO","MU","LRCX","TER","TSM",
    "GEV","HWM","CAT","BWXT",
    "RKLB","KTOS",
    "PLTR","COHR","NBIS","IREN",
    "AMZN","MSFT","GOOGL"
]

CRYPTO = ["IBIT","ETHA","GDLC"]

EXPANSION = [
    "SMCI","CRWD","PANW","ZS","NET",
    "TSLA","META","SHOP","SNOW",
    "XOM","CVX","LLY"
]

BASE_RISK = 0.012
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
    "universe":[]
}

# ================= UTIL =================
def sf(x): return float(np.asarray(x).item())

# ================= UNIVERSE =================
def build_universe():
    pool = CORE + CRYPTO + EXPANSION
    scores = []

    for s in pool:
        try:
            df = yf.download(s, period="3mo", progress=False)
            if df.empty: continue
            p = np.array(df["Close"], float)
            ret = (p[-1]/p[-20])-1
            vol = np.std(np.diff(p[-20:])/p[-20:-1])
            scores.append((s, ret/(vol+1e-6)))
        except: continue

    scores = sorted(scores, key=lambda x:x[1], reverse=True)
    selected = [s for s,_ in scores[:20]]
    portfolio["universe"] = selected
    return selected

# ================= DATA =================
def load(symbols):
    data={}
    for s in symbols:
        try:
            df=yf.download(s,period="6mo",progress=False)
            if df.empty: continue
            p=np.array(df["Close"],float)
            if len(p)>80: data[s]=p
        except: continue
    return data

# ================= REGIME =================
def regime(data):
    spy=data.get("SPY")
    if spy is None: return "neutral"
    ma20=np.mean(spy[-20:])
    ma50=np.mean(spy[-50:])
    if ma20>ma50*1.01: return "bull"
    if ma20<ma50*0.99: return "bear"
    return "neutral"

# ================= VOL TARGET =================
def portfolio_vol(hist):
    if len(hist)<10: return 0.01
    r=np.diff(hist)/hist[:-1]
    return np.std(r)

# ================= CAPITAL SCALING =================
def capital_scale():
    dd=(portfolio["equity"]-portfolio["peak"])/portfolio["peak"]
    if dd<-0.05: return 0.5
    if dd<-0.02: return 0.75
    return 1.2

# ================= SIGNAL =================
def signals(data,idx,reg):
    raw=[]
    for s,p in data.items():
        try:
            price=p[idx]
            ma50=np.mean(p[idx-50:idx])
            ret=(p[idx]/p[idx-20])-1
            vol=np.std(np.diff(p[idx-20:idx])/p[idx-20:idx-1])
            score=ret/(vol+1e-6)

            if reg=="bull" and price>ma50 and ret>0.03:
                raw.append((s,score,vol))
            elif reg=="bear" and price<ma50 and ret<-0.03:
                raw.append((s,-score,vol))
        except: continue

    raw=sorted(raw,key=lambda x:x[1],reverse=True)
    return raw[:MAX_POSITIONS]

# ================= EXECUTION =================
def run():
    global portfolio

    universe=build_universe()+["SPY","QQQ"]
    data=load(universe)
    if not data: return {"error":"no data"}

    idx=portfolio["step"]
    portfolio["step"]+=1

    reg=regime(data)
    sig=signals(data,idx,reg)

    # ===== MARK TO MARKET =====
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

    # ===== RISK ON/OFF =====
    vol=portfolio_vol(portfolio["history"])
    risk_multiplier=1.0
    if vol>0.02: risk_multiplier=0.5
    elif reg=="bear": risk_multiplier=0.6

    scale=capital_scale()

    total_exposure=sum(
        pos["shares"]*data[s][idx]
        for s,pos in portfolio["positions"].items()
        if s in data
    )

    max_allowed=portfolio["equity"]*MAX_HEAT*risk_multiplier

    # ===== STOP LOSS =====
    for s,pos in list(portfolio["positions"].items()):
        price=sf(data[s][idx])
        loss=(price-pos["entry"])/pos["entry"]
        if pos["side"]=="short":
            loss=(pos["entry"]-price)/pos["entry"]

        if loss<-STOP_LOSS:
            portfolio["cash"]+=pos["shares"]*price
            del portfolio["positions"][s]

    # ===== ENTRY =====
    for s,score,vol in sig:
        price=sf(data[s][idx])

        size=portfolio["equity"]*BASE_RISK*scale*risk_multiplier/(vol*5)

        if total_exposure+size>max_allowed:
            continue

        shares=size/price
        side="long" if reg=="bull" else "short"

        if portfolio["cash"]>=size:
            portfolio["cash"]-=size
            portfolio["positions"][s]={
                "shares":shares,
                "entry":price,
                "side":side
            }

    portfolio["history"].append(portfolio["equity"])
    portfolio["last_run"]=str(datetime.utcnow())

    return {
        "equity":round(portfolio["equity"],2),
        "regime":reg,
        "volatility":round(vol,4),
        "risk_multiplier":risk_multiplier
    }

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status":"FINAL INSTITUTIONAL SYSTEM LIVE"}

@app.route("/paper/run")
def run_api():
    if request.args.get("key")!=SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/paper/metrics")
def metrics():
    eq=portfolio["history"]
    if len(eq)<10: return {"message":"not enough data"}

    r=np.diff(eq)/eq[:-1]
    sharpe=np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak=eq[0]
    dd=0
    for e in eq:
        peak=max(peak,e)
        dd=min(dd,(e-peak)/peak)

    return {
        "sharpe":round(sharpe,2),
        "drawdown_pct":round(dd*100,2)
    }

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
