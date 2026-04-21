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
SYMBOLS = [
    "AMD","NVDA","META","AVGO","INTC",
    "AAPL","MSFT","GOOGL","AMZN","TSLA",
    "SMCI","ARM","TSM","NFLX","CRM",
    "QCOM","ADBE","NOW","PANW","SNOW"
]

MAX_POSITIONS = 5
RISK_PER_TRADE = 0.02
MIN_SCORE = 1.0

TRAILING_STOP = 0.03   # 3% trailing stop
CHECK_INTERVAL = 300   # 5 minutes

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

# store peak prices
peak_prices = {}

# =========================
# DATA
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
def get_momentum_score(symbol):
    prices = get_prices(symbol)

    if prices is None:
        return 0

    short = prices[-1] - prices[-10]
    medium = prices[-1] - prices[-20]

    return float((short * 0.6) + (medium * 0.4))

# =========================
# VOLATILITY
# =========================
def get_volatility(symbol):
    prices = get_prices(symbol)

    if prices is None:
        return 0.01

    returns = np.diff(prices) / prices[:-1]
    return max(np.std(returns[-20:]), 0.001)

# =========================
# SIGNALS
# =========================
def get_signals():
    ranked = []

    for s in SYMBOLS:
        try:
            score = get_momentum_score(s)
            price = api.get_latest_trade(s).price

            ranked.append({
                "symbol": s,
                "score": score,
                "price": float(price),
                "vol": get_volatility(s)
            })
        except:
            continue

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

# =========================
# TRAILING STOP LOGIC
# =========================
def handle_trailing_stops():
    global peak_prices

    try:
        positions = api.list_positions()

        for p in positions:
            symbol = p.symbol
            current_price = float(p.current_price)

            # update peak
            if symbol not in peak_prices:
                peak_prices[symbol] = current_price

            peak_prices[symbol] = max(peak_prices[symbol], current_price)

            drawdown = (current_price - peak_prices[symbol]) / peak_prices[symbol]

            if drawdown <= -TRAILING_STOP:
                print(f"Trailing stop hit: {symbol}")

                api.submit_order(
                    symbol=symbol,
                    qty=p.qty,
                    side="sell",
                    type="market",
                    time_in_force="day"
                )

                peak_prices.pop(symbol, None)

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
        current_symbols = [p.symbol for p in positions]

        candidates = [s for s in signals if s["score"] >= MIN_SCORE]
        candidates = candidates[:MAX_POSITIONS]

        for s in candidates:
            if s["symbol"] in current_symbols:
                continue

            if len(current_symbols) >= MAX_POSITIONS:
                break

            risk = cash * RISK_PER_TRADE
            vol = s["vol"]

            qty = int(risk / (vol * s["price"]))

            if qty > 0:
                print(f"Buying {s['symbol']}")

                api.submit_order(
                    symbol=s["symbol"],
                    qty=qty,
                    side="buy",
                    type="market",
                    time_in_force="day"
                )

                current_symbols.append(s["symbol"])

    except:
        pass

# =========================
# EXIT (WEAK SIGNALS)
# =========================
def handle_exits(signals):
    try:
        positions = api.list_positions()
        signal_map = {s["symbol"]: s for s in signals}

        for p in positions:
            sym = p.symbol

            if sym not in signal_map or signal_map[sym]["score"] < 0:
                print(f"Exiting weak: {sym}")

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
# MAIN LOOP
# =========================
def run_bot():
    print(f"Running bot at {datetime.utcnow()}")

    signals = get_signals()

    handle_trailing_stops()
    handle_exits(signals)
    handle_entries(signals)

# =========================
# AUTO RUN THREAD
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
    return {"signals": get_signals()}

@app.route("/run")
def run():
    run_bot()
    return {"status": "ran"}

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
