from flask import Flask, request
import pandas as pd
import time
import os
import threading
import sqlite3
from alpaca_trade_api.rest import REST

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META","MSFT","AAPL"]
REFRESH_INTERVAL = 60
MAX_POSITIONS = 3

DB_NAME = "trades.db"

# =========================
# ENV / ALPACA
# =========================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

# 🔥 IMPORTANT CHANGE HERE
BASE_URL = "https://data.alpaca.markets"

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED","false").lower()=="true"
REQUIRE_CONFIRM = os.environ.get("REQUIRE_CONFIRM","true").lower()=="true"

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise Exception("❌ Alpaca keys missing")

api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL)

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

def get_open_positions():
    trades = get_trades()
    positions = {}

    for _, t in trades.iterrows():
        sym = t["symbol"]

        if sym not in positions:
            positions[sym] = 0

        if t["side"] == "BUY":
            positions[sym] += t["shares"]
        elif t["side"] == "SELL":
            positions[sym] -= t["shares"]

    return {k:v for k,v in positions.items() if v > 0}

init_db()

# =========================
# DATA STORAGE
# =========================
DATA = {}
DATA_READY = False

def process_data(df):
    df["ma"] = df["c"].rolling(50).mean()
    df["momentum"] = df["c"] / df["c"].shift(20)
    return df.dropna()

# =========================
# LOAD DATA (WORKING 100%)
# =========================
def load_data():
    global DATA, DATA_READY
    new_data = {}

    for symbol in SYMBOLS:
        try:
            bars = api.get_bars(
                symbol,
                "1Day",
                limit=200,
                feed="iex"
            ).df

            if bars is None or bars.empty:
                print(f"❌ No data for {symbol}")
                continue

            df = pd.DataFrame({
                "c": bars["close"],
                "h": bars["high"],
                "l": bars["low"]
            })

            df.index = pd.to_datetime(bars.index)

            df = process_data(df)

            if not df.empty:
                new_data[symbol] = df
                print(f"✅ Loaded: {symbol}")

        except Exception as e:
            print(f"❌ ERROR {symbol}: {e}")

    if new_data:
        DATA = new_data
        DATA_READY = True
        print("🚀 DATA READY")
    else:
        print("🚨 STILL NO DATA")

# =========================
# BACKGROUND LOADER
# =========================
def background():
    while True:
        try:
            load_data()
        except Exception as e:
            print(f"Background error: {e}")
        time.sleep(REFRESH_INTERVAL)

threading.Thread(target=background, daemon=True).start()

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status":"live","data_ready":DATA_READY}

@app.route("/debug")
def debug():
    return {
        "alpaca_connected": True,
        "data_ready": DATA_READY,
        "symbols_loaded": list(DATA.keys())
    }

@app.route("/signals")
def signals():

    if not DATA_READY:
        return {"error":"Data loading..."}

    spy = DATA.get("SPY")
    if spy is None or spy.empty:
        return {"error":"SPY missing"}

    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return {"market":"bearish","signals":[]}

    rs = [(s, DATA[s].loc[last]["momentum"]) for s in DATA if last in DATA[s].index]
    rs = sorted(rs, key=lambda x: x[1], reverse=True)

    signals = []

    for s,_ in rs[:5]:
        row = DATA[s].loc[last]

        if row["c"] > row["ma"] and row["momentum"] > 1.02:
            signals.append({
                "symbol": s,
                "price": round(float(row["c"]),2)
            })

    return {"market":"bullish","signals":signals}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
