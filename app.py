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
TOP_N = 4
MAX_TOTAL_RISK = 0.8

DB_NAME = "trades.db"

# =========================
# DB SETUP
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

init_db()

# =========================
# SAVE TRADE
# =========================
def save_trade(symbol, side, shares, price):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    INSERT INTO trades (symbol, side, shares, price, timestamp)
    VALUES (?, ?, ?, ?, datetime('now'))
    """, (symbol, side, shares, price))

    conn.commit()
    conn.close()

# =========================
# LOAD TRADES
# =========================
def get_trades():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM trades", conn)
    conn.close()
    return df

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

def generate_fake_data():
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=120)
    price = np.linspace(100, 120, 120)
    df = pd.DataFrame({"c": price, "h": price+1, "l": price-1}, index=dates)
    return df

def process_data(df):
    if "Close" in df.columns:
        df = df.rename(columns={"Close":"c","High":"h","Low":"l"})

    df["ma"] = df["c"].rolling(50).mean()
    df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

    prev = df["c"].shift(1)
    tr = np.maximum(df["h"]-df["l"], np.maximum(abs(df["h"]-prev), abs(df["l"]-prev)))

    df["atr"] = pd.Series(tr).rolling(14).mean()
    df["atr_change"] = df["atr"].pct_change()
    df["momentum"] = df["c"] / df["c"].shift(20)

    return df.dropna()

def load_data():
    global DATA
    new_data = {}

    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False, threads=False)
            if df is None or df.empty:
                df = generate_fake_data()
        except:
            df = generate_fake_data()

        df = process_data(df)
        new_data[s] = df

    DATA = new_data

# initial + background
load_data()
threading.Thread(target=lambda: [load_data() or time.sleep(REFRESH_INTERVAL) for _ in iter(int,1)], daemon=True).start()

# =========================
# SIGNALS
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

        if not (row["c"]>row["ma"] and row["c"]>row["high_break"] and row["atr_change"]>0):
            continue

        signals.append({
            "symbol": s,
            "price": round(row["c"],2)
        })

    return jsonify({"market":"bullish","signals":signals})

# =========================
# AUTO TRADE + SAVE
# =========================
@app.route("/auto_trade")
def auto_trade():

    if not AUTO_TRADING_ENABLED:
        return jsonify({"error":"disabled"})

    if REQUIRE_CONFIRM and request.args.get("confirm") != "true":
        return jsonify({"error":"confirm required"})

    executed = []

    spy = DATA["SPY"]
    last = spy.index[-1]

    for s in SYMBOLS:
        df = DATA[s]
        if last not in df.index:
            continue

        row = df.loc[last]

        if not (row["c"]>row["ma"] and row["c"]>row["high_break"] and row["atr_change"]>0):
            continue

        price = float(row["c"])

        try:
            if api:
                api.submit_order(symbol=s, qty=1, side="buy", type="market", time_in_force="gtc")

            save_trade(s, "BUY", 1, price)

            executed.append({"symbol":s,"price":price})

        except Exception as e:
            executed.append({"symbol":s,"error":str(e)})

    return jsonify({"executed":executed})

# =========================
# PORTFOLIO (🔥 NEW)
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
            positions[sym] = {"shares":0,"avg_price":0}

        if t["side"]=="BUY":
            positions[sym]["shares"] += t["shares"]

    result = []

    for sym,pos in positions.items():
        if sym not in DATA:
            continue

        last_price = float(DATA[sym].iloc[-1]["c"])

        result.append({
            "symbol":sym,
            "shares":pos["shares"],
            "price":round(last_price,2)
        })

    return jsonify({"positions":result})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
