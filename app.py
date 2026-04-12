from flask import Flask
import pandas as pd
import os
import sqlite3
from datetime import datetime
import subprocess
import sys
import threading
import time

app = Flask(__name__)

# =========================
# DEPENDENCIES
# =========================
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "alpaca-py", "yfinance", "pandas"])
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    import yfinance as yf

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
MAX_POSITIONS = 3
RISK_PER_TRADE = 0.1

STOP_LOSS = 0.93
TAKE_PROFIT = 1.18

# 🔥 ENV CONTROL (this is what we are debugging)
AUTO_TRADING = os.environ.get("AUTO_TRADING", "false").lower() == "true"

# =========================
# CLIENT
# =========================
trading_client = TradingClient(
    os.environ.get("ALPACA_API_KEY"),
    os.environ.get("ALPACA_SECRET_KEY"),
    paper=True
)

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trades.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    side TEXT,
    price REAL,
    qty INTEGER,
    timestamp TEXT
)
""")
conn.commit()

# =========================
# MARKET HOURS
# =========================
def market_is_open():
    clock = trading_client.get_clock()
    return clock.is_open

# =========================
# DATA
# =========================
def load_data(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", auto_adjust=True)

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if "Close" not in df.columns or len(df) < 30:
            return None

        df["ma"] = df["Close"].rolling(20).mean()
        df["momentum"] = df["Close"] / df["Close"].shift(10)
        df = df.dropna()

        return df

    except:
        return None

# =========================
# SIGNALS
# =========================
def get_signals():
    spy = load_data("SPY")
    if spy is None:
        return "error", []

    spy_close = float(spy["Close"].values[-1])
    spy_ma = float(spy["ma"].values[-1])

    if spy_close <= spy_ma:
        return "bearish", []

    scores = []

    for symbol in SYMBOLS:
        df = load_data(symbol)
        if df is None:
            continue

        price = float(df["Close"].values[-1])
        ma = float(df["ma"].values[-1])
        momentum = float(df["momentum"].values[-1])

        if price > ma:
            scores.append((symbol, momentum, price))

    ranked = sorted(scores, key=lambda x: x[1], reverse=True)
    signals = [{"symbol": s, "price": p} for s,_,p in ranked[:3]]

    return "bullish", signals

# =========================
# POSITION SIZE
# =========================
def calculate_qty(price):
    account = trading_client.get_account()
    buying_power = float(account.buying_power)
    allocation = buying_power * RISK_PER_TRADE
    return max(int(allocation // price), 1)

# =========================
# BUY
# =========================
def buy(symbol, price):
    qty = calculate_qty(price)

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC
    )

    trading_client.submit_order(order)

    c.execute(
        "INSERT INTO trades VALUES (NULL,?,?,?,?,?)",
        (symbol,"BUY",price,qty,datetime.now())
    )
    conn.commit()

# =========================
# MANAGE POSITIONS
# =========================
def manage_positions():
    positions = trading_client.get_all_positions()

    for p in positions:
        symbol = p.symbol
        entry = float(p.avg_entry_price)
        current = float(p.current_price)
        change = current / entry

        if change <= STOP_LOSS or change >= TAKE_PROFIT:

            order = MarketOrderRequest(
                symbol=symbol,
                qty=int(float(p.qty)),
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC
            )

            trading_client.submit_order(order)

# =========================
# AUTO LOOP
# =========================
def auto_trader():
    while True:
        try:
            if AUTO_TRADING and market_is_open():

                market, signals = get_signals()

                if market == "bullish":
                    positions = trading_client.get_all_positions()
                    held = [p.symbol for p in positions]

                    for s in signals:
                        if s["symbol"] not in held and len(held) < MAX_POSITIONS:
                            buy(s["symbol"], s["price"])

                manage_positions()

        except Exception as e:
            print("AUTO ERROR:", e)

        time.sleep(300)

# =========================
# START THREAD
# =========================
threading.Thread(target=auto_trader, daemon=True).start()

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {
        "status":"running",
        "auto_trading":AUTO_TRADING,
        "market_open": market_is_open()
    }

@app.route("/env")
def env():
    return {
        "AUTO_TRADING_raw": os.environ.get("AUTO_TRADING"),
        "AUTO_TRADING_eval": os.environ.get("AUTO_TRADING", "false").lower() == "true"
    }

@app.route("/portfolio")
def portfolio():
    positions = trading_client.get_all_positions()
    return {"positions":[p.symbol for p in positions]}

@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
