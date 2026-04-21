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
MAX_POSITIONS = 5
FILTERED_UNIVERSE = 20

RISK_PER_TRADE = 0.02
TRAILING_STOP = 0.03
CHECK_INTERVAL = 300

MIN_SCORE = 1.0
ROTATION_BUFFER = 0.5
TRADE_COOLDOWN = 900
CACHE_TTL = 120

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

peak_prices = {}
last_trade_time = {}
price_cache = {}

# =========================
# CACHE
# =========================
def get_cached_prices(symbol):
    now = time.time()

    if symbol in price_cache:
        data, ts = price_cache[symbol]
        if now - ts < CACHE_TTL:
            return data

    try:
        df = yf.download(symbol, period="5d", interval="1h", progress=False, threads=False)
        if df is None or df.empty:
            return None

        prices = np.array(df["Close"]).astype(float).flatten()

        if len(prices) < 30:
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
# REGIME FILTER (SPY)
# =========================
def get_market_regime():
    prices = get_cached_prices("SPY")

    if prices is None:
        return "neutral"

    smooth = ema(prices, span=20)

    if smooth[-1] > smooth[-10]:
        return "bull"

    if smooth[-1] < smooth[-10]:
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
# FAST FILTER
# =========================
def fast_filter(symbols):
    results = []

    for s in symbols:
        prices = get_cached_prices(s)
        if prices is None:
            continue

        price = prices[-1]
        move = abs(prices[-1] - prices[-10])

        if price < 10:
            continue

        results.append((s, move))

    results.sort(key=lambda x: x[1], reverse=True)

    filtered = [r[0] for r in results[:FILTERED_UNIVERSE]]

    if len(filtered) == 0:
        return symbols[:FILTERED_UNIVERSE]

    return filtered

# =========================
# SCORE
# =========================
def get_score(symbol):
    prices = get_cached_prices(symbol)
    if prices is None:
        return None

    smooth = ema(prices)

    short = smooth[-1] - smooth[-10]
    medium = smooth[-1] - smooth[-20]

    return float((short * 0.6) + (medium * 0.4))

# =========================
# VOL
# =========================
def get_vol(symbol):
    prices = get_cached_prices(symbol)
    if prices is None:
        return 0.01

    returns = np.diff(prices) / prices[:-1]
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
            if score is None:
                continue

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

    if len(ranked) == 0:
        return [{"symbol":"AMD","score":1,"price":100,"vol":1}]

    return ranked

# =========================
# PREFLIGHT
# =========================
def preflight(signals):
    if len(signals) == 0:
        return False

    scores = [s["score"] for s in signals]

    if np.std(scores) < 0.01:
        return False

    return True

# =========================
# TRAILING
# =========================
def handle_trailing():
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

# =========================
# ROTATION
# =========================
def handle_rotation(signals):
    positions = api.list_positions()
    top = signals[:MAX_POSITIONS]

    top_symbols = [s["symbol"] for s in top]
    signal_map = {s["symbol"]: s for s in signals}

    for p in positions:
        sym = p.symbol

        if sym not in top_symbols:
            current_score = signal_map.get(sym, {}).get("score", -999)
            best_score = top[-1]["score"]

            if best_score - current_score > ROTATION_BUFFER:
                print(f"Rotating out: {sym}")

                api.submit_order(
                    symbol=sym,
                    qty=p.qty,
                    side="sell",
                    type="market",
                    time_in_force="day"
                )

                peak_prices.pop(sym, None)

# =========================
# ENTRY (WEIGHTED + REGIME)
# =========================
def handle_entries(signals):
    regime = get_market_regime()

    if regime == "bear":
        print("Bear regime — skipping entries")
        return

    account = api.get_account()
    cash = float(account.cash)

    positions = api.list_positions()
    current = [p.symbol for p in positions]

    top = [s for s in signals if s["score"] >= MIN_SCORE][:MAX_POSITIONS]

    scores = np.array([max(s["score"], 0) for s in top])
    total_score = np.sum(scores)

    if total_score == 0:
        return

    now = time.time()

    for s, score in zip(top, scores):
        sym = s["symbol"]

        if sym in current:
            continue

        if sym in last_trade_time:
            if now - last_trade_time[sym] < TRADE_COOLDOWN:
                continue

        weight = score / total_score

        allocation = cash * weight
        qty = int(allocation / s["price"])
        qty = min(qty, 100)

        if qty > 0:
            print(f"Buying {sym} weight {round(weight,2)}")

            api.submit_order(
                symbol=sym,
                qty=qty,
                side="buy",
                type="market",
                time_in_force="day"
            )

            last_trade_time[sym] = now

# =========================
# BOT
# =========================
def run_bot():
    print(f"Run: {datetime.utcnow()}")

    signals = get_signals()

    if not preflight(signals):
        print("Blocked by preflight")
        return {"status": "blocked"}

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
    return {
        "signals": get_signals()[:10],
        "regime": get_market_regime()
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
