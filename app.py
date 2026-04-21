import os
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify

# =========================
# CONFIG
# =========================
SYMBOLS = ["AMD", "NVDA", "META", "AVGO", "INTC"]

RISK_PER_TRADE = 0.02
TRAILING_STOP = 0.06
WEAK_EXIT = -0.015
PROFIT_LOCK = 0.07

BASE_URL = "https://paper-api.alpaca.markets"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# =========================
# SAFE ALPACA INIT
# =========================
api = None
try:
    from alpaca_trade_api import REST
    if API_KEY and API_SECRET:
        api = REST(API_KEY, API_SECRET, BASE_URL)
except Exception as e:
    print("Alpaca init failed:", e)

# =========================
# APP
# =========================
app = Flask(__name__)

# =========================
# MARKET CHECK
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

# =========================
# MOMENTUM
# =========================
def get_momentum_score(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if len(df) < 30:
            return 0

        r5 = df["Close"].pct_change(5).iloc[-1]
        r10 = df["Close"].pct_change(10).iloc[-1]
        r20 = df["Close"].pct_change(20).iloc[-1]

        vol = df["Close"].pct_change().rolling(20).std().iloc[-1]

        return float((r5*0.5)+(r10*0.3)+(r20*0.2)-(vol*0.5))
    except:
        return 0

def get_signals():
    ranked = []
    for s in SYMBOLS:
        score = get_momentum_score(s)
        price = yf.Ticker(s).history(period="1d")["Close"].iloc[-1]

        ranked.append({
            "symbol": s,
            "score": score,
            "price": float(price)
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

# =========================
# POSITIONS
# =========================
def get_positions():
    if not api:
        return []
    try:
        return api.list_positions()
    except:
        return []

# =========================
# PROFIT LOCK
# =========================
def handle_profit_lock(p):
    if float(p.unrealized_plpc) >= PROFIT_LOCK:
        qty = int(float(p.qty) * 0.5)
        if qty > 0:
            api.submit_order(
                symbol=p.symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )

# =========================
# EXITS
# =========================
def handle_exits(p):
    if float(p.unrealized_plpc) <= WEAK_EXIT:
        api.submit_order(
            symbol=p.symbol,
            qty=p.qty,
            side="sell",
            type="market",
            time_in_force="day"
        )

# =========================
# ENTRIES
# =========================
def handle_entries(signals, current):
    if not api:
        return

    cash = float(api.get_account().cash)

    for s in signals[:2]:
        if s["symbol"] not in current:
            qty = int((cash * RISK_PER_TRADE) / s["price"])
            if qty > 0:
                api.submit_order(
                    symbol=s["symbol"],
                    qty=qty,
                    side="buy",
                    type="market",
                    time_in_force="day"
                )

# =========================
# BOT
# =========================
def run_bot():
    if not api:
        return {"error": "no api"}

    if not market_open():
        return {"status": "market closed"}

    positions = get_positions()
    signals = get_signals()

    current = [p.symbol for p in positions]

    for p in positions:
        handle_profit_lock(p)
        handle_exits(p)

    handle_entries(signals, current)

    return {"status": "ran"}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Bot running"

@app.route("/health")
def health():
    return jsonify({"status": "running"})

@app.route("/debug")
def debug():
    return jsonify({
        "has_key": bool(API_KEY),
        "has_secret": bool(API_SECRET),
        "market_open": market_open(),
        "positions": [p.symbol for p in get_positions()],
        "signals": get_signals()
    })

@app.route("/run")
def run():
    return jsonify(run_bot())

# =========================
# CRITICAL FIX (DO NOT REMOVE)
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
