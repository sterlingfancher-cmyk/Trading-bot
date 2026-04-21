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

TRAILING_STOP = 0.03
CHECK_INTERVAL = 300

MAX_DAILY_LOSS = -0.05   # -5% account stop

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

peak_prices = {}
daily_start_equity = None

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
# EMA SMOOTHING
# =========================
def ema(prices, span=10):
    alpha = 2 / (span + 1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(alpha * p + (1 - alpha) * ema_vals[-1])
    return np.array(ema_vals)

# =========================
# MOMENTUM (IMPROVED)
# =========================
def get_momentum_score(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return 0

    smooth = ema(prices, span=10)

    short = smooth[-1] - smooth[-10]
    medium = smooth[-1] - smooth[-20]

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
# RISK CONTROL (ACCOUNT LEVEL)
# =========================
def risk_check():
    global daily_start_equity

    account = api.get_account()
    equity = float(account.equity)

    if daily_start_equity is None:
        daily_start_equity = equity
        return True

    change = (equity - daily_start_equity) / daily_start_equity

    if change <= MAX_DAILY_LOSS:
        print("MAX DAILY LOSS HIT — STOPPING TRADING")
        return False

    return True

# =========================
# TRAILING STOP
# =========================
def handle_trailing_stops():
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
# ROTATION (LONG)
# =========================
def handle_long_rotation(signals):
    try:
        positions = api.list_positions()
        top_longs = [s["symbol"] for s in signals[:MAX_POSITIONS] if s["score"] >= MIN_SCORE]

        for p in positions:
            if p.side == "long" and p.symbol not in top_longs:
                print(f"Exit long: {p.symbol}")

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
# SHORT SYSTEM
# =========================
def handle_shorts(signals):
    try:
        positions = api.list_positions()
        current = [p.symbol for p in positions]

        weakest = [s for s in signals if s["score"] < -MIN_SCORE]
        weakest = weakest[-2:]  # bottom 2

        for s in weakest:
            if s["symbol"] in current:
                continue

            qty = 1  # keep shorts small for now

            print(f"Shorting {s['symbol']}")

            api.submit_order(
                symbol=s["symbol"],
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )

    except:
        pass

# =========================
# ENTRY (LONG)
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
# BOT
# =========================
def run_bot():
    print(f"Running bot at {datetime.utcnow()}")

    if not risk_check():
        return {"status": "risk halted"}

    signals = get_signals()

    handle_trailing_stops()
    handle_long_rotation(signals)
    handle_entries(signals)
    handle_shorts(signals)

    return {"top": signals[:5]}

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
    return {"signals": get_signals()}

@app.route("/run")
def run():
    return run_bot()

@app.route("/health")
def health():
    return {"status": "running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
