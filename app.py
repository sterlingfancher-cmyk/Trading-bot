import os
import requests
from datetime import datetime
import pytz
from flask import Flask, jsonify

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

MAX_POSITIONS = 3
RISK_PER_TRADE = 0.02

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY
}

highest_price_tracker = {}

# ==============================
# LOGGING
# ==============================

def log(message, data=None):
    timestamp = datetime.utcnow().isoformat()
    entry = f"{timestamp} | {message}"

    if data:
        entry += f" | {data}"

    print(entry)

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
# API HELPERS
# ==============================

def api_get(endpoint):
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS)
        log("API GET", {"endpoint": endpoint, "status": r.status_code})

        try:
            return r.json()
        except:
            log("API JSON ERROR", r.text)
            return {}

    except Exception as e:
        log("API GET ERROR", str(e))
        return {}

def api_post(endpoint, data):
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, headers=HEADERS)
        log("API POST", {"endpoint": endpoint, "status": r.status_code})
        return r.json()
    except Exception as e:
        log("API POST ERROR", str(e))
        return {}

# ==============================
# DATA
# ==============================

def get_positions():
    data = api_get("/v2/positions")

    if isinstance(data, list):
        return data

    log("POSITIONS ERROR", data)
    return []

def get_account():
    data = api_get("/v2/account")

    if isinstance(data, dict) and "cash" in data:
        return data

    log("ACCOUNT ERROR", data)
    return {"cash": 0}

def get_price(symbol):
    try:
        r = requests.get(
            f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest",
            headers=HEADERS
        )

        log("PRICE FETCH", {"symbol": symbol, "status": r.status_code})

        data = r.json()

        return float(data["trade"]["p"])

    except Exception as e:
        log("PRICE ERROR", {"symbol": symbol, "error": str(e)})
        return None

# ==============================
# TRAILING STOP
# ==============================

def get_trailing_stop(entry_price, highest_price):
    gain = (highest_price - entry_price) / entry_price

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

    result = api_post("/v2/orders", order)
    log("ORDER PLACED", result)

# ==============================
# SIGNALS
# ==============================

WATCHLIST = ["AMD", "NVDA", "META", "AVGO", "INTC"]

def get_signals():
    signals = []

    for symbol in WATCHLIST:
        price = get_price(symbol)

        if price:
            signals.append({
                "symbol": symbol,
                "price": price
            })

    log("SIGNALS GENERATED", signals)
    return signals

# ==============================
# POSITION MANAGEMENT
# ==============================

def manage_positions():
    positions = get_positions()

    for pos in positions:

        if not isinstance(pos, dict):
            log("BAD POSITION FORMAT", pos)
            continue

        symbol = pos.get("symbol")
        qty = int(float(pos.get("qty", 0)))
        entry_price = float(pos.get("avg_entry_price", 0))
        current_price = get_price(symbol)

        if not current_price:
            continue

        if symbol not in highest_price_tracker:
            highest_price_tracker[symbol] = current_price

        if current_price > highest_price_tracker[symbol]:
            highest_price_tracker[symbol] = current_price

        highest = highest_price_tracker[symbol]

        trailing = get_trailing_stop(entry_price, highest)
        stop_price = highest * trailing

        if current_price > entry_price * 1.03:
            stop_price = max(stop_price, entry_price)

        log("POSITION CHECK", {
            "symbol": symbol,
            "entry": entry_price,
            "current": current_price,
            "highest": highest,
            "stop": stop_price
        })

        if current_price <= stop_price:
            log("TRAILING STOP HIT", symbol)
            place_order(symbol, qty, "sell")
            highest_price_tracker.pop(symbol, None)

# ==============================
# ENTRY ENGINE
# ==============================

def find_new_trades():
    positions = get_positions()
    held_symbols = [p["symbol"] for p in positions if isinstance(p, dict)]

    if len(held_symbols) >= MAX_POSITIONS:
        log("MAX POSITIONS REACHED")
        return

    signals = get_signals()
    account = get_account()

    buying_power = float(account.get("cash", 0))

    for s in signals:
        symbol = s["symbol"]
        price = s["price"]

        if symbol in held_symbols:
            continue

        if len(held_symbols) >= MAX_POSITIONS:
            break

        position_size = buying_power * RISK_PER_TRADE
        qty = int(position_size / price)

        if qty <= 0:
            continue

        log("BUY SIGNAL", {"symbol": symbol, "qty": qty})
        place_order(symbol, qty, "buy")

        held_symbols.append(symbol)

# ==============================
# CORE ENGINE
# ==============================

def run_bot():
    log("BOT START")

    log("ENV CHECK", {
        "has_key": API_KEY is not None,
        "has_secret": SECRET_KEY is not None
    })

    market_open = is_market_open()
    log("MARKET STATUS", market_open)

    manage_positions()

    if market_open:
        find_new_trades()

    log("CYCLE COMPLETE")

# ==============================
# WEB ROUTES
# ==============================

@app.route("/")
def home():
    return {"status": "bot running"}

@app.route("/run")
def run_once():
    run_bot()
    return {"status": "ran once"}

@app.route("/debug")
def debug():
    return jsonify({
        "market_open": is_market_open(),
        "positions": get_positions(),
        "signals": get_signals(),
        "has_key": API_KEY is not None,
        "has_secret": SECRET_KEY is not None
    })

@app.route("/force-exit")
def force_exit():
    positions = get_positions()

    for pos in positions:
        if isinstance(pos, dict):
            place_order(pos["symbol"], int(float(pos["qty"])), "sell")

    return {"status": "force exit executed"}

# ==============================
# PORT FIX
# ==============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
