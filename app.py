import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# UNIVERSE
# =========================
SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META",
    "AMZN","GOOGL","TSLA","AVGO","CRM"
]

# =========================
# DATA
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
# STRATEGY (RELATIVE STRENGTH)
# =========================
def simulate():
    data = get_data()

    if len(data) < 5:
        return {"error": "not enough data"}

    length = min(len(p) for p in data.values())

    cash = 10000
    equity_curve = []

    for i in range(30, length):

        scores = []

        for s, prices in data.items():
            ret = (prices[i] - prices[i-20]) / prices[i-20]
            scores.append((s, ret))

        # rank by strength
        scores.sort(key=lambda x: x[1], reverse=True)

        top = scores[:3]

        # equal weight top 3
        value = 0

        for s, _ in top:
            price = data[s][i]
            value += cash / 3

        cash = value
        equity_curve.append(cash)

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
