import os
import time
import threading
import sqlite3
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, Response
from alpaca_trade_api import REST
import requests

app = Flask(__name__)

# =========================
# CONFIG
# =========================
BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")

api = REST(API_KEY, API_SECRET, BASE_URL)

CHECK_INTERVAL = 300
MAX_TRADES_PER_CYCLE = 4

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trading.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS equity (time TEXT, equity REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS trades (time TEXT, symbol TEXT, side TEXT, qty REAL, price REAL)")
conn.commit()

# =========================
# UTIL
# =========================
def alert(msg):
    print(msg)
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": msg})
        except:
            pass

# =========================
# DATA
# =========================
def get_prices(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df.empty:
            return None
        return np.array(df["Close"]).astype(float)
    except:
        return None

# =========================
# STRATEGY 1: TREND
# =========================
def trend_signals(symbols):
    results = []

    for s in symbols:
        prices = get_prices(s)
        if prices is None or len(prices) < 30:
            continue

        score = prices[-1] - prices[-10]
        results.append({"symbol": s, "score": score, "type": "trend"})

    return results

# =========================
# STRATEGY 2: MEAN REVERSION
# =========================
def mean_reversion_signals(symbols):
    results = []

    for s in symbols:
        prices = get_prices(s)
        if prices is None or len(prices) < 30:
            continue

        mean = np.mean(prices[-20:])
        deviation = (prices[-1] - mean) / mean

        # negative deviation = oversold
        score = -deviation
        results.append({"symbol": s, "score": score, "type": "mean"})

    return results

# =========================
# MERGE STRATEGIES
# =========================
def get_combined_signals():
    symbols = ["CRWD","CAT","MDB","NET","AMD","PANW","ZS","MSFT","SHOP","ROKU"]

    trend = trend_signals(symbols)
    mean = mean_reversion_signals(symbols)

    combined = trend + mean

    # normalize scores
    scores = np.array([s["score"] for s in combined])
    mean_val = np.mean(scores)
    std = np.std(scores) if np.std(scores) > 0 else 1

    for s in combined:
        s["z"] = (s["score"] - mean_val) / std

    return sorted(combined, key=lambda x: x["z"], reverse=True)

# =========================
# RISK ENGINE
# =========================
start_equity = None
peak_equity = None

def risk_check():
    global start_equity, peak_equity

    account = api.get_account()
    equity = float(account.equity)

    if start_equity is None:
        start_equity = equity
        peak_equity = equity

    peak_equity = max(peak_equity, equity)

    drawdown = (equity - peak_equity) / peak_equity

    if drawdown < -0.1:
        alert("🚨 Max drawdown hit. Liquidating.")
        liquidate_all()
        return False

    return True

def liquidate_all():
    for p in api.list_positions():
        try:
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
# LOGGING
# =========================
def log_trade(symbol, side, qty, price):
    cursor.execute("INSERT INTO trades VALUES (?,?,?,?,?)",
                   (datetime.utcnow().isoformat(), symbol, side, qty, price))
    conn.commit()

def log_equity(value):
    cursor.execute("INSERT INTO equity VALUES (?,?)",
                   (datetime.utcnow().isoformat(), value))
    conn.commit()

# =========================
# BOT
# =========================
def run_bot():
    if not risk_check():
        return

    account = api.get_account()
    equity = float(account.equity)

    signals = get_combined_signals()

    trades = 0

    for s in signals:
        if trades >= MAX_TRADES_PER_CYCLE:
            break

        if s["z"] < 0.5:
            continue

        try:
            price = api.get_latest_trade(s["symbol"]).price

            position_value = equity * 0.02
            qty = int(position_value / price)
            qty = max(1, min(qty, 50))

            api.submit_order(
                symbol=s["symbol"],
                qty=qty,
                side="buy",
                type="market",
                time_in_force="day"
            )

            log_trade(s["symbol"], "buy", qty, price)
            trades += 1

        except:
            continue

    log_equity(equity)

# =========================
# LOOP
# =========================
def scheduler():
    while True:
        run_bot()
        time.sleep(CHECK_INTERVAL)

threading.Thread(target=scheduler, daemon=True).start()

# =========================
# DATA API
# =========================
@app.route("/data")
def data():
    cursor.execute("SELECT equity FROM equity")
    equity = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT symbol, side, qty, price FROM trades ORDER BY rowid DESC LIMIT 20")
    trades = cursor.fetchall()

    return jsonify({
        "equity": equity,
        "signals": get_combined_signals()[:10],
        "trades": trades
    })

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    return Response("""
<html>
<head><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head>
<body>
<h1>🚀 Multi-Strategy Dashboard</h1>
<canvas id="equity"></canvas>

<script>
async function load(){
    const r = await fetch('/data');
    const d = await r.json();

    new Chart(document.getElementById('equity'), {
        type:'line',
        data:{
            labels:d.equity.map((_,i)=>i),
            datasets:[{label:'Equity',data:d.equity}]
        }
    });
}

setInterval(load,5000);
load();
</script>
</body>
</html>
""", mimetype="text/html")

# =========================
# HEALTH
# =========================
@app.route("/health")
def health():
    return {"status":"running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
