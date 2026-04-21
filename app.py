import os
import time
import threading
from flask import Flask, jsonify
from datetime import datetime
import pytz
import yfinance as yf

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

def init_api():
    global api
    if API_KEY and API_SECRET and REST:
        try:
            api = REST(API_KEY, API_SECRET, BASE_URL)
            print("API initialized")
        except Exception as e:
            print("API INIT FAILED:", e)
            api = None

# ==============================
# CONFIG
# ==============================
WATCHLIST = ["AMD", "NVDA", "META", "AVGO", "INTC"]
POSITION_SIZE = 0.20
TRAILING_STOP = 0.06
WEAKNESS_EXIT = -0.015

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

        if change < -TRAILING_STOP:
            print(f"EXIT TRAIL: {pos.symbol}")
            return True

        intraday = float(pos.unrealized_intraday_plpc)
        if intraday < WEAKNESS_EXIT:
            print(f"EXIT WEAK: {pos.symbol}")
            return True

        return False
    except:
        return False

# ==============================
# SIGNALS
# ==============================
def generate_signals():
    signals = []
    for s in WATCHLIST:
        price = get_price(s)
        if price:
            signals.append({"symbol": s, "price": price})
    return sorted(signals, key=lambda x: x["price"], reverse=True)

# ==============================
# TRADING ENGINE
# ==============================
def manage_positions():
    if not api:
        print("No API")
        return

    positions = get_positions()
    account = get_account()
    if not account:
        return

    equity = float(account.equity)

    # SELL
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
                print("Sold", pos.symbol)
            except Exception as e:
                print("Sell error:", e)

    # REFRESH
    positions = get_positions()
    held = [p.symbol for p in positions]

    # BUY
    for sig in generate_signals():
        if sig["symbol"] in held:
            continue
        try:
            qty = int((equity * POSITION_SIZE) / sig["price"])
            if qty <= 0:
                continue

            api.submit_order(
                symbol=sig["symbol"],
                qty=qty,
                side="buy",
                type="market",
                time_in_force="gtc"
            )
            print("Bought", sig["symbol"])
            break
        except Exception as e:
            print("Buy error:", e)

# ==============================
# BOT LOOP
# ==============================
def bot_loop():
    print("Bot started")
    while True:
        try:
            if market_open():
                manage_positions()
            else:
                print("Market closed")
        except Exception as e:
            print("Loop error:", e)

        time.sleep(300)

# ==============================
# START BOT (NO FLASK HOOKS)
# ==============================
def start_background_bot():
    init_api()
    thread = threading.Thread(target=bot_loop)
    thread.daemon = True
    thread.start()

start_background_bot()

# ==============================
# ROUTES
# ==============================
@app.route("/")
def home():
    return "OK"

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
        except:
            pass

    return jsonify({"status": "done"})
