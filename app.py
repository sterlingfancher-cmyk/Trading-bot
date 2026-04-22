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
    "JPM","BAC","GS","MS","C","WFC",
    "CAT","DE","GE","BA","HON","UPS","FDX",
    "COST","WMT","HD","MCD",
    "LLY","JNJ","MRK","ABBV",
    "XOM","CVX",
    "SPY","QQQ","IWM"
]

MAX_POSITION_RISK = 0.05
MAX_POSITION_SIZE = 0.4

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
    "last_equity": 10000.0,
    "last_signals": [],
    "step": 60
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

            if len(prices) < 60:
                continue

            data[s] = prices
        except:
            continue
    return data

# =========================
# STRATEGIES
# =========================
def momentum(data, idx):
    scores = []
    for s,p in data.items():
        try:
            ret = (p[idx]/p[idx-20])-1
            scores.append((s, float(ret)))
        except:
            continue
    return sorted(scores, key=lambda x:x[1], reverse=True)

def mean_reversion(data, idx):
    scores = []
    for s,p in data.items():
        try:
            std = np.std(p[idx-20:idx])
            if std == 0:
                continue
            z = (p[idx]-np.mean(p[idx-20:idx]))/std
            if z < -0.3:
                scores.append((s, float(abs(z))))
        except:
            continue
    return sorted(scores, key=lambda x:x[1], reverse=True)

# =========================
# SIGNAL ENGINE (FIXED)
# =========================
def generate_signals(data, idx):
    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}

    for s,v in mom[:5]:
        combined[s] = combined.get(s,0)+v

    for s,v in mr[:5]:
        combined[s] = combined.get(s,0)+v

    # 🔥 ALWAYS TRADE (fallback)
    if not combined:
        fallback = list(data.keys())[:3]
        return [
            {"symbol": s, "weight": 1/3, "side": "long"}
            for s in fallback
        ], "fallback"

    top = sorted(combined.items(), key=lambda x:x[1], reverse=True)[:3]
    total = sum(x[1] for x in top) or 1

    return [
        {"symbol": s, "weight": float(v/total), "side": "long"}
        for s,v in top
    ], "active"

# =========================
# EXECUTION (TIME PROGRESSION)
# =========================
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

        signals, regime = generate_signals(data, idx)
        portfolio["last_signals"] = signals

        # CLOSE OLD POSITIONS
        for s,pos in portfolio["positions"].items():
            if s in data:
                price = float(data[s][idx])
                pnl = (price - pos["entry_price"]) * pos["shares"]
                portfolio["trades"].append({
                    "symbol": s,
                    "entry": pos["entry_price"],
                    "exit": price,
                    "pnl": round(pnl,2)
                })

        portfolio["cash"] = float(portfolio["equity"])
        portfolio["positions"] = {}

        new_pos = {}

        for sig in signals:
            s = sig["symbol"]
            price = float(data[s][idx])

            alloc = portfolio["cash"] * sig["weight"]
            alloc = min(alloc, portfolio["equity"] * MAX_POSITION_RISK)

            shares = float(alloc / price)

            new_pos[s] = {
                "shares": shares,
                "entry_price": price
            }

        value = 0.0
        for s,pos in new_pos.items():
            price = float(data[s][idx])
            value += pos["shares"] * price

        used = sum(pos["shares"] * pos["entry_price"] for pos in new_pos.values())

        portfolio["cash"] -= used
        portfolio["positions"] = new_pos
        portfolio["equity"] = float(portfolio["cash"] + value)

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())
        portfolio["last_equity"] = portfolio["equity"]
        portfolio["strategy"] = regime

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
    return jsonify({
        "strategy": portfolio.get("strategy","init"),
        "signals": portfolio.get("last_signals",[])
    })

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
    sharpe = float(np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252))

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

# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
