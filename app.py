import os
import time
import threading
from flask import Flask, jsonify

# =========================
# SAFE ALPACA IMPORT
# =========================
try:
    from alpaca_trade_api import REST
except:
    REST = None

app = Flask(__name__)

# =========================
# ENV VARIABLES
# =========================
def get_env():
    return {
        "API_KEY": os.getenv("APCA_API_KEY_ID"),
        "API_SECRET": os.getenv("APCA_API_SECRET_KEY"),
        "BASE_URL": os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    }

# =========================
# SAFE API INIT
# =========================
def get_api():
    env = get_env()

    if not env["API_KEY"] or not env["API_SECRET"]:
        print("⚠️ Missing Alpaca API keys")
        return None

    if REST is None:
        print("⚠️ alpaca_trade_api not installed")
        return None

    try:
        return REST(env["API_KEY"], env["API_SECRET"], env["BASE_URL"])
    except Exception as e:
        print(f"❌ API INIT ERROR: {e}")
        return None

# =========================
# MARKET CHECK
# =========================
def is_market_open():
    api = get_api()
    if not api:
        return False

    try:
        clock = api.get_clock()
        return clock.is_open
    except:
        return False

# =========================
# GET POSITIONS
# =========================
def get_positions():
    api = get_api()
    if not api:
        return []

    try:
        positions = api.list_positions()
        return [p._raw for p in positions]
    except Exception as e:
        print(f"❌ Position error: {e}")
        return []

# =========================
# MOCK SIGNALS (replace later)
# =========================
def get_signals():
    return [
        {"symbol": "AMD", "price": 275},
        {"symbol": "NVDA", "price": 200},
        {"symbol": "META", "price": 670},
        {"symbol": "AVGO", "price": 400},
        {"symbol": "INTC", "price": 65},
    ]

# =========================
# CORE BOT LOGIC
# =========================
def run_bot():
    print("🚀 BOT RUN STARTED")

    api = get_api()
    if not api:
        print("❌ API not available")
        return {"status": "no_api"}

    if not is_market_open():
        print("🕒 Market closed")
        return {"status": "market_closed"}

    positions = get_positions()
    signals = get_signals()

    print(f"📊 Positions: {len(positions)}")
    print(f"📡 Signals: {len(signals)}")

    # (PLACE YOUR STRATEGY LOGIC HERE)

    return {"status": "ran"}

# =========================
# AUTO LOOP (5 MIN)
# =========================
def bot_loop():
    while True:
        try:
            run_bot()
        except Exception as e:
            print(f"❌ LOOP ERROR: {e}")
        time.sleep(300)  # 5 minutes

# =========================
# START BACKGROUND THREAD
# =========================
threading.Thread(target=bot_loop, daemon=True).start()

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return run_bot()

@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/debug")
def debug():
    env = get_env()

    return {
        "has_key": bool(env["API_KEY"]),
        "has_secret": bool(env["API_SECRET"]),
        "market_open": is_market_open(),
        "positions": get_positions(),
        "signals": get_signals()
    }

@app.route("/force-exit")
def force_exit():
    api = get_api()
    if not api:
        return {"error": "API not initialized"}

    try:
        positions = api.list_positions()
        for p in positions:
            api.submit_order(
                symbol=p.symbol,
                qty=p.qty,
                side="sell" if p.side == "long" else "buy",
                type="market",
                time_in_force="gtc"
            )
        return {"status": "positions closed"}
    except Exception as e:
        return {"error": str(e)}

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
