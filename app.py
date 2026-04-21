import os
import pytz
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify
from alpaca_trade_api import REST

SYMBOLS = ["AMD","NVDA","META","AVGO","INTC"]

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)
app = Flask(__name__)

# =========================
# MARKET CHECK
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

# =========================
# GET PRICES (YFINANCE)
# =========================
def get_prices(symbol):
    try:
        df = yf.download(symbol, period="10d", interval="1h", progress=False)

        if df is None or df.empty:
            return None

        prices = df["Close"].dropna().values

        if len(prices) < 20:
            return None

        return prices

    except Exception as e:
        print(f"Data error {symbol}: {e}")
        return None

# =========================
# MOMENTUM (SLOPE)
# =========================
def get_momentum_score(symbol):
    prices = get_prices(symbol)

    if prices is None:
        return 0

    try:
        x = np.arange(len(prices))
        y = np.log(prices)

        slope, _ = np.polyfit(x, y, 1)

        returns = np.diff(prices) / prices[:-1]
        vol = np.std(returns[-20:])

        score = slope / (vol + 1e-6)

        return float(score)

    except:
        return 0

# =========================
# SIGNAL ENGINE
# =========================
def get_signals():
    ranked = []

    for s in SYMBOLS:
        score = get_momentum_score(s)

        try:
            price = api.get_latest_trade(s).price

            ranked.append({
                "symbol": s,
                "score": score,
                "price": float(price)
            })

        except:
            pass

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():
    return {
        "signals": get_signals()
    }

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
