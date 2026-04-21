import os
import time
import threading
from flask import Flask, jsonify
from alpaca_trade_api import REST
from datetime import datetime

app = Flask(__name__)

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

TRAILING_STOP_PCT = 0.06
MAX_POSITIONS = 5
POSITION_SIZE = 0.20

AUTO_RUN_INTERVAL = 300  # 🔥 5 minutes

api = REST(API_KEY, API_SECRET, BASE_URL)

# =========================
# HELPERS
# =========================
def is_market_open():
    return api.get_clock().is_open

def get_positions():
    try:
        return [p._raw for p in api.list_positions()]
    except Exception as e:
        print("ERROR positions:", e)
        return []

def get_account():
    return api.get_account()

def get_signals():
    return [
        {"symbol": "AMD"},
        {"symbol": "NVDA"},
        {"symbol": "META"},
        {"symbol": "AVGO"},
        {"symbol": "INTC"},
    ]

# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    positions = get_positions()

    for pos in positions:
        try:
            symbol = pos.get("symbol")
            entry = float(pos.get("avg_entry_price", 0))
            current = float(pos.get("current_price", 0))

            if entry == 0:
                continue

            drawdown = (entry - current) / entry

            if drawdown >= TRAILING_STOP_PCT:
                print(f"SELL: {symbol}")

                api.submit_order(
                    symbol=symbol,
                    qty=pos.get("qty"),
                    side="sell",
                    type="market",
                    time_in_force="gtc"
                )

        except Exception as e:
            print("ERROR manage:", e)

# =========================
# ENTRY LOGIC
# =========================
def place_trades():
    account = get_account()
    buying_power = float(account.buying_power)

    positions = get_positions()
    held = [p.get("symbol") for p in positions]

    for signal in get_signals():
        if len(held) >= MAX_POSITIONS:
            break

        symbol = signal["symbol"]

        if symbol in held:
            continue

        try:
            price = api.get_latest_trade(symbol).price
            qty = int((buying_power * POSITION_SIZE) / price)

            if qty <= 0:
                continue

            print(f"BUY: {symbol}")

            api.submit_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

            held.append(symbol)

        except Exception as e:
            print("ERROR buy:", e)

# =========================
# MAIN BOT
# =========================
def run_bot():
    print("RUN:", datetime.now())

    if not is_market_open():
        print("Market closed")
        return {"status": "closed"}

    manage_positions()
    place_trades()

    return {"status": "ran"}

# =========================
# AUTO LOOP
# =========================
def auto_loop():
    print("AUTO LOOP STARTED")

    while True:
        try:
            run_bot()
        except Exception as e:
            print("AUTO LOOP ERROR:", e)

        time.sleep(AUTO_RUN_INTERVAL)

# Start background thread ONCE
thread_started = False

def start_auto_loop():
    global thread_started
    if not thread_started:
        thread = threading.Thread(target=auto_loop, daemon=True)
        thread.start()
        thread_started = True

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    start_auto_loop()
    return "Bot running with auto-loop"

@app.route("/run")
def run():
    return jsonify(run_bot())

@app.route("/health")
def health():
    return jsonify({"status": "running"})

@app.route("/debug")
def debug():
    return jsonify({
        "market_open": is_market_open(),
        "positions": get_positions(),
        "signals": get_signals()
    })

@app.route("/force-exit")
def force_exit():
    for pos in get_positions():
        try:
            api.submit_order(
                symbol=pos.get("symbol"),
                qty=pos.get("qty"),
                side="sell",
                type="market",
                time_in_force="gtc"
            )
        except Exception as e:
            print("ERROR exit:", e)

    return jsonify({"status": "exited"})
