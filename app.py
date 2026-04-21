import os
import requests
from datetime import datetime
import pytz
from flask import Flask, jsonify

app = Flask(__name__)

# ==============================
# 🔥 BULLETPROOF ENV LOADING
# ==============================

API_KEY = (
    os.getenv("APCA_API_KEY_ID") or
    os.getenv("ALPACA_API_KEY") or
    os.getenv("API_KEY")
)

SECRET_KEY = (
    os.getenv("APCA_API_SECRET_KEY") or
    os.getenv("ALPACA_SECRET_KEY") or
    os.getenv("SECRET_KEY")
)

BASE_URL = "https://paper-api.alpaca.markets"

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY
}

MAX_POSITIONS = 5
RISK_PER_TRADE = 0.02

highest_price_tracker = {}

# ==============================
# LOGGING
# ==============================

def log(msg, data=None):
    print(f"{datetime.utcnow()} | {msg} | {data if data else ''}")

# ==============================
# MARKET HOURS
# ==============================

def is_market_open():
    tz = pytz.timezone("US/Central")
    now = datetime.now(tz)

    if now.weekday() >= 5:
        return False

    open_time = now.replace(hour=8, minute=30, second=0)
    close_time = now.replace(hour=15, minute=0, second=0)

    return open_time <= now <= close_time

# ==============================
# API
# ==============================

def api_get(endpoint):
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS)
        log("API GET", {"endpoint": endpoint, "status": r.status_code})
        return r.json()
    except Exception as e:
        log("API ERROR", str(e))
        return {}

def get_positions():
    data = api_get("/v2/positions")
    return data if isinstance(data, list) else []

def get_account():
    data = api_get("/v2/account")
    return data if isinstance(data, dict) else {"cash": 0}

def get_price(symbol):
    try:
        r = requests.get(
            f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest",
            headers=HEADERS
        )
        return float(r.json()["trade"]["p"])
    except:
        log("PRICE ERROR", symbol)
        return None

# ==============================
# TRAILING STOP
# ==============================

def get_trailing_stop(entry, high):
    gain = (high - entry) / entry

    if gain < 0.03:
        return 0.97
    elif gain < 0.07:
        return 0.95
    elif gain < 0.15:
        return 0.93
    else:
        return 0.90

# ==============================
# ORDERS
# ==============================

def place_order(symbol, qty, side):
    order = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day"
    }

    r = requests.post(f"{BASE_URL}/v2/orders", json=order, headers=HEADERS)
    log("ORDER", r.json())

# ==============================
# SIGNALS
# ==============================

WATCHLIST = ["AMD", "NVDA", "META", "AVGO", "INTC"]

def get_signals():
    signals = []
    for s in WATCHLIST:
        p = get_price(s)
        if p:
            signals.append({"symbol": s, "price": p})
    return signals

# ==============================
# POSITION MANAGEMENT
# ==============================

def manage_positions():
    positions = get_positions()

    for p in positions:
        symbol = p["symbol"]
        qty = int(float(p["qty"]))
        entry = float(p["avg_entry_price"])
        current = get_price(symbol)

        if not current:
            continue

        if symbol not in highest_price_tracker:
            highest_price_tracker[symbol] = current

        if current > highest_price_tracker[symbol]:
            highest_price_tracker[symbol] = current

        high = highest_price_tracker[symbol]

        trailing = get_trailing_stop(entry, high)
        stop = high * trailing

        if current > entry * 1.03:
            stop = max(stop, entry)

        log("CHECK", {"symbol": symbol, "current": current, "stop": stop})

        if current <= stop:
            log("SELL TRIGGER", symbol)
            place_order(symbol, qty, "sell")
            highest_price_tracker.pop(symbol, None)

# ==============================
# ENTRY
# ==============================

def find_new_trades():
    positions = get_positions()
    held = [p["symbol"] for p in positions]

    if len(held) >= MAX_POSITIONS:
        return

    signals = get_signals()
    cash = float(get_account().get("cash", 0))

    for s in signals:
        if s["symbol"] in held:
            continue

        if len(held) >= MAX_POSITIONS:
            break

        qty = int((cash * RISK_PER_TRADE) / s["price"])

        if qty > 0:
            place_order(s["symbol"], qty, "buy")
            held.append(s["symbol"])

# ==============================
# CORE
# ==============================

def run_bot():
    log("START")

    log("ENV CHECK", {
        "key_loaded": API_KEY is not None,
        "secret_loaded": SECRET_KEY is not None
    })

    manage_positions()

    if is_market_open():
        find_new_trades()

# ==============================
# ROUTES
# ==============================

@app.route("/")
def home():
    return {"status": "running"}

@app.route("/run")
def run():
    run_bot()
    return {"status": "ran"}

@app.route("/debug")
def debug():
    return jsonify({
        "has_key": API_KEY is not None,
        "has_secret": SECRET_KEY is not None,
        "positions": get_positions(),
        "signals": get_signals(),
        "market_open": is_market_open()
    })

# ==============================
# START
# ==============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
