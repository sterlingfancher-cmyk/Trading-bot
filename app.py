import os
import time
import threading
import sqlite3
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, Response
from alpaca_trade_api import REST

app = Flask(__name__)

# =========================
# CONFIG
# =========================
BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

CHECK_INTERVAL = 300
MAX_DRAWDOWN = -0.10

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trading.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS equity (time TEXT, equity REAL)")
conn.commit()

# =========================
# DATA
# =========================
def get_prices(symbol, period="1y"):
    df = yf.download(symbol, period=period, interval="1d", progress=False)
    if df.empty:
        return None
    return np.array(df["Close"]).astype(float)

# =========================
# BACKTEST CORE
# =========================
def simulate(prices, short=10, long=20):
    cash = 10000
    pos = 0
    equity = []

    for i in range(long, len(prices)):
        s = np.mean(prices[i-short:i])
        l = np.mean(prices[i-long:i])
        price = prices[i]

        if s > l and pos == 0:
            pos = cash / price
            cash = 0

        elif s < l and pos > 0:
            cash = pos * price
            pos = 0

        equity.append(cash + pos * price)

    if not equity:
        return None

    ret = (equity[-1] - 10000) / 10000
    peak = equity[0]
    dd = 0

    for e in equity:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    return {"return": ret, "drawdown": dd}

# =========================
# WALK-FORWARD ENGINE
# =========================
def walk_forward(symbol="AAPL"):
    prices = get_prices(symbol, "1y")
    if prices is None or len(prices) < 200:
        return {"error": "not enough data"}

    window_train = 60
    window_test = 20

    results = []

    i = 0
    while i + window_train + window_test < len(prices):
        train = prices[i:i+window_train]
        test = prices[i+window_train:i+window_train+window_test]

        best = None
        best_ret = -999

        # optimize on train
        for s in [5,10,15]:
            for l in [20,30,50]:
                if s >= l:
                    continue

                res = simulate(train, s, l)
                if res and res["return"] > best_ret:
                    best_ret = res["return"]
                    best = (s, l)

        # test on unseen data
        out = simulate(test, best[0], best[1])

        if out:
            results.append(out)

        i += window_test

    if not results:
        return {"error": "no results"}

    returns = [r["return"] for r in results]
    dds = [r["drawdown"] for r in results]

    return {
        "segments": len(results),
        "avg_return": round(np.mean(returns)*100,2),
        "worst_drawdown": round(min(dds)*100,2),
        "consistency": round((sum(1 for r in returns if r>0)/len(returns))*100,2),
        "details": results
    }

# =========================
# ROUTES
# =========================
@app.route("/walkforward")
def wf():
    return jsonify(walk_forward())

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
