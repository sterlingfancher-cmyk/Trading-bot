from flask import Flask, request
import pandas as pd
import os
import sqlite3
from datetime import datetime
import subprocess
import sys

app = Flask(__name__)

# =========================
# INSTALL
# =========================
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "alpaca-py"])
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
MAX_POSITIONS = 3
RISK_PER_TRADE = 0.1  # 10% of buying power

# =========================
# CLIENTS
# =========================
trading_client = TradingClient(
    os.environ.get("ALPACA_API_KEY"),
    os.environ.get("ALPACA_SECRET_KEY"),
    paper=True
)

data_client = StockHistoricalDataClient(
    os.environ.get("ALPACA_API_KEY"),
    os.environ.get("ALPACA_SECRET_KEY")
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
# REAL DATA LOADER
# =========================
def load_data(symbol):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        limit=100
    )

    bars = data_client.get_stock_bars(request).df

    if bars.empty:
        return None

    df = bars.xs(symbol)
    df["ma"] = df["close"].rolling(20).mean()
    df["momentum"] = df["close"] / df["close"].shift(10)
    df = df.dropna()

    return df

# =========================
# SIGNAL ENGINE (REAL DATA)
# =========================
def get_signals():

    spy = load_data("SPY")
    if spy is None:
        return "error", []

    last = spy.index[-1]

    if spy.loc[last]["close"] <= spy.loc[last]["ma"]:
        return "bearish", []

    scores = []

    for symbol in SYMBOLS:
        df = load_data(symbol)
        if df is None:
            continue

        row = df.iloc[-1]

        if row["close"] > row["ma"]:
            scores.append((symbol, row["momentum"], row["close"]))

    ranked = sorted(scores, key=lambda x: x[1], reverse=True)

    signals = [
        {"symbol": s, "price": round(p,2)}
        for s,_,p in ranked[:3]
    ]

    return "bullish", signals

# =========================
# POSITION SIZING
# =========================
def calculate_position_size(price):
    account = trading_client.get_account()
    buying_power = float(account.buying_power)

    allocation = buying_power * RISK_PER_TRADE
    qty = int(allocation // price)

    return max(qty, 1)

# =========================
# EXECUTE TRADE
# =========================
def execute_trade(symbol):

    try:
        positions = trading_client.get_all_positions()
        held = [p.symbol for p in positions]

        if symbol in held:
            return {"error":"already holding"}

        if len(held) >= MAX_POSITIONS:
            return {"error":"max positions reached"}

        # get latest price
        df = load_data(symbol)
        price = df.iloc[-1]["close"]

        qty = calculate_position_size(price)

        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )

        trading_client.submit_order(order_data)

        c.execute(
            "INSERT INTO trades VALUES (NULL,?,?,?,?,?)",
            (symbol,"BUY",price,qty,datetime.now())
        )
        conn.commit()

        return {
            "status":"executed",
            "symbol":symbol,
            "qty":qty,
            "price":round(price,2)
        }

    except Exception as e:
        return {"error":str(e)}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"running"}

@app.route("/signals")
def signals():
    market, sigs = get_signals()
    return {"market":market,"signals":sigs}

@app.route("/trade")
def trade():
    symbol = request.args.get("symbol")
    return execute_trade(symbol.upper())

@app.route("/portfolio")
def portfolio():
    positions = trading_client.get_all_positions()

    return {
        "positions":[
            {
                "symbol":p.symbol,
                "qty":p.qty,
                "price":float(p.current_price),
                "pnl":float(p.unrealized_pl)
            } for p in positions
        ]
    }

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
