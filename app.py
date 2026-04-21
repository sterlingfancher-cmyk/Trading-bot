import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify
from alpaca_trade_api import REST

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["AMD","NVDA","META","AVGO","INTC"]

RISK_PER_TRADE = 0.02
BASE_URL = "https://paper-api.alpaca.markets"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

# =========================
# GET PRICES
# =========================
def get_prices(symbol):
    try:
        df = yf.download(
            symbol,
            period="5d",
            interval="1h",
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            return None

        prices = np.array(df["Close"]).astype(float).flatten()

        if len(prices) < 20:
            return None

        return prices

    except:
        return None

# =========================
# MOMENTUM SCORE (FINAL)
# =========================
def get_momentum_score(symbol):
    prices = get_prices(symbol)

    if prices is None:
        return 0

    try:
        # simple + effective
        short = prices[-1] - prices[-10]
        medium = prices[-1] - prices[-20]

        score = (short * 0.6) + (medium * 0.4)

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
# POSITIONS
# =========================
def get_positions():
    try:
        return api.list_positions()
    except:
        return []

# =========================
# ENTRY LOGIC
# =========================
def handle_entries(signals, current_symbols):
    try:
        account = api.get_account()
        cash = float(account.cash)

        for s in signals[:2]:
            if s["symbol"] not in current_symbols:
                qty = int((cash * RISK_PER_TRADE) / s["price"])

                if qty > 0:
                    api.submit_order(
                        symbol=s["symbol"],
                        qty=qty,
                        side="buy",
                        type="market",
                        time_in_force="day"
                    )
    except:
        pass

# =========================
# EXIT LOGIC
# =========================
def handle_exits():
    try:
        positions = api.list_positions()

        for p in positions:
            if float(p.unrealized_plpc) < -0.02:
                api.submit_order(
                    symbol=p.symbol,
                    qty=p.qty,
                    side="sell",
                    type="market",
                    time_in_force="day"
                )
    except:
        pass

# =========================
# BOT
# =========================
def run_bot():
    positions = get_positions()
    signals = get_signals()

    current_symbols = [p.symbol for p in positions]

    handle_exits()
    handle_entries(signals, current_symbols)

    return {
        "signals": signals[:3],
        "positions": current_symbols
    }

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():
    return {
        "signals": get_signals()
    }

@app.route("/run")
def run():
    return run_bot()

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
