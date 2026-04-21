import os
import time
import threading
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify
from alpaca_trade_api import REST

app = Flask(__name__)

# =========================
# CONFIG
# =========================
MAX_UNIVERSE = 300
FILTERED_UNIVERSE = 60
MAX_POSITIONS = 5

RISK_PER_TRADE = 0.02
MIN_SCORE = 1.0
TRAILING_STOP = 0.03
CHECK_INTERVAL = 300

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

peak_prices = {}

# =========================
# STEP 1: BUILD UNIVERSE
# =========================
def get_universe():
    try:
        assets = api.list_assets(status='active')

        symbols = [
            a.symbol for a in assets
            if a.tradable and a.easy_to_borrow and a.shortable
        ]

        return symbols[:MAX_UNIVERSE]

    except:
        return []

# =========================
# STEP 2: FAST FILTER
# =========================
def fast_filter(symbols):
    filtered = []

    for s in symbols:
        try:
            df = yf.download(s, period="2d", interval="1h", progress=False, threads=False)

            if df is None or df.empty:
                continue

            price = df["Close"].iloc[-1]
            volume = df["Volume"].iloc[-1]

            # 🔥 FILTER RULES
            if price < 10:
                continue

            if volume < 1_000_000:
                continue

            move = abs(df["Close"].iloc[-1] - df["Close"].iloc[0])

            filtered.append((s, move))

        except:
            continue

    # sort by movement (fast momentum proxy)
    filtered.sort(key=lambda x: x[1], reverse=True)

    return [s[0] for s in filtered[:FILTERED_UNIVERSE]]

# =========================
# STEP 3: GET PRICES
# =========================
def get_prices(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="1h", progress=False, threads=False)

        if df is None or df.empty:
            return None

        prices = np.array(df["Close"]).astype(float).flatten()

        if len(prices) < 30:
            return None

        return prices

    except:
        return None

# =========================
# MOMENTUM
# =========================
def get_score(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return 0

    short = prices[-1] - prices[-10]
    medium = prices[-1] - prices[-20]

    return float((short * 0.6) + (medium * 0.4))

# =========================
# VOLATILITY
# =========================
def get_vol(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return 0.01

    returns = np.diff(prices) / prices[:-1]
    return max(np.std(returns[-20:]), 0.001)

# =========================
# SIGNAL ENGINE
# =========================
def get_signals():
    universe = get_universe()
    candidates = fast_filter(universe)

    ranked = []

    for s in candidates:
        try:
            score = get_score(s)
            price = api.get_latest_trade(s).price

            ranked.append({
                "symbol": s,
                "score": score,
                "price": float(price),
                "vol": get_vol(s)
            })

        except:
            continue

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

# =========================
# TRAILING STOP
# =========================
def handle_trailing():
    global peak_prices

    try:
        positions = api.list_positions()

        for p in positions:
            sym = p.symbol
            price = float(p.current_price)

            if sym not in peak_prices:
                peak_prices[sym] = price

            peak_prices[sym] = max(peak_prices[sym], price)

            drawdown = (price - peak_prices[sym]) / peak_prices[sym]

            if drawdown <= -TRAILING_STOP:
                print(f"Trailing stop: {sym}")

                api.submit_order(
                    symbol=sym,
                    qty=p.qty,
                    side="sell",
                    type="market",
                    time_in_force="day"
                )

                peak_prices.pop(sym, None)

    except:
        pass

# =========================
# ROTATION
# =========================
def handle_rotation(signals):
    try:
        positions = api.list_positions()
        top = [s["symbol"] for s in signals[:MAX_POSITIONS]]

        for p in positions:
            if p.symbol not in top:
                print(f"Rotating out: {p.symbol}")

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
# ENTRY
# =========================
def handle_entries(signals):
    try:
        account = api.get_account()
        cash = float(account.cash)

        positions = api.list_positions()
        current = [p.symbol for p in positions]

        for s in signals[:MAX_POSITIONS]:
            if s["symbol"] in current:
                continue

            risk = cash * RISK_PER_TRADE
            qty = int(risk / (s["vol"] * s["price"]))

            if qty > 0:
                print(f"Buying {s['symbol']}")

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
    print(f"Running at {datetime.utcnow()}")

    signals = get_signals()

    handle_trailing()
    handle_rotation(signals)
    handle_entries(signals)

    return signals[:5]

# =========================
# AUTO LOOP
# =========================
def scheduler():
    while True:
        run_bot()
        time.sleep(CHECK_INTERVAL)

threading.Thread(target=scheduler, daemon=True).start()

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():
    return {"signals": get_signals()[:10]}

@app.route("/run")
def run():
    return {"top": run_bot()}

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
