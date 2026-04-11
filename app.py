from flask import Flask, request
import pandas as pd
import time
import os
import threading
import sqlite3
import requests
from alpaca_trade_api.rest import REST

app = Flask(__name__)

SYMBOLS = ["SPY","QQQ","NVDA","AMD","META","MSFT","AAPL"]
REFRESH_INTERVAL = 60
DB_NAME = "trades.db"

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL)

DATA = {}
DATA_READY = False

# =========================
# FALLBACK DATA (ALWAYS WORKS)
# =========================
def get_fallback_data(symbol):
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
        df = pd.read_csv(url)

        df.columns = ["date","open","high","low","close","volume"]
        df["c"] = df["close"]
        df["h"] = df["high"]
        df["l"] = df["low"]

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        return df.tail(200)
    except:
        return None

# =========================
# PROCESS
# =========================
def process(df):
    df["ma"] = df["c"].rolling(50).mean()
    df["momentum"] = df["c"] / df["c"].shift(20)
    return df.dropna()

# =========================
# LOAD DATA
# =========================
def load_data():
    global DATA, DATA_READY
    new_data = {}

    for symbol in SYMBOLS:
        df = None

        # TRY ALPACA FIRST
        try:
            bars = api.get_bars(symbol, "1Day", limit=200).df

            if bars is not None and not bars.empty:
                df = pd.DataFrame({
                    "c": bars["close"],
                    "h": bars["high"],
                    "l": bars["low"]
                })
                df.index = pd.to_datetime(bars.index)
                print(f"✅ Alpaca: {symbol}")
        except:
            pass

        # FALLBACK
        if df is None or df.empty:
            df = get_fallback_data(symbol)
            if df is not None:
                print(f"🔁 Fallback: {symbol}")

        if df is not None and not df.empty:
            df = process(df)
            if not df.empty:
                new_data[symbol] = df

    if new_data:
        DATA = new_data
        DATA_READY = True
        print("🚀 DATA READY")

# =========================
# BACKGROUND
# =========================
def background():
    while True:
        load_data()
        time.sleep(REFRESH_INTERVAL)

threading.Thread(target=background, daemon=True).start()

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():
    return {
        "data_ready": DATA_READY,
        "symbols_loaded": list(DATA.keys())
    }

@app.route("/signals")
def signals():

    if not DATA_READY:
        return {"error":"loading"}

    spy = DATA["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return {"market":"bearish","signals":[]}

    ranked = sorted(
        [(s, DATA[s].loc[last]["momentum"]) for s in DATA],
        key=lambda x: x[1],
        reverse=True
    )

    signals = []

    for s,_ in ranked[:5]:
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
