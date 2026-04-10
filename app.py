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

# =========================
# LOAD DATA ON STARTUP (KEY FIX)
# =========================
def load_all_data():
    data = {}

    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)

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

            df["ma_200"] = df["c"].rolling(200).mean()
            df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

            data[symbol] = df.dropna()

        except Exception as e:
            print(f"FAILED: {symbol} -> {e}")

    return data


print("🚀 Loading market data...")
DATA = load_all_data()
print(f"✅ Loaded {len(DATA)} symbols")


# =========================
# ROUTE
# =========================
@app.route("/portfolio")
def portfolio():

    if len(DATA) == 0:
        return jsonify({"error": "No data loaded"})

    capital = INITIAL_CAPITAL

    for symbol, df in DATA.items():
        capital += len(df) * 0.01  # dummy logic just to prove it works

    return jsonify({
        "final_balance": round(capital, 2),
        "symbols_loaded": len(DATA)
    })


@app.route("/")
def home():
    return jsonify({"status": "running-fast"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
