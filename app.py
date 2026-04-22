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
# LOAD DATA
# =========================
def get_data():
    data = {}

    for s in SYMBOLS:
        df = yf.download(s, period="1y", interval="1d", progress=False)

        if df is None or df.empty:
            continue

        prices = np.array(df["Close"]).reshape(-1)
        prices = prices[np.isfinite(prices)]

        if len(prices) > 100:
            data[s] = prices.astype(float)

    return data

# =========================
# SIMULATION (WITH COSTS)
# =========================
def simulate_segment(data, start, end):
    capital = 10000
    positions = {}
    equity_curve = []

    holding_period = 5
    rebalance_counter = 0

    cost_rate = 0.001  # 0.1% per rebalance

    for i in range(start, end):
        rebalance_counter += 1

        if rebalance_counter >= holding_period:

            scores = []
            for s, prices in data.items():
                if i < 20:
                    continue

                ret = (prices[i] - prices[i-20]) / prices[i-20]
                scores.append((s, ret))

            scores.sort(key=lambda x: x[1], reverse=True)
            top = [s for s, _ in scores[:3]]

            positions = {}
            allocation = capital / 3

            for s in top:
                price = data[s][i]
                shares = allocation / price
                positions[s] = shares

            # 🔥 APPLY COST
            capital *= (1 - cost_rate)

            rebalance_counter = 0

        total_value = 0
        for s, shares in positions.items():
            price = data[s][i]
            total_value += shares * price

        if positions:
            capital = total_value

        equity_curve.append(capital)

    if len(equity_curve) < 5:
        return None

    ret = (equity_curve[-1] - 10000) / 10000

    peak = equity_curve[0]
    dd = 0

    for e in equity_curve:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    return {"return": ret, "drawdown": dd}

# =========================
# TRUE WALK-FORWARD
# =========================
def walk_forward():
    data = get_data()

    if len(data) < 5:
        return {"error": "not enough data"}

    length = min(len(p) for p in data.values())

    train = 60
    test = 20

    results = []
    i = 30

    while i + train + test < length:

        start = i + train
        end = start + test

        res = simulate_segment(data, start, end)

        if res:
            results.append(res)

        i += test

    if not results:
        return {"error": "no results"}

    returns = [r["return"] for r in results]
    dds = [r["drawdown"] for r in results]

    return {
        "segments": len(results),
        "avg_return_pct": round(np.mean(returns)*100, 2),
        "worst_drawdown_pct": round(min(dds)*100, 2),
        "consistency_pct": round(
            (sum(1 for r in returns if r > 0)/len(returns))*100, 2
        )
    }

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "live"}

@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/walkforward")
def wf():
    return jsonify(walk_forward())

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
