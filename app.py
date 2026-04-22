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
# SIMULATION
# =========================
def simulate():
    data = get_data()

    if len(data) < 5:
        return {"error": "not enough data"}

    length = min(len(p) for p in data.values())

    capital = 10000
    equity_curve = []

    positions = {}  # {symbol: shares}

    for i in range(30, length):

        # --- RANK STOCKS ---
        scores = []
        for s, prices in data.items():
            ret = (prices[i] - prices[i-20]) / prices[i-20]
            scores.append((s, ret))

        scores.sort(key=lambda x: x[1], reverse=True)
        top = [s for s, _ in scores[:3]]

        # --- REBALANCE ---
        positions = {}
        allocation = capital / 3

        for s in top:
            price = data[s][i]
            shares = allocation / price
            positions[s] = shares

        # --- MARK TO MARKET ---
        total_value = 0
        for s, shares in positions.items():
            price = data[s][i]
            total_value += shares * price

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
# WALKFORWARD
# =========================
def walk_forward():
    results = []

    for _ in range(5):
        res = simulate()
        if res:
            results.append(res)

    if not results:
        return {"error": "no results"}

    returns = [r["return"] for r in results]
    dds = [r["drawdown"] for r in results]

    return {
        "runs": len(results),
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
