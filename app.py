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

MAX_DRAWDOWN = -0.10

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trading.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    time TEXT,
    symbol TEXT,
    side TEXT,
    qty REAL,
    price REAL,
    strategy TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS equity (
    time TEXT,
    equity REAL
)
""")

conn.commit()

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
# STRATEGIES
# =========================
def trend_signals(symbols):
    results = []
    for s in symbols:
        p = get_prices(s)
        if p is None or len(p) < 30:
            continue
        score = p[-1] - p[-10]
        results.append({"symbol": s, "score": score, "strategy": "trend"})
    return results

def mean_signals(symbols):
    results = []
    for s in symbols:
        p = get_prices(s)
        if p is None or len(p) < 30:
            continue
        mean = np.mean(p[-20:])
        dev = (p[-1] - mean) / mean
        results.append({"symbol": s, "score": -dev, "strategy": "mean"})
    return results

# =========================
# PERFORMANCE TRACKING
# =========================
def get_strategy_performance():
    cursor.execute("SELECT strategy, price FROM trades")
    data = cursor.fetchall()

    stats = {"trend": [], "mean": []}

    for strat, price in data:
        stats[strat].append(price)

    perf = {}
    for k, v in stats.items():
        if len(v) > 1:
            perf[k] = float(np.mean(np.diff(v)))
        else:
            perf[k] = 0.0

    return perf

def get_weights():
    perf = get_strategy_performance()
    total = sum(abs(v) for v in perf.values()) or 1

    return {k: max(v / total, 0.1) for k, v in perf.items()}

# =========================
# SIGNAL MERGE
# =========================
def get_signals():
    symbols = ["CRWD","CAT","MDB","NET","AMD","PANW","ZS","MSFT","SHOP","ROKU"]

    signals = trend_signals(symbols) + mean_signals(symbols)

    scores = np.array([s["score"] for s in signals])
    mean = np.mean(scores)
    std = np.std(scores) if np.std(scores) > 0 else 1

    for s in signals:
        s["z"] = (s["score"] - mean) / std

    return sorted(signals, key=lambda x: x["z"], reverse=True)

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
    dd = (equity - peak_equity) / peak_equity

    if dd < MAX_DRAWDOWN:
        alert("🚨 Drawdown hit. Liquidating.")
        liquidate_all()
        return False

    return True

def liquidate_all():
    for p in api.list_positions():
        try:
            api.submit_order(symbol=p.symbol, qty=p.qty,
                             side="sell", type="market",
                             time_in_force="day")
        except:
            pass

# =========================
# LOGGING
# =========================
def log_trade(symbol, side, qty, price, strategy):
    cursor.execute("INSERT INTO trades VALUES (?,?,?,?,?,?)",
                   (datetime.utcnow().isoformat(), symbol, side, qty, price, strategy))
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

    weights = get_weights()
    signals = get_signals()

    trades = 0

    for s in signals:
        if trades >= MAX_TRADES_PER_CYCLE:
            break

        if s["z"] < 0.5:
            continue

        try:
            price = api.get_latest_trade(s["symbol"]).price
            w = weights.get(s["strategy"], 0.5)

            position_value = equity * 0.02 * w
            qty = int(position_value / price)
            qty = max(1, min(qty, 50))

            api.submit_order(symbol=s["symbol"], qty=qty,
                             side="buy", type="market",
                             time_in_force="day")

            log_trade(s["symbol"], "buy", qty, price, s["strategy"])
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
# BACKTEST
# =========================
def run_backtest(symbol="AAPL", short=10, long=20):
    df = yf.download(symbol, period="6mo", interval="1d", progress=False)

    prices = df["Close"].values

    cash = 10000
    pos = 0
    equity = []

    for i in range(long, len(prices)):
        s_ma = np.mean(prices[i-short:i])
        l_ma = np.mean(prices[i-long:i])
        price = prices[i]

        if s_ma > l_ma and pos == 0:
            pos = cash / price
            cash = 0

        elif s_ma < l_ma and pos > 0:
            cash = pos * price
            pos = 0

        equity.append(cash + pos * price)

    ret = (equity[-1] - 10000) / 10000

    return {"return_pct": round(ret*100,2), "equity": equity}

def optimize():
    best = None
    best_ret = -999

    for s in [5,10,15]:
        for l in [20,30,50]:
            if s >= l:
                continue

            res = run_backtest("AAPL", s, l)
            if res["return_pct"] > best_ret:
                best_ret = res["return_pct"]
                best = (s,l)

    return {"best": best, "return": best_ret}

# =========================
# ROUTES
# =========================
@app.route("/dashboard")
def dashboard():
    cursor.execute("SELECT equity FROM equity")
    equity = [r[0] for r in cursor.fetchall()]

    return Response(f"""
<html>
<head><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head>
<body>
<h1>🚀 Full Trading System</h1>

<canvas id="eq"></canvas>

<script>
new Chart(document.getElementById('eq'), {{
    type:'line',
    data:{{
        labels:{list(range(len(equity)))},
        datasets:[{{label:'Equity',data:{equity}}}]
    }}
}});
</script>

</body>
</html>
""", mimetype="text/html")

@app.route("/backtest")
def bt():
    return jsonify(run_backtest())

@app.route("/optimize")
def opt():
    return jsonify(optimize())

@app.route("/health")
def health():
    return {"status":"running"}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
