from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

LOOKBACK = 20
ATR_MULT = 2.5

SYMBOLS = [
    "SPY", "QQQ", "IWM",
    "XLE", "XLK", "XLF", "XLV",
    "XLI", "XLP", "XLY",
    "GLD", "SLV",
    "TLT",
    "ARKK",
    "SMH"
]

INITIAL_CAPITAL = 1000

# 🔥 GLOBAL CACHE (empty at start)
DATA = None


# =========================
# SAFE LOAD (LAZY)
# =========================
def load_data():

    global DATA

    if DATA is not None:
        return DATA  # already loaded

    data = {}

    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="6mo", interval="1d", progress=False)

            if df is None or df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.rename(columns={
                "Open": "o",
                "High": "h",
                "Low": "l",
                "Close": "c",
                "Volume": "v"
            })

            df["ma_200"] = df["c"].rolling(50).mean()  # reduced for speed
            df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

            data[symbol] = df.dropna()

        except Exception as e:
            print(f"ERROR loading {symbol}: {e}")

    DATA = data
    return DATA


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({"status": "running"})


@app.route("/portfolio")
def portfolio():

    data = load_data()

    if len(data) == 0:
        return jsonify({"error": "no data"})

    capital = INITIAL_CAPITAL

    for symbol, df in data.items():
        capital += len(df) * 0.5  # simple test logic

    return jsonify({
        "final_balance": round(capital, 2),
        "symbols": len(data)
    })


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
