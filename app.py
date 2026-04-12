from flask import Flask, request
import pandas as pd
import os
import sqlite3
from datetime import datetime
import subprocess
import sys

app = Flask(__name__)

# =========================
# FORCE INSTALL DEPENDENCIES
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

# =========================
# ALPACA CLIENT
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
# DATA LOADER
# =========================
def load_data(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d")

        if df is None or df.empty or len(df) < 30:
            return None

        df["ma"] = df["Close"].rolling(20).mean()
        df["momentum"] = df["Close"] / df["Close"].shift(10)
        df = df.dropna()

        return df if not df.empty else None

    except Exception:
        return None

# =========================
# SIGNAL ENGINE (FIXED)
# =========================
def get_signals():

    spy = load_data("SPY")
    if spy is None:
        return "error", []

    last_close = float(spy["Close"].iloc[-1])
    last_ma = float(spy["ma"].iloc[-1])

    if last_close <= last_ma:
        return "bearish", []

    scores = []

    for symbol in SYMBOLS:
        df = load_data(symbol)
        if df is None:
            continue

        price = float(df["Close"].iloc[-1])
        ma = float(df["ma"].iloc[-1])
        momentum = float(df["momentum"].iloc[-1])

        if price > ma:
            scores.append((symbol, momentum, price))

    if not scores:
        return "no_data", []

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
# EXECUTE TRADE (FIXED)
# =========================
def execute_trade(symbol):

    try:
        positions = trading_client.get_all_positions()
        held = [p.symbol for p in positions]

        if symbol in held:
            return {"error":"already holding"}

        if len(held) >= MAX_POSITIONS:
            return {"error":"max positions reached"}

        df = load_data(symbol)
        if df is None:
            return {"error":"no data available"}

        price = float(df["Close"].iloc[-1])
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
    if not symbol:
        return {"error":"symbol required"}
    return execute_trade(symbol.upper())

@app.route("/portfolio")
def portfolio():
    try:
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

    except Exception as e:
        return {"error":str(e)}

@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

# =========================
# DEBUG ROUTE
# =========================
@app.route("/test_data")
def test_data():
    try:
        df = yf.download("SPY", period="1mo")
        return {"rows": len(df)}
    except Exception as e:
        return {"error": str(e)}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
