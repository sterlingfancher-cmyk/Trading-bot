import os
import time
import threading
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify
from alpaca_trade_api import REST
import pytz

app = Flask(__name__)

# =========================
# CONFIG
# =========================
MAX_POSITIONS = 5
FILTERED_UNIVERSE = 20

TARGET_VOL = 0.02           # 🔥 portfolio risk target
REBALANCE_THRESHOLD = 0.25  # 🔥 only rebalance if weight drift > 25%
PULLBACK_THRESHOLD = 0.02   # 🔥 require small pullback to enter

TRAILING_STOP = 0.03
CHECK_INTERVAL = 300

MIN_SCORE = 1.0
CACHE_TTL = 120

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

price_cache = {}
peak_prices = {}

# =========================
# MARKET HOURS
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

# =========================
# CLEAN DATA
# =========================
def clean_array(arr):
    arr = np.array(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr if len(arr) > 30 else None

# =========================
# CACHE
# =========================
def get_prices(symbol):
    now = time.time()

    if symbol in price_cache:
        data, ts = price_cache[symbol]
        if now - ts < CACHE_TTL:
            return data

    try:
        df = yf.download(symbol, period="5d", interval="1h", progress=False, threads=False)
        if df is None or df.empty:
            return None

        prices = clean_array(df["Close"])
        if prices is None:
            return None

        price_cache[symbol] = (prices, now)
        return prices

    except:
        return None

# =========================
# EMA
# =========================
def ema(prices, span=20):
    alpha = 2 / (span + 1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(alpha * p + (1 - alpha) * ema_vals[-1])
    return np.array(ema_vals)

# =========================
# REGIME
# =========================
def get_market_regime():
    prices = get_prices("SPY")
    if prices is None:
        return "neutral"

    smooth = ema(prices)

    if smooth[-1] > smooth[-10]:
        return "bull"
    elif smooth[-1] < smooth[-10]:
        return "bear"
    return "neutral"

# =========================
# UNIVERSE
# =========================
def get_universe():
    return [
        "AMD","NVDA","META","AVGO","INTC",
        "AAPL","MSFT","GOOGL","AMZN","TSLA",
        "SMCI","ARM","TSM","NFLX","CRM",
        "QCOM","ADBE","NOW","PANW","SNOW",
        "PLTR","UBER","COIN","SQ","PYPL",
        "SHOP","ROKU","DDOG","NET","CRWD",
        "ZS","OKTA","TEAM","MDB","F","GM",
        "BA","CAT","GE"
    ]

# =========================
# FILTER
# =========================
def fast_filter(symbols):
    results = []

    for s in symbols:
        prices = get_prices(s)
        if prices is None:
            continue

        move = abs(prices[-1] - prices[-10])

        if prices[-1] < 10:
            continue

        results.append((s, move))

    results.sort(key=lambda x: x[1], reverse=True)
    return [r[0] for r in results[:FILTERED_UNIVERSE]] or symbols[:FILTERED_UNIVERSE]

# =========================
# SCORE
# =========================
def get_score(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return None

    smooth = ema(prices)

    short = smooth[-1] - smooth[-10]
    medium = smooth[-1] - smooth[-20]

    score = (short * 0.6) + (medium * 0.4)

    return float(score) if np.isfinite(score) else None

# =========================
# VOL
# =========================
def get_vol(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return None

    returns = np.diff(prices) / prices[:-1]
    returns = returns[np.isfinite(returns)]

    if len(returns) < 10:
        return None

    return max(np.std(returns[-20:]), 0.001)

# =========================
# SIGNALS
# =========================
def get_signals():
    universe = get_universe()
    candidates = fast_filter(universe)

    ranked = []

    for s in candidates:
        try:
            score = get_score(s)
            vol = get_vol(s)

            if score is None or vol is None:
                continue

            price = api.get_latest_trade(s).price

            ranked.append({
                "symbol": s,
                "score": score,
                "price": float(price),
                "vol": vol
            })

        except:
            continue

    ranked.sort(key=lambda x: x["score"], reverse=True)

    return ranked if ranked else [{"symbol":"AMD","score":1,"price":100,"vol":1}]

# =========================
# ENTRY FILTER (PULLBACK)
# =========================
def valid_entry(symbol):
    prices = get_prices(symbol)
    if prices is None:
        return False

    smooth = ema(prices)
    pullback = (prices[-1] - smooth[-1]) / smooth[-1]

    return pullback < PULLBACK_THRESHOLD

# =========================
# TRAILING
# =========================
def handle_trailing():
    for p in api.list_positions():
        sym = p.symbol
        price = float(p.current_price)

        peak_prices[sym] = max(peak_prices.get(sym, price), price)

        drawdown = (price - peak_prices[sym]) / peak_prices[sym]

        if drawdown <= -TRAILING_STOP:
            api.submit_order(symbol=sym, qty=p.qty, side="sell", type="market", time_in_force="day")
            peak_prices.pop(sym, None)

# =========================
# ENTRY (OPTIMIZED)
# =========================
def handle_entries(signals):
    if not market_open():
        return

    if get_market_regime() == "bear":
        return

    account = api.get_account()
    equity = float(account.equity)

    positions = api.list_positions()
    current = [p.symbol for p in positions]

    top = [s for s in signals if s["score"] >= MIN_SCORE][:MAX_POSITIONS]

    scores = np.array([s["score"] for s in top])
    weights = scores / np.sum(scores)

    for s, w in zip(top, weights):
        if s["symbol"] in current:
            continue

        if not valid_entry(s["symbol"]):
            continue

        # 🔥 volatility targeting
        position_value = equity * TARGET_VOL / s["vol"]

        qty = int(position_value / s["price"])
        qty = min(qty, 100)

        if qty > 0:
            api.submit_order(symbol=s["symbol"], qty=qty, side="buy", type="market", time_in_force="day")

# =========================
# BOT
# =========================
def run_bot():
    signals = get_signals()

    handle_trailing()
    handle_entries(signals)

    return signals[:5]

# =========================
# LOOP
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
    return {
        "regime": get_market_regime(),
        "signals": get_signals()[:10]
    }

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
