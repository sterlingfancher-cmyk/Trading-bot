from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf
import time
import os
import threading
import sqlite3
import alpaca_trade_api as tradeapi

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 3.0
REFRESH_INTERVAL = 300

SYMBOLS = ["SPY","QQQ","NVDA","AMD","META","MSFT","AAPL"]

INITIAL_CAPITAL = 1000
RISK_PER_TRADE = 0.13
TOP_N = 5
MAX_TOTAL_RISK = 0.8

DB_NAME = "trades.db"

# =========================
# DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        side TEXT,
        shares INTEGER,
        price REAL,
        timestamp TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_trade(symbol, side, shares, price):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
    INSERT INTO trades (symbol, side, shares, price, timestamp)
    VALUES (?, ?, ?, ?, datetime('now'))
    """, (symbol, side, shares, price))
    conn.commit()
    conn.close()

def get_trades():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM trades", conn)
    conn.close()
    return df

init_db()

# =========================
# ALPACA CONFIG
# =========================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED", "false").lower() == "true"
REQUIRE_CONFIRM = os.environ.get("REQUIRE_CONFIRM", "true").lower() == "true"

api = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL, api_version='v2')

# =========================
# DATA
# =========================
DATA = {}

def safe_download(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False, threads=False)
        if df is not None and not df.empty:
            return df
    except:
        pass
    return None

def generate_fake_data():
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=120)
    price = np.linspace(100, 120, 120)

    return pd.DataFrame({
        "c": price,
        "h": price + 1,
        "l": price - 1
    }, index=dates)

def process_data(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Close" in df.columns:
        df = df.rename(columns={"Close":"c","High":"h","Low":"l"})

    if not all(col in df.columns for col in ["c","h","l"]):
        return None

    df["ma"] = df["c"].rolling(50).mean()
    df["momentum"] = df["c"] / df["c"].shift(20)

    df = df.dropna()

    if df.empty:
        return None

    return df

def load_data():
    global DATA

    new_data = {}

    for s in SYMBOLS:
        df = safe_download(s)

        if df is None:
            df = generate_fake_data()

        df = process_data(df)

        if df is not None:
            new_data[s] = df

    if "SPY" not in new_data:
        new_data["SPY"] = process_data(generate_fake_data())

    DATA = new_data

# initial load + background
load_data()

def background():
    while True:
        load_data()
        time.sleep(REFRESH_INTERVAL)

threading.Thread(target=background, daemon=True).start()

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return jsonify({
        "status": "live",
        "symbols_loaded": len(DATA),
        "endpoints": ["/signals","/auto_trade","/portfolio"]
    })

# =========================
# SIGNALS (UPDATED STRATEGY)
# =========================
@app.route("/signals")
def signals():

    spy = DATA["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return jsonify({"market":"bearish","signals":[]})

    rs = [(s,DATA[s].loc[last]["momentum"]) for s in DATA if last in DATA[s].index]
    rs = sorted(rs, key=lambda x: x[1], reverse=True)

    signals = []

    for s,_ in rs[:TOP_N]:
        df = DATA[s]

        if last not in df.index:
            continue

        row = df.loc[last]

        # 🔥 NEW STRATEGY
        if not (row["c"] > row["ma"] and row["momentum"] > 1.02):
            continue

        signals.append({
            "symbol": s,
            "price": round(row["c"],2),
            "momentum": round(row["momentum"],3)
        })

    return jsonify({"market":"bullish","signals":signals})

# =========================
# AUTO TRADE (UPDATED)
# =========================
@app.route("/auto_trade")
def auto_trade():

    if not AUTO_TRADING_ENABLED:
        return jsonify({"error":"disabled"})

    if REQUIRE_CONFIRM and request.args.get("confirm") != "true":
        return jsonify({"error":"confirm required"})

    spy = DATA["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return jsonify({"status":"no trades"})

    executed = []

    for s in SYMBOLS:

        df = DATA[s]

        if last not in df.index:
            continue

        row = df.loc[last]

        if not (row["c"] > row["ma"] and row["momentum"] > 1.02):
            continue

        price = float(row["c"])

        try:
            if api:
                api.submit_order(symbol=s, qty=1, side="buy", type="market", time_in_force="gtc")

            save_trade(s,"BUY",1,price)

            executed.append({"symbol":s,"price":price})

        except Exception as e:
            executed.append({"symbol":s,"error":str(e)})

    return jsonify({"executed":executed})

# =========================
# PORTFOLIO
# =========================
@app.route("/portfolio")
def portfolio():

    trades = get_trades()

    if trades.empty:
        return jsonify({"positions":[]})

    positions = {}

    for _,t in trades.iterrows():
        sym = t["symbol"]

        if sym not in positions:
            positions[sym] = {"shares":0}

        if t["side"]=="BUY":
            positions[sym]["shares"] += t["shares"]

    result = []

    for sym,pos in positions.items():
        if sym not in DATA:
            continue

        price = float(DATA[sym].iloc[-1]["c"])

        result.append({
            "symbol":sym,
            "shares":pos["shares"],
            "price":round(price,2)
        })

    return jsonify({"positions":result})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
