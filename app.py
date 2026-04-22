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
    "equity": 10000,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None
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
# REGIME
# =========================
def get_market_regime():
    try:
        df = yf.download("SPY", period="3mo", interval="1d", progress=False)
        prices = np.array(df["Close"])

        ma20 = np.mean(prices[-20:])
        ma50 = np.mean(prices[-50:])

        if ma20 > ma50:
            return "bull"
        elif ma20 < ma50:
            return "bear"
        else:
            return "neutral"
    except:
        return "neutral"

# =========================
# STRATEGY 1: MEAN REVERSION
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
            scores.append((s, z, strength))

    if len(scores) < 2:
        return []

    scores.sort(key=lambda x: x[1])
    selected = scores[:3]

    total = sum(x[2] for x in selected)
    n = len(selected)

    return [
        {"symbol": s, "weight": round(0.5*(1/n)+0.5*(strength/total),3)}
        for s,_,strength in selected
    ]

# =========================
# STRATEGY 2: MOMENTUM
# =========================
def momentum(data, idx):
    scores = []

    for s, prices in data.items():
        ret = (prices[idx] / prices[idx-20]) - 1

        vol = get_vol(prices, idx)
        score = ret / vol

        scores.append((s, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    top = scores[:3]

    total = sum(x[1] for x in top)

    return [
        {"symbol": s, "weight": round(score/total,3)}
        for s,score in top
    ]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals():
    data = load_data()
    if len(data) < 5:
        return [], "none"

    idx = min(len(p) for p in data.values()) - 1
    regime = get_market_regime()

    if regime == "bull":
        return momentum(data, idx), "momentum"

    elif regime == "neutral":
        return mean_reversion(data, idx), "mean_reversion"

    else:
        return [], "none"

# =========================
# EXECUTION
# =========================
def run_paper():
    global portfolio

    data = load_data()
    signals, strat = generate_signals()

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

    if not signals:
        portfolio["history"].append(capital)
        portfolio["last_run"] = str(datetime.utcnow())
        portfolio["strategy"] = strat
        return {"message":"no trades"}

    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        price = data[s][idx]
        shares = (capital * sig["weight"]) / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price
        }

    portfolio["positions"] = new_positions

    total = sum(pos["shares"] * data[s][idx] for s, pos in new_positions.items())

    portfolio["equity"] = total
    portfolio["history"].append(total)
    portfolio["last_run"] = str(datetime.utcnow())
    portfolio["strategy"] = strat

    return {"equity": round(total,2), "strategy": strat}

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
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"MULTI-STRATEGY LIVE"}

@app.route("/signals")
def signals():
    sigs, strat = generate_signals()
    return jsonify({"strategy": strat, "signals": sigs})

@app.route("/paper/run")
def run():
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

# =========================
# START
# =========================
start_scheduler()

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=PORT)
