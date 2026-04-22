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
        return df["Close"].dropna().values.astype(float)
    except Exception as e:
        return None

# =========================
# STRATEGY
# =========================
def simulate(prices, short_window=10, long_window=20):
    if prices is None or len(prices) < long_window:
        return None

    cash = 10000.0
    position = 0.0
    equity_curve = []

    for i in range(long_window, len(prices)):
        short_ma = np.mean(prices[i - short_window:i])
        long_ma = np.mean(prices[i - long_window:i])
        price = prices[i]

        if short_ma > long_ma and position == 0:
            position = cash / price
            cash = 0

        elif short_ma < long_ma and position > 0:
            cash = position * price
            position = 0

        equity = cash + position * price
        equity_curve.append(equity)

    if not equity_curve:
        return None

    total_return = (equity_curve[-1] - 10000.0) / 10000.0

    peak = equity_curve[0]
    max_dd = 0

    for e in equity_curve:
        peak = max(peak, e)
        dd = (e - peak) / peak
        max_dd = min(max_dd, dd)

    return {
        "return": float(total_return),
        "drawdown": float(max_dd)
    }

# =========================
# WALK-FORWARD
# =========================
def walk_forward(symbol="AAPL"):
    prices = get_prices(symbol)

    if prices is None or len(prices) < 200:
        return {"error": "Not enough data"}

    train_window = 60
    test_window = 20

    results = []
    i = 0

    while i + train_window + test_window < len(prices):

        train_data = prices[i:i + train_window]
        test_data = prices[i + train_window:i + train_window + test_window]

        best_params = None
        best_return = -999

        for short in [5, 10, 15]:
            for long in [20, 30, 50]:
                if short >= long:
                    continue

                result = simulate(train_data, short, long)

                if result and result["return"] > best_return:
                    best_return = result["return"]
                    best_params = (short, long)

        if best_params is None:
            i += test_window
            continue

        out = simulate(test_data, best_params[0], best_params[1])

        if out:
            results.append(out)

        i += test_window

    if not results:
        return {"error": "No valid results"}

    returns = [r["return"] for r in results]
    drawdowns = [r["drawdown"] for r in results]

    return {
        "segments": len(results),
        "avg_return_pct": round(np.mean(returns) * 100, 2),
        "worst_drawdown_pct": round(min(drawdowns) * 100, 2),
        "consistency_pct": round(
            (sum(1 for r in returns if r > 0) / len(returns)) * 100, 2
        ),
        "details": results
    }

# =========================
# ROUTES
# =========================
@app.route("/walkforward")
def walkforward():
    try:
        return jsonify(walk_forward())
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
