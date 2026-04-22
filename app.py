import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META",
    "AMZN","GOOGL","TSLA","AVGO","CRM"
]

# =========================
# GLOBAL STATE (PAPER TRADING)
# =========================
portfolio = {
    "cash": 10000,
    "positions": {},
    "equity": 10000,
    "history": []
}

# =========================
# LOAD DATA
# =========================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="1y", interval="1d", progress=False)
            if df is None or df.empty:
                continue

            prices = np.array(df["Close"]).reshape(-1)
            prices = prices[np.isfinite(prices)]

            if len(prices) > 100:
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
# SIGNALS
# =========================
def generate_signals():
    data = load_data()

    if len(data) < 5:
        return []

    idx = min(len(p) for p in data.values()) - 1

    scores = []

    for s, prices in data.items():
        if idx < 20:
            continue

        window = prices[idx-20:idx]
        mean = np.mean(window)
        std = np.std(window)

        if std == 0:
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
        w = 0.5*(1/n) + 0.5*(strength/total)
        signals.append((s, w))

    return signals

# =========================
# PAPER TRADING EXECUTION
# =========================
def run_paper():
    global portfolio

    data = load_data()
    signals = generate_signals()

    if not signals:
        return {"message": "no trades"}

    idx = min(len(p) for p in data.values()) - 1

    # SELL everything (rebalance)
    portfolio["positions"] = {}

    capital = portfolio["equity"]

    new_positions = {}

    for s, weight in signals:
        price = data[s][idx]
        allocation = capital * weight
        shares = allocation / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price
        }

    portfolio["positions"] = new_positions

    # update equity
    total = 0
    for s, pos in new_positions.items():
        price = data[s][idx]
        total += pos["shares"] * price

    portfolio["equity"] = total

    portfolio["history"].append({
        "equity": round(total,2),
        "positions": list(new_positions.keys())
    })

    return {
        "executed": True,
        "equity": round(total,2),
        "positions": new_positions
    }

# =========================
# STATUS
# =========================
def get_status():
    return portfolio

# =========================
# BACKTEST
# =========================
def walk_forward():
    data = load_data()

    length = min(len(p) for p in data.values())

    train = 60
    test = 20

    results = []
    i = 30

    while i + train + test < length:
        start = i + train
        end = start + test

        capital = 10000

        for j in range(start, end):
            # simplified reuse
            pass

        results.append(capital)

        i += test

    return {"note": "use prior validated result"}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "paper trading system live"}

@app.route("/signals")
def signals():
    return jsonify({"signals": generate_signals()})

@app.route("/paper/run")
def paper_run():
    return jsonify(run_paper())

@app.route("/paper/status")
def paper_status():
    return jsonify(get_status())

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
