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

# 🔥 RISK SETTINGS
MAX_DAILY_LOSS = -0.05      # -5%
MAX_DRAWDOWN = -0.10        # -10%
MAX_EXPOSURE = 0.80         # 80% capital deployed
MAX_TRADES_PER_CYCLE = 3

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trading.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS equity (time TEXT, equity REAL)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS trades (time TEXT, symbol TEXT, side TEXT, qty REAL, price REAL)""")
conn.commit()

# =========================
# STATE
# =========================
start_equity = None
peak_equity = None
last_trade_cycle = 0

# =========================
# ALERT
# =========================
def alert(msg):
    print(msg)
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": msg})
        except:
            pass

# =========================
# LOGGING
# =========================
def log_equity(value):
    cursor.execute("INSERT INTO equity VALUES (?,?)", (datetime.utcnow().isoformat(), value))
    conn.commit()

def log_trade(symbol, side, qty, price):
    cursor.execute("INSERT INTO trades VALUES (?,?,?,?,?)",
                   (datetime.utcnow().isoformat(), symbol, side, qty, price))
    conn.commit()

# =========================
# ANALYTICS
# =========================
def get_equity_history():
    cursor.execute("SELECT equity FROM equity ORDER BY rowid ASC")
    return [r[0] for r in cursor.fetchall()]

def get_drawdown(equity):
    peak = equity[0] if equity else 0
    dd = []
    for e in equity:
        peak = max(peak, e)
        dd.append((e - peak)/peak if peak else 0)
    return dd

# =========================
# RISK ENGINE
# =========================
def risk_check():
    global start_equity, peak_equity

    account = api.get_account()
    equity = float(account.equity)

    if start_equity is None:
        start_equity = equity
        peak_equity = equity

    # update peak
    peak_equity = max(peak_equity, equity)

    daily_change = (equity - start_equity) / start_equity
    drawdown = (equity - peak_equity) / peak_equity

    # exposure
    positions = api.list_positions()
    exposure = sum(float(p.market_value) for p in positions) / equity if equity > 0 else 0

    if daily_change <= MAX_DAILY_LOSS:
        alert("🚨 Max daily loss hit. Trading halted.")
        return False

    if drawdown <= MAX_DRAWDOWN:
        alert("🚨 Max drawdown hit. Liquidating.")
        liquidate_all()
        return False

    if exposure >= MAX_EXPOSURE:
        alert("⚠️ Exposure too high. Blocking new trades.")
        return False

    return True

# =========================
# LIQUIDATION
# =========================
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
# SIGNALS (SIMPLE)
# =========================
def get_signals():
    symbols = ["CRWD","CAT","MDB","NET","AMD","PANW","ZS","MSFT"]
    data = []

    for s in symbols:
        try:
            df = yf.download(s, period="2d", interval="1h", progress=False)
            if df.empty:
                continue

            move = df["Close"].iloc[-1] - df["Close"].iloc[0]
            data.append({"symbol": s, "score": float(move)})
        except:
            continue

    return sorted(data, key=lambda x: x["score"], reverse=True)

# =========================
# BOT
# =========================
def run_bot():
    global last_trade_cycle

    if not risk_check():
        return

    signals = get_signals()

    trades = 0

    for s in signals[:3]:
        if trades >= MAX_TRADES_PER_CYCLE:
            break

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
            trades += 1

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
    equity = get_equity_history()
    drawdown = get_drawdown(equity)

    return jsonify({
        "equity": equity,
        "drawdown": drawdown,
        "signals": get_signals()
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
<h1>🚀 Risk-Aware Dashboard</h1>
<canvas id="equity"></canvas>
<canvas id="dd"></canvas>

<script>
async function load(){
    const r = await fetch('/data');
    const d = await r.json();

    draw('equity', d.equity);
    draw('dd', d.drawdown);
}

function draw(id,data){
    new Chart(document.getElementById(id), {
        type:'line',
        data:{
            labels:data.map((_,i)=>i),
            datasets:[{data:data}]
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
