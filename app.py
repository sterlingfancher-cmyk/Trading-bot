import os
import time
import threading
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, Response
from alpaca_trade_api import REST
import pytz
import json

app = Flask(__name__)

# =========================
# CONFIG
# =========================
MAX_POSITIONS = 5
FILTERED_UNIVERSE = 20

TARGET_VOL = 0.02
TRAILING_STOP = 0.03
CHECK_INTERVAL = 300

MIN_SCORE = 1.0
CACHE_TTL = 120
PULLBACK_THRESHOLD = 0.02

BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

# =========================
# STATE
# =========================
price_cache = {}
peak_prices = {}
trade_log = []
equity_history = []
start_equity = None
closed_trades = []

# =========================
# UTIL
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

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
    return ranked if ranked else []

# =========================
# TRADE LOGGING
# =========================
def log_trade(symbol, side, qty, price):
    trade_log.append({
        "time": str(datetime.utcnow()),
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price
    })

# =========================
# ANALYTICS
# =========================
def get_stats():
    wins = 0
    losses = 0
    profits = []

    for t in closed_trades:
        pnl = t["pnl"]
        profits.append(pnl)
        if pnl > 0:
            wins += 1
        else:
            losses += 1

    total = wins + losses

    return {
        "total_trades": total,
        "win_rate": round((wins / total)*100, 2) if total > 0 else 0,
        "avg_pnl": round(np.mean(profits), 2) if profits else 0,
        "max_drawdown": round(min(profits), 2) if profits else 0
    }

# =========================
# BOT CORE
# =========================
def run_bot():
    global start_equity

    account = api.get_account()
    equity = float(account.equity)

    if start_equity is None:
        start_equity = equity

    equity_history.append(equity)
    if len(equity_history) > 200:
        equity_history.pop(0)

    signals = get_signals()

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
# DASHBOARD UI
# =========================
@app.route("/dashboard")
def dashboard():
    stats = get_stats()
    signals = get_signals()[:5]
    regime = get_market_regime()

    html = f"""
    <html>
    <head><title>Trading Dashboard</title></head>
    <body>
    <h1>🚀 Trading Dashboard</h1>
    <p><b>Regime:</b> {regime}</p>

    <h2>📊 Performance</h2>
    <p>Trades: {stats['total_trades']}</p>
    <p>Win Rate: {stats['win_rate']}%</p>
    <p>Avg PnL: {stats['avg_pnl']}</p>

    <h2>📈 Signals</h2>
    {json.dumps(signals, indent=2)}

    <h2>🧾 Trades</h2>
    {json.dumps(trade_log[-10:], indent=2)}

    </body>
    </html>
    """
    return Response(html, mimetype='text/html')

# =========================
# ROUTES
# =========================
@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/debug")
def debug():
    return {
        "regime": get_market_regime(),
        "signals": get_signals()[:10],
        "stats": get_stats()
    }

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
