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
SYMBOLS = [
    "SPY","QQQ",
    "AAPL","MSFT","GOOGL","AMZN",
    "NVDA","AMD","META","AVGO","TSLA",
    "NFLX","CRM","ADBE","INTC",
    "JPM","GS","CAT","BA"
]

MAX_POSITIONS = 3

LONG_RISK = 0.1
SHORT_RISK = 0.05

STOP_LOSS = 0.93
TRAILING_STOP = 0.90

SHORT_STOP_LOSS = 1.04
SHORT_TRAILING_STOP = 1.10

# =========================
# ENV
# =========================
def is_auto_trading():
    return os.environ.get("AUTO_TRADING", "false").lower() == "true"

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
# TRAILING STORAGE
# =========================
peak_prices = {}
low_prices = {}

# =========================
# MARKET HOURS
# =========================
def market_is_open():
    return trading_client.get_clock().is_open

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

    scores = []

    for symbol in SYMBOLS:
        df = load_data(symbol)
        if df is None:
            continue

        price = float(df["Close"].values[-1])
        ma = float(df["ma"].values[-1])
        momentum = float(df["momentum"].values[-1])

        scores.append((symbol, momentum, price, ma))

    if spy_close > spy_ma:
        strong = [s for s in scores if s[2] > s[3]]
        ranked = sorted(strong, key=lambda x: x[1], reverse=True)
        return "bullish", [{"symbol": s, "price": p} for s,_,p,_ in ranked[:3]]

    else:
        weak = [s for s in scores if s[2] < s[3]]
        ranked = sorted(weak, key=lambda x: x[1])
        return "bearish", [{"symbol": s, "price": p} for s,_,p,_ in ranked[:3]]

# =========================
# POSITION SIZE
# =========================
def calculate_qty(price, risk):
    account = trading_client.get_account()
    buying_power = float(account.buying_power)
    allocation = buying_power * risk
    return max(int(allocation // price), 1)

# =========================
# ORDER EXECUTION
# =========================
def place_order(symbol, price, side, risk):
    qty = calculate_qty(price, risk)

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC
    )

    trading_client.submit_order(order)

    c.execute(
        "INSERT INTO trades VALUES (NULL,?,?,?,?,?)",
        (symbol, side.name, price, qty, datetime.now())
    )
    conn.commit()

# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    positions = trading_client.get_all_positions()

    for p in positions:
        symbol = p.symbol
        entry = float(p.avg_entry_price)
        current = float(p.current_price)
        side = p.side

        # LONG
        if side == "long":
            peak_prices[symbol] = max(peak_prices.get(symbol, entry), current)

            if current <= entry * STOP_LOSS or current <= peak_prices[symbol] * TRAILING_STOP:
                trading_client.submit_order(MarketOrderRequest(
                    symbol=symbol,
                    qty=int(float(p.qty)),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC
                ))

        # SHORT
        elif side == "short":
            low_prices[symbol] = min(low_prices.get(symbol, entry), current)

            if current >= entry * SHORT_STOP_LOSS or current >= low_prices[symbol] * SHORT_TRAILING_STOP:
                trading_client.submit_order(MarketOrderRequest(
                    symbol=symbol,
                    qty=int(float(p.qty)),
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC
                ))

# =========================
# AUTO TRADER
# =========================
def auto_trader():
    while True:
        try:
            if is_auto_trading() and market_is_open():

                market, signals = get_signals()

                positions = trading_client.get_all_positions()
                held = [p.symbol for p in positions]

                for s in signals:
                    if s["symbol"] not in held and len(held) < MAX_POSITIONS:

                        if market == "bullish":
                            place_order(s["symbol"], s["price"], OrderSide.BUY, LONG_RISK)

                        elif market == "bearish":
                            place_order(s["symbol"], s["price"], OrderSide.SELL, SHORT_RISK)

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
        "status": "running",
        "auto_trading": is_auto_trading(),
        "market_open": market_is_open()
    }

@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
