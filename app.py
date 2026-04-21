import os
import pytz
import requests
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, jsonify
from alpaca_trade_api import REST

SYMBOLS = ["AMD","NVDA","META","AVGO","INTC"]

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)
app = Flask(__name__)

# =========================
# GET PRICES (NO FILTERS)
# =========================
def get_prices(symbol):
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"

    headers = {
        "APCA-API-KEY-ID": API_KEY,
        "APCA-API-SECRET-KEY": API_SECRET
    }

    end = datetime.utcnow()
    start = end - timedelta(days=10)

    params = {
        "timeframe": "1Hour",
        "start": start.isoformat() + "Z",
        "end": end.isoformat() + "Z",
        "limit": 500
    }

    res = requests.get(url, headers=headers, params=params)
    data = res.json()

    bars = data.get("bars", [])

    if not bars:
        return None

    bars = sorted(bars, key=lambda x: x["t"])
    prices = np.array([bar["c"] for bar in bars])

    return prices

# =========================
# MOMENTUM (FORCED NON-ZERO)
# =========================
def get_momentum_score(symbol):
    prices = get_prices(symbol)

    if prices is None or len(prices) < 10:
        return {
            "score": 0,
            "reason": "no_data"
        }

    # FORCE simple movement calc
    change = prices[-1] - prices[0]

    return {
        "score": float(change),  # 🔥 IMPOSSIBLE TO BE ALWAYS ZERO
        "first_price": float(prices[0]),
        "last_price": float(prices[-1]),
        "bars": len(prices)
    }

# =========================
# DEBUG ROUTE (FULL VISIBILITY)
# =========================
@app.route("/debug")
def debug():
    results = {}

    for s in SYMBOLS:
        try:
            results[s] = get_momentum_score(s)
        except Exception as e:
            results[s] = {"error": str(e)}

    return jsonify(results)

# =========================
# HEALTH
# =========================
@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
