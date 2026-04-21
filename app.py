import os
import time
import threading
from flask import Flask, jsonify
from datetime import datetime
import pytz
import yfinance as yf

# SAFE IMPORT (prevents crash if package missing during build)
try:
    from alpaca_trade_api import REST
except:
    REST = None

app = Flask(__name__)

# ==============================
# ENV VARIABLES
# ==============================
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

api = None
if API_KEY and API_SECRET and REST:
    api = REST(API_KEY, API_SECRET, BASE_URL)

# ==============================
# CONFIG
# ==============================
WATCHLIST = ["AMD", "NVDA", "META", "AVGO", "INTC"]
POSITION_SIZE = 0.20  # 20% per trade
TRAILING_STOP = 0.06  # 6%
WEAKNESS_EXIT = -0.015  # -1.5% intraday

# ==============================
# HELPERS
# ==============================
def market_open():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est)
    return now.weekday() < 5 and 9 <= now.hour < 16


def get_price(symbol):
    try:
        data = yf.Ticker(symbol).history(period="1d")
        return float(data["Close"].iloc[-1])
    except:
        return None


def get_positions():
    if not api:
        return []
    try:
        return api.list_positions()
    except:
        return []


def get_account():
    if not api:
        return None
    try:
        return api.get_account()
    except:
        return None


# ==============================
# EXIT LOGIC
# ==============================
def should_exit(pos):
    try:
        entry = float(pos.avg_entry_price)
        price = float(pos.current_price)
        change = (price - entry) / entry

        # 1. TRAILING STOP
        if change < -TRAILING_STOP:
            print(f"EXIT (TRAILING STOP): {pos.symbol}")
            return True

        # 2. WEAKNESS EXIT (NEW)
        intraday = float(pos.unrealized_intraday_plpc)
        if intraday < WEAKNESS_EXIT:
            print(f"EXIT (WEAKNESS): {pos.symbol}")
            return True

        return False

    except Exception as e:
        print("Exit error:", e)
        return False


# ==============================
# SIGNAL ENGINE
# ==============================
def generate_signals():
    signals = []

    for symbol in WATCHLIST:
        price = get_price(symbol)
        if price:
            signals.append({
                "symbol": symbol,
                "price": price
            })

    # Simple ranking (price momentum placeholder)
    return sorted(signals, key=lambda x: x["price"], reverse=True)


# ==============================
# POSITION MANAGEMENT
# ==============================
def manage_positions():
    if not api:
        print("No API - skipping trading")
        return

    positions = get_positions()
    account = get_account()

    if not account:
        return

    equity = float(account.equity)

    # ===== EXIT FIRST =====
    for pos in positions:
        if should_exit(pos):
            try:
                api.submit_order(
                    symbol=pos.symbol,
                    qty=pos.qty,
                    side="sell",
                    type="market",
                    time_in_force="gtc"
                )
                print(f"SOLD {pos.symbol}")
            except Exception as e:
                print("Sell error:", e)

    # ===== REFRESH POSITIONS AFTER SELL =====
    positions = get_positions()
    held_symbols = [p.symbol for p in positions]

    # ===== FIND NEW ENTRIES =====
    signals = generate_signals()

    for sig in signals:
        symbol = sig["symbol"]

        if symbol in held_symbols:
            continue

        try:
            cash_to_use = equity * POSITION_SIZE
            qty = int(cash_to_use / sig["price"])

            if qty <= 0:
                continue

            api.submit_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

            print(f"BOUGHT {symbol}")
            break  # one trade per cycle

        except Exception as e:
            print("Buy error:", e)


# ==============================
# MAIN LOOP (AUTO RUN EVERY 5 MIN)
# ==============================
def bot_loop():
    while True:
        try:
            if market_open():
                print("Bot running...")
                manage_positions()
            else:
                print("Market closed")

        except Exception as e:
            print("Loop error:", e)

        time.sleep(300)  # 5 minutes


# Start background thread
threading.Thread(target=bot_loop, daemon=True).start()

# ==============================
# ROUTES
# ==============================
@app.route("/")
def home():
    return "Bot is running"


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
        "signals": generate_signals()
    })


@app.route("/run")
def run_once():
    manage_positions()
    return jsonify({"status": "ran"})


@app.route("/force-exit")
def force_exit():
    if not api:
        return jsonify({"error": "no api"})

    for pos in get_positions():
        try:
            api.submit_order(
                symbol=pos.symbol,
                qty=pos.qty,
                side="sell",
                type="market",
                time_in_force="gtc"
            )
        except Exception as e:
            print(e)

    return jsonify({"status": "liquidated"})
