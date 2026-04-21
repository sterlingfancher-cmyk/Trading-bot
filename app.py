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
PROFIT_LOCK = 0.07   # 7% profit → partial sell

BASE_URL = "https://paper-api.alpaca.markets"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# =========================
# SAFE ALPACA IMPORT
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
# MOMENTUM ENGINE
# =========================
def get_momentum_score(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if len(df) < 30:
            return 0

        df["returns"] = df["Close"].pct_change()

        # Multi-timeframe momentum
        r5 = df["Close"].pct_change(5).iloc[-1]
        r10 = df["Close"].pct_change(10).iloc[-1]
        r20 = df["Close"].pct_change(20).iloc[-1]

        # Volatility penalty
        vol = df["returns"].rolling(20).std().iloc[-1]

        score = (r5 * 0.5) + (r10 * 0.3) + (r20 * 0.2) - (vol * 0.5)

        return float(score)

    except Exception as e:
        print(f"Momentum error {symbol}:", e)
        return 0

# =========================
# GET SIGNALS (RANKED)
# =========================
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
# GET POSITIONS
# =========================
def get_positions():
    if not api:
        return []

    try:
        return api.list_positions()
    except:
        return []

# =========================
# PROFIT LOCKING
# =========================
def handle_profit_lock(position):
    unrealized = float(position.unrealized_plpc)

    if unrealized >= PROFIT_LOCK:
        qty = int(float(position.qty) * 0.5)

        if qty > 0:
            print(f"🔒 Profit lock: Selling half {position.symbol}")
            api.submit_order(
                symbol=position.symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )

# =========================
# EXIT LOGIC
# =========================
def handle_exits(position):
    pl = float(position.unrealized_plpc)

    if pl <= WEAK_EXIT:
        print(f"❌ Weak exit {position.symbol}")
        api.submit_order(
            symbol=position.symbol,
            qty=position.qty,
            side="sell",
            type="market",
            time_in_force="day"
        )

# =========================
# ENTRY LOGIC
# =========================
def handle_entries(signals, current_symbols):
    if not api:
        return

    account = api.get_account()
    buying_power = float(account.cash)

    for s in signals[:2]:  # top 2 only
        if s["symbol"] not in current_symbols:
            qty = int((buying_power * RISK_PER_TRADE) / s["price"])

            if qty > 0:
                print(f"🚀 Buying {s['symbol']}")
                api.submit_order(
                    symbol=s["symbol"],
                    qty=qty,
                    side="buy",
                    type="market",
                    time_in_force="day"
                )

# =========================
# MAIN BOT LOOP
# =========================
def run_bot():
    if not api:
        return {"error": "no api"}

    if not market_open():
        return {"status": "market closed"}

    positions = get_positions()
    signals = get_signals()

    current_symbols = [p.symbol for p in positions]

    for p in positions:
        handle_profit_lock(p)
        handle_exits(p)

    handle_entries(signals, current_symbols)

    return {
        "status": "ran",
        "positions": current_symbols,
        "top_signal": signals[0] if signals else None
    }

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
