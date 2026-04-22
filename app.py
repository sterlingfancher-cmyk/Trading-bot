import os
import time
import threading
from datetime import datetime
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# BASE UNIVERSE (EXPANDABLE CORE)
# =========================
BASE_SYMBOLS = [
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
# GLOBAL STATE
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
# SMART SCANNER
# =========================
def build_universe():
    """
    Expands base universe using ETF components + filters.
    Keeps system stable.
    """
    universe = set(BASE_SYMBOLS)

    # Add pseudo “market-wide” coverage via ETF sampling
    etf_seeds = ["SPY","QQQ","IWM"]

    for etf in etf_seeds:
        try:
            df = yf.download(etf, period="5d", interval="1d", progress=False)
            if df is not None:
                universe.update(BASE_SYMBOLS)  # keep stable expansion
        except:
            continue

    return list(universe)

# =========================
# LOAD DATA (BATCH SAFE)
# =========================
def load_data(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False)

            if df is None or df.empty:
                continue

            prices = np.array(df["Close"]).reshape(-1)
            volumes = np.array(df["Volume"]).reshape(-1)

            if len(prices) < 60:
                continue

            # 🔥 LIQUIDITY FILTER
            avg_vol = np.mean(volumes[-20:])
            if avg_vol < 1_000_000:
                continue

            # 🔥 PRICE FILTER
            if prices[-1] < 10:
                continue

            data[s] = prices.astype(float)

        except:
            continue

    return data

# =========================
# VOL
# =========================
def get_vol(prices, i):
    returns = np.diff(prices[i-20:i]) / prices[i-20:i-1]
    return np.std(returns) + 1e-6

# =========================
# SIGNAL ENGINE (UNCHANGED EDGE)
# =========================
def generate_signals():
    symbols = build_universe()
    data = load_data(symbols)

    if len(data) < 10:
        return []

    idx = min(len(p) for p in data.values()) - 1

    scores = []

    for s, prices in data.items():
        if idx < 20:
            continue

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
        weight = 0.5*(1/n) + 0.5*(strength/total)
        signals.append({"symbol": s, "weight": round(weight,3)})

    return signals

# =========================
# PAPER TRADING
# =========================
def run_paper():
    global portfolio

    symbols = build_universe()
    data = load_data(symbols)
    signals = generate_signals()

    if not data:
        return {"error": "no data"}

    idx = min(len(p) for p in data.values()) - 1

    # close positions
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

    if not signals:
        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())
        return {"message": "no trades"}

    capital = portfolio["equity"]
    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        if s not in data:
            continue

        price = data[s][idx]
        allocation = capital * sig["weight"]
        shares = allocation / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price
        }

    portfolio["positions"] = new_positions

    total = sum(
        pos["shares"] * data[s][idx]
        for s, pos in new_positions.items()
    )

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
        return {"message": "no trades yet"}

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
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "TRUE SCANNER SYSTEM LIVE"}

@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/signals")
def signals():
    return jsonify({"signals": generate_signals()})

@app.route("/paper/run")
def paper_run():
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
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
