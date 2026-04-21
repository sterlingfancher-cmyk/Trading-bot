import os
import pytz
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, jsonify

from alpaca_trade_api import REST

# =========================
# CONFIG
# =========================
SYMBOLS = ["AMD", "NVDA", "META", "AVGO", "INTC"]

RISK_PER_TRADE = 0.02
WEAK_EXIT = -0.015
PROFIT_LOCK = 0.07

BASE_URL = "https://paper-api.alpaca.markets"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

app = Flask(__name__)

# =========================
# MARKET CHECK
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

# =========================
# GET HISTORICAL DATA (ALPACA)
# =========================
def get_prices(symbol):
    try:
        bars = api.get_bars(
            symbol,
            "1Day",
            limit=30
        ).df

        if bars.empty:
            return None

        return bars["close"].values

    except Exception as e:
        print(f"Data error {symbol}: {e}")
        return None

# =========================
# MOMENTUM ENGINE (ALPACA DATA)
# =========================
def get_momentum_score(symbol):
    prices = get_prices(symbol)

    if prices is None or len(prices) < 25:
        return 0

    try:
        r5 = (prices[-1] / prices[-6]) - 1
        r10 = (prices[-1] / prices[-11]) - 1
        r20 = (prices[-1] / prices[-21]) - 1

        returns = np.diff(prices) / prices[:-1]

        if len(returns) < 20:
            return 0

        vol = np.std(returns[-20:])

        score = (r5 * 0.5) + (r10 * 0.3) + (r20 * 0.2) - (vol * 0.5)

        if not np.isfinite(score):
            return 0

        return float(score)

    except Exception as e:
        print(f"Momentum error {symbol}: {e}")
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

        except Exception as e:
            print(f"Price error {s}: {e}")

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
# PROFIT LOCK
# =========================
def handle_profit_lock(p):
    try:
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
    except:
        pass

# =========================
# EXIT LOGIC
# =========================
def handle_exits(p):
    try:
        if float(p.unrealized_plpc) <= WEAK_EXIT:
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
# BOT
# =========================
def run_bot():
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
        "top_signals": signals[:3]
    }

# =========================
# ROUTES
# =========================
@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/debug")
def debug():
    return {
        "signals": get_signals(),
        "positions": [p.symbol for p in get_positions()]
    }

@app.route("/run")
def run():
    return run_bot()

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
