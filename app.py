import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# =========================
# SECURITY
# =========================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

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
    "cash": 10000.0,
    "equity": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None,
    "cooldown": 0,
    "last_equity": 10000.0,
    "last_signals": []
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

            prices = np.array(df["Close"], dtype=float)
            volumes = np.array(df["Volume"], dtype=float)

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
    try:
        r = np.diff(prices[i-20:i]) / prices[i-20:i-1]
        return float(np.std(r)) + 1e-6
    except:
        return 1e-6

# =========================
# REGIME
# =========================
def get_regime():
    try:
        df = yf.download("SPY", period="3mo", progress=False)
        p = np.array(df["Close"], dtype=float)

        if len(p) < 50:
            return "neutral", 0.5

        ma20 = float(np.mean(p[-20:]))
        ma50 = float(np.mean(p[-50:]))
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
        try:
            ret = (p[idx]/p[idx-20])-1
            vol = get_vol(p, idx)
            scores.append((s, float(ret/vol)))
        except:
            continue
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def mean_reversion(data, idx):
    scores = []
    for s,p in data.items():
        try:
            std = np.std(p[idx-20:idx])
            if std == 0:
                continue
            z = (p[idx]-np.mean(p[idx-20:idx]))/std
            if z < -0.7:
                scores.append((s, float(abs(z))))
        except:
            continue
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def short_strategy(data, idx):
    scores = []
    for s,p in data.items():
        try:
            ret = (p[idx]/p[idx-20])-1
            scores.append((s, float(ret)))
        except:
            continue
    return sorted(scores, key=lambda x:x[1])[:3]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals_with_data(data):
    if not data or len(data) < 5:
        return [], "no_data"

    lengths = [len(p) for p in data.values() if len(p) > 50]
    if not lengths:
        return [], "no_data"

    idx = min(lengths) - 1
    regime, w = get_regime()

    if regime == "bear":
        shorts = short_strategy(data, idx)
        total = sum(abs(x[1]) for x in shorts) or 1
        return [{"symbol":s,"weight":abs(v)/total,"side":"short"} for s,v in shorts], "bear_short"

    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}
    for s,v in mom:
        combined[s] = combined.get(s,0)+v*w
    for s,v in mr:
        combined[s] = combined.get(s,0)+v*(1-w)

    if not combined:
        return [], regime

    top = sorted(combined.items(), key=lambda x:x[1], reverse=True)[:3]
    total = sum(x[1] for x in top) or 1

    return [{"symbol":s,"weight":float(v/total),"side":"long"} for s,v in top], regime

# =========================
# RISK
# =========================
def risk_check():
    eq = float(portfolio["equity"])
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
# EXECUTION (FIXED)
# =========================
def run_paper():
    global portfolio

    try:
        if risk_check() != "OK":
            portfolio["history"].append(portfolio["equity"])
            return {"status":"risk_pause"}

        data = load_data()
        if not data:
            return {"error":"no market data"}

        signals, regime = generate_signals_with_data(data)
        portfolio["last_signals"] = signals

        lengths = [len(p) for p in data.values() if len(p) > 50]
        if not lengths:
            return {"error":"insufficient data"}

        idx = min(lengths) - 1

        # log trades
        for s,pos in portfolio["positions"].items():
            if s in data:
                price = float(data[s][idx])
                pnl = (price-pos["entry_price"])*pos["shares"] if pos["side"]=="long" else (pos["entry_price"]-price)*pos["shares"]
                portfolio["trades"].append({
                    "symbol":s,
                    "side":pos["side"],
                    "entry":pos["entry_price"],
                    "exit":price,
                    "pnl":round(float(pnl),2)
                })

        portfolio["cash"]=float(portfolio["equity"])
        portfolio["positions"]={}

        new_pos={}
        for sig in signals:
            s=sig["symbol"]
            if s not in data:
                continue

            price=float(data[s][idx])

            alloc = portfolio["cash"] * min(sig["weight"], MAX_POSITION_SIZE)
            alloc = min(alloc, portfolio["equity"]*MAX_POSITION_RISK)

            shares=float(alloc/price)
            new_pos[s]={"shares":shares,"entry_price":price,"side":sig["side"]}

        val=0.0
        for s,pos in new_pos.items():
            price=float(data[s][idx])
            val += pos["shares"]*price if pos["side"]=="long" else pos["shares"]*(pos["entry_price"]-price)

        used=sum(pos["shares"]*pos["entry_price"] for pos in new_pos.values())

        portfolio["cash"]=float(portfolio["cash"]-used)
        portfolio["positions"]=new_pos
        portfolio["equity"]=float(portfolio["cash"]+val)

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"]=str(datetime.utcnow())
        portfolio["last_equity"]=portfolio["equity"]
        portfolio["strategy"]=regime

        return {"equity": round(portfolio["equity"],2), "strategy": regime}

    except Exception as e:
        return {"error": str(e)}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"LIVE SYSTEM"}

@app.route("/signals")
def signals():
    if portfolio["last_signals"]:
        return jsonify({
            "regime": portfolio["strategy"],
            "signals": portfolio["last_signals"]
        })
    return jsonify({"regime":"init","signals":[]})

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
    if len(eq)<5:
        return {"message":"not enough data"}

    r = np.diff(eq)/eq[:-1]
    sharpe = float(np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252))

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
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
