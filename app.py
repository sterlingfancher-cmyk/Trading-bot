import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["AMD","NVDA","META","AVGO","INTC"]

# =========================
# MARKET CHECK (optional)
# =========================
def market_open():
    now = datetime.utcnow()
    return now.weekday() < 5

# =========================
# TEST DATA FETCH
# =========================
def test_data(symbol):
    try:
        df = yf.download(
            symbol,
            period="5d",
            interval="1h",
            progress=False,
            threads=False  # 🔥 important for Railway stability
        )

        # 🔴 HARD DEBUG
        if df is None:
            return {"status": "fail", "reason": "df is None"}

        if df.empty:
            return {"status": "fail", "reason": "df EMPTY"}

        closes = df["Close"].dropna()

        if closes.empty:
            return {"status": "fail", "reason": "no close data"}

        prices = closes.values

        return {
            "status": "success",
            "bars": len(prices),
            "first_price": float(prices[0]),
            "last_price": float(prices[-1]),
            "change": float(prices[-1] - prices[0])
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

# =========================
# DEBUG ROUTE
# =========================
@app.route("/debug")
def debug():
    results = {}

    for s in SYMBOLS:
        results[s] = test_data(s)

    return jsonify({
        "timestamp": datetime.utcnow().isoformat(),
        "market_open": market_open(),
        "results": results
    })

# =========================
# HEALTH CHECK
# =========================
@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# ROOT (optional)
# =========================
@app.route("/")
def home():
    return {
        "message": "Trading bot diagnostic running",
        "endpoints": ["/health", "/debug"]
    }

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
