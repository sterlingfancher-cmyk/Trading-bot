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
BASE_URL = "https://paper-api.alpaca.markets"
API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

api = REST(API_KEY, API_SECRET, BASE_URL)

CHECK_INTERVAL = 300
CACHE_TTL = 120
TRAILING_STOP = 0.03

# =========================
# STATE
# =========================
price_cache = {}
equity_history = []
pnl_curve = []
drawdown_curve = []
trade_log = []
start_equity = None
peak_equity = None

# =========================
# DATA
# =========================
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
# TRADE LOGGING
# =========================
def log_trade(symbol, side, qty, price):
    trade_log.append({
        "time": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price
    })

    if len(trade_log) > 200:
        trade_log.pop(0)

# =========================
# ANALYTICS
# =========================
def update_equity():
    global start_equity, peak_equity

    account = api.get_account()
    equity = float(account.equity)

    if start_equity is None:
        start_equity = equity
        peak_equity = equity

    equity_history.append(equity)

    pnl = (equity - start_equity)
    pnl_curve.append(pnl)

    peak_equity = max(peak_equity, equity)
    drawdown = (equity - peak_equity) / peak_equity
    drawdown_curve.append(drawdown)

    if len(equity_history) > 200:
        equity_history.pop(0)
        pnl_curve.pop(0)
        drawdown_curve.pop(0)

# =========================
# BOT (CONNECTED)
# =========================
def run_bot():
    signals = get_signals()

    # Example trade logic (simple)
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

    update_equity()

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
    return jsonify({
        "equity": equity_history,
        "pnl": pnl_curve,
        "drawdown": drawdown_curve,
        "signals": get_signals(),
        "trades": trade_log,
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

<h1>📊 Trading Dashboard</h1>
<h2 id="stats"></h2>

<canvas id="equity"></canvas>
<canvas id="pnl"></canvas>
<canvas id="dd"></canvas>

<script>
async function load(){
    const r = await fetch('/data');
    const d = await r.json();

    document.getElementById("stats").innerHTML =
        "Regime: " + d.regime;

    drawChart('equity', d.equity, 'Equity');
    drawChart('pnl', d.pnl, 'PnL');
    drawChart('dd', d.drawdown, 'Drawdown');
}

function drawChart(id,data,label){
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
