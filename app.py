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
CACHE_TTL = 120

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trading.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    symbol TEXT,
    side TEXT,
    qty REAL,
    price REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    equity REAL
)
""")

conn.commit()

# =========================
# CACHE
# =========================
price_cache = {}

def clean_array(arr):
    arr = np.array(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr if len(arr) > 30 else None

def get_prices(symbol):
    now = time.time()

    if symbol in price_cache:
        data, ts = price_cache[symbol]
        if now - ts < CACHE_TTL:
            return data

    try:
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df is None or df.empty:
            return None

        prices = clean_array(df["Close"])
        if prices is None:
            return None

        price_cache[symbol] = (prices, now)
        return prices
    except:
        return None

def ema(prices, span=20):
    alpha = 2/(span+1)
    e = [prices[0]]
    for p in prices[1:]:
        e.append(alpha*p + (1-alpha)*e[-1])
    return np.array(e)

# =========================
# REGIME
# =========================
def get_regime():
    prices = get_prices("SPY")
    if prices is None:
        return "neutral"

    smooth = ema(prices)
    return "bull" if smooth[-1] > smooth[-10] else "bear"

# =========================
# SIGNALS
# =========================
def get_signals():
    symbols = ["CRWD","CAT","MDB","NET","AMD","PANW","ZS","MSFT","SHOP","ROKU"]
    results = []

    for s in symbols:
        prices = get_prices(s)
        if prices is None:
            continue

        score = prices[-1] - prices[-10]
        results.append({"symbol": s, "score": float(score)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

# =========================
# ALERTS
# =========================
def send_alert(msg):
    print(msg)

    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": msg})
        except:
            pass

# =========================
# LOGGING
# =========================
def log_trade(symbol, side, qty, price):
    cursor.execute(
        "INSERT INTO trades (time, symbol, side, qty, price) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), symbol, side, qty, price)
    )
    conn.commit()

    send_alert(f"{side.upper()} {symbol} qty={qty} @ {price}")

def log_equity(value):
    cursor.execute(
        "INSERT INTO equity (time, equity) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), value)
    )
    conn.commit()

# =========================
# ANALYTICS
# =========================
def get_equity_curve():
    cursor.execute("SELECT equity FROM equity ORDER BY id ASC")
    return [row[0] for row in cursor.fetchall()]

def get_drawdown(equity):
    peak = equity[0] if equity else 0
    dd = []
    for e in equity:
        peak = max(peak, e)
        dd.append((e - peak) / peak if peak > 0 else 0)
    return dd

# =========================
# BOT
# =========================
def run_bot():
    signals = get_signals()

    if get_regime() == "bull":
        for s in signals[:2]:
            try:
                price = api.get_latest_trade(s["symbol"]).price

                api.submit_order(
                    symbol=s["symbol"],
                    qty=1,
                    side="buy",
                    type="market",
                    time_in_force="day"
                )

                log_trade(s["symbol"], "buy", 1, price)

            except:
                continue

    # log equity
    try:
        account = api.get_account()
        log_equity(float(account.equity))
    except:
        pass

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
    equity = get_equity_curve()
    drawdown = get_drawdown(equity)

    cursor.execute("SELECT symbol, side, qty, price FROM trades ORDER BY id DESC LIMIT 20")
    trades = cursor.fetchall()

    return jsonify({
        "equity": equity,
        "drawdown": drawdown,
        "signals": get_signals(),
        "trades": trades,
        "regime": get_regime()
    })

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    return Response("""
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>

<h1>🚀 Pro Trading Dashboard</h1>
<h2 id="stats"></h2>

<canvas id="equity"></canvas>
<canvas id="dd"></canvas>

<script>
async function load(){
    const r = await fetch('/data');
    const d = await r.json();

    document.getElementById("stats").innerHTML =
        "Regime: " + d.regime;

    draw('equity', d.equity, 'Equity');
    draw('dd', d.drawdown, 'Drawdown');
}

function draw(id,data,label){
    new Chart(document.getElementById(id), {
        type:'line',
        data:{
            labels:data.map((_,i)=>i),
            datasets:[{label:label,data:data}]
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
