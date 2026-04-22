import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# DATA
# =========================
def get_prices(symbol="AAPL"):
    df = yf.download(symbol, period="1y", interval="1d", progress=False)

    if df is None or df.empty:
        return None

    prices = np.array(df["Close"]).reshape(-1)
    prices = prices[np.isfinite(prices)]

    return prices.astype(float)

# =========================
# BREAKOUT STRATEGY
# =========================
def simulate(prices):
    cash = 10000
    position = 0
    equity_curve = []

    for i in range(30, len(prices)):
        price = prices[i]

        # 🔥 breakout level
        recent_high = np.max(prices[i-20:i])

        # 🔥 volatility expansion
        returns = np.diff(prices[i-20:i]) / prices[i-20:i-1]
        vol = np.std(returns)

        # ENTRY: breakout + expansion
        if price > recent_high and vol > 0.01:
            if position == 0:
                position = cash / price
                cash = 0

        # EXIT: momentum loss
        elif price < np.mean(prices[i-10:i]):
            if position > 0:
                cash = position * price
                position = 0

        equity = cash + position * price
        equity_curve.append(equity)

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
    prices = get_prices()

    if prices is None or len(prices) < 100:
        return {"error": "not enough data"}

    window = 60
    step = 20

    results = []
    i = 0

    while i + window < len(prices):
        segment = prices[i:i+window]
        res = simulate(segment)

        if res:
            results.append(res)

        i += step

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
def walkforward():
    return jsonify(walk_forward())

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
