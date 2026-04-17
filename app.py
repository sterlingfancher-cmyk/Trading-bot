import os
import requests
from datetime import datetime
import pytz

# ==============================
# CONFIG
# ==============================

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

MAX_POSITIONS = 3
RISK_PER_TRADE = 0.02
TRAILING_STOP = 0.95

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY
}

highest_price_tracker = {}

# ==============================
# LOGGING SYSTEM (NEW)
# ==============================

def log(message, data=None):
    timestamp = datetime.utcnow().isoformat()
    entry = f"{timestamp} | {message}"

    if data:
        entry += f" | {data}"

    print(entry)  # shows in Railway logs

    with open("bot_log.txt", "a") as f:
        f.write(entry + "\n")

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
        return r.json()
    except Exception as e:
        log("API GET ERROR", str(e))
        return {}

def api_post(endpoint, data):
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, headers=HEADERS)
        return r.json()
    except Exception as e:
        log("API POST ERROR", str(e))
        return {}

# ==============================
# DATA
# ==============================

def get_positions():
    return api_get("/v2/positions")

def get_account():
    return api_get("/v2/account")

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
            signals.append({"symbol": symbol, "price": price})

    return signals

# ==============================
# POSITION MANAGEMENT (FIXED)
# ==============================

def manage_positions():
    positions = get_positions()

    for pos in positions:
        symbol = pos["symbol"]
        qty = int(float(pos["qty"]))
        entry_price = float(pos["avg_entry_price"])
        current_price = get_price(symbol)

        if not current_price:
            continue

        if symbol not in highest_price_tracker:
            highest_price_tracker[symbol] = current_price

        if current_price > highest_price_tracker[symbol]:
            highest_price_tracker[symbol] = current_price

        highest = highest_price_tracker[symbol]
        stop_price = highest * TRAILING_STOP

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
    held_symbols = [p["symbol"] for p in positions]

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
# MAIN
# ==============================

def run():
    log("BOT START")

    market_open = is_market_open()
    log("MARKET STATUS", market_open)

    # ALWAYS run exits
    manage_positions()

    # ONLY run entries when open
    if market_open:
        find_new_trades()

    log("CYCLE COMPLETE")


if __name__ == "__main__":
    run()
