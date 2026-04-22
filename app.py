import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# DATA
# =========================
def get_prices(symbol, period="1y"):
    try:
        df = yf.download(symbol, period=period, interval="1d", progress=False)

        if df is None or df.empty:
            return None

        close = np.array(df["Close"]).reshape(-1)
        close = close[np.isfinite(close)]

        return close.astype(float)

    except:
        return None

# =========================
# SIMPLE TEST STRATEGY
# =========================
def simulate(prices):
    if prices is None or len(prices) < 100:
        return None

    cash = 10000
    position = 0
    equity = []

    for i in range(50, len(prices)):
        ma_fast = np.mean(prices[i-10:i])
        ma_slow = np.mean(prices[i-30:i])
        price = prices[i]

        if ma_fast > ma_slow and position == 0:
            position = cash / price
            cash = 0

        elif ma_fast < ma_slow and position > 0:
            cash = position * price
            position = 0

        equity.append(cash + position * price)

    if not equity:
        return None

    ret = (equity[-1] - 10000) / 10000
    return {"return": float(ret)}

# =========================
# WALKFORWARD (SIMPLIFIED)
# =========================
def walk_forward(symbol="AAPL"):
    prices = get_prices(symbol)

    if prices is None:
        return {"error": "no data"}

    window = 50
    step = 20

    results = []
    i = 0

    while i + window < len(prices):
        segment = prices[i:i+window]
        res = simulate(segment)

        if res:
            results.append(res)

        i += step

    if not results:
        return {"error": "no results"}

    returns = [r["return"] for r in results]

    return {
        "segments": len(results),
        "avg_return_pct": round(np.mean(returns)*100, 2),
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
def walkforward():
    return jsonify(walk_forward())

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
