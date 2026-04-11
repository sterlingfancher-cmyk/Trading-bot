from flask import Flask, request
import pandas as pd
import time
import os
import threading
import sqlite3
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame

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
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED","false").lower()=="true"
REQUIRE_CONFIRM = os.environ.get("REQUIRE_CONFIRM","true").lower()=="true"

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise Exception("❌ Alpaca keys missing")

api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL, api_version='v2')

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
# LOAD DATA (SAFE)
# =========================
def load_data():
    global DATA, DATA_READY
    new_data = {}

    for symbol in SYMBOLS:
        try:
            bars = api.get_bars(symbol, TimeFrame.Day, limit=200).df

            if bars is None or bars.empty:
                print(f"❌ No data for {symbol}")
                continue

            bars = bars.reset_index()

            df = pd.DataFrame({
                "c": bars["close"],
                "h": bars["high"],
                "l": bars["low"]
            })

            df.index = pd.to_datetime(bars["timestamp"])

            df = process_data(df)

            if not df.empty:
                new_data[symbol] = df
                print(f"✅ Loaded: {symbol}")

        except Exception as e:
            print(f"❌ ERROR {symbol}: {e}")

    if new_data:
        DATA = new_data
        DATA_READY = True
    else:
        print("🚨 No data loaded yet")

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

# =========================
# SIGNALS
# =========================
@app.route("/signals")
def signals():

    if not DATA_READY:
        return {"error":"Data loading... try again shortly"}

    if "SPY" not in DATA:
        return {"error":"SPY not loaded"}

    spy = DATA["SPY"]

    if spy.empty:
        return {"error":"SPY empty"}

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
# AUTO TRADE
# =========================
@app.route("/auto_trade")
def auto_trade():

    if not AUTO_TRADING_ENABLED:
        return {"error":"disabled"}

    if REQUIRE_CONFIRM and request.args.get("confirm")!="true":
        return {"error":"confirm required"}

    if not DATA_READY:
        return {"error":"data not ready"}

    executed = []
    open_positions = get_open_positions()

    spy = DATA["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return {"executed":executed,"note":"bearish"}

    for s in SYMBOLS:

        if s in open_positions:
            continue

        if len(open_positions) >= MAX_POSITIONS:
            break

        df = DATA.get(s)
        if df is None or last not in df.index:
            continue

        row = df.loc[last]

        if row["c"] > row["ma"] and row["momentum"] > 1.02:
            price = float(row["c"])

            try:
                api.submit_order(symbol=s, qty=1, side="buy", type="market", time_in_force="gtc")
                save_trade(s,"BUY",1,price)
                executed.append({"symbol":s,"price":price})
            except Exception as e:
                executed.append({"symbol":s,"error":str(e)})

    return {"executed":executed}

# =========================
# PORTFOLIO
# =========================
@app.route("/portfolio")
def portfolio():

    if not DATA_READY:
        return {"error":"data not ready"}

    positions = get_open_positions()
    result = []

    for sym, shares in positions.items():
        df = DATA.get(sym)

        if df is None or df.empty:
            continue

        price = float(df.iloc[-1]["c"])

        result.append({
            "symbol":sym,
            "shares":shares,
            "price":round(price,2)
        })

    return {"positions":result}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
