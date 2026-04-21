import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

SYMBOLS = ["AMD","NVDA","META","AVGO","INTC"]

# =========================
# MARKET CHECK
# =========================
def market_open():
    now = datetime.utcnow()
    return now.weekday() < 5

# =========================
# SAFE DATA FETCH
# =========================
def test_data(symbol):
    try:
        df = yf.download(
            symbol,
            period="5d",
            interval="1h",
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            return {"status": "fail", "reason": "no data"}

        closes = df["Close"]

        # 🔥 FORCE SAFE NUMERIC ARRAY
        prices = np.array(closes).astype(float).flatten()

        if len(prices) == 0:
            return {"status": "fail", "reason": "empty prices"}

        return {
            "status": "success",
            "bars": int(len(prices)),
            "first_price": float(prices[0]),
            "last_price": float(prices[-1]),
            "change": float(prices[-1] - prices[0])
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

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
# HEALTH
# =========================
@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# ROOT
# =========================
@app.route("/")
def home():
    return {
        "message": "Diagnostic running",
        "endpoints": ["/health", "/debug"]
    }

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
