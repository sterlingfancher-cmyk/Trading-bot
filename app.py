from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 2.5
SYMBOLS = ["SPY", "QQQ", "IWM", "XLE", "XLK"]
INITIAL_CAPITAL = 1000


# =========================
# DATA
# =========================
def get_data(symbol):
    df = yf.download(symbol, period="5y", interval="1d", progress=False)

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Open": "o",
        "High": "h",
        "Low": "l",
        "Close": "c",
        "Volume": "v"
    })

    return df[["o", "h", "l", "c", "v"]].dropna()


# =========================
# PREP DATA
# =========================
def prepare(df):
    df["ma_200"] = df["c"].rolling(200).mean()
    df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(
            abs(df["h"] - prev_close),
            abs(df["l"] - prev_close)
        )
    )

    df["atr"] = tr.rolling(14).mean()
    df["atr_rising"] = df["atr"] > df["atr"].shift(1)

    return df.dropna()


# =========================
# 🔥 TRUE PORTFOLIO ENGINE
# =========================
@app.route("/portfolio")
def portfolio():

    data = {}

    for symbol in SYMBOLS:
        df = get_data(symbol)
        if df is None:
            continue
        data[symbol] = prepare(df)

    # Align dates
    all_dates = sorted(set().union(*[df.index for df in data.values()]))

    capital = INITIAL_CAPITAL
    positions = {}
    entry_price = {}
    peak_price = {}

    trade_count = 0

    for date in all_dates:

        for symbol, df in data.items():

            if date not in df.index:
                continue

            row = df.loc[date]

            # ENTRY
            if symbol not in positions:
                trend = row["c"] > row["ma_200"]
                breakout = row["c"] > row["high_break"]
                vol = row["atr_rising"]

                if trend and breakout and vol:
                    allocation = capital / len(SYMBOLS)

                    positions[symbol] = allocation
                    entry_price[symbol] = row["c"]
                    peak_price[symbol] = row["c"]

            # EXIT
            else:
                peak_price[symbol] = max(peak_price[symbol], row["c"])

                stop = peak_price[symbol] - (ATR_MULT * row["atr"])

                if row["c"] < stop:
                    pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]

                    capital += positions[symbol] * pct

                    del positions[symbol]
                    del entry_price[symbol]
                    del peak_price[symbol]

                    trade_count += 1

    return jsonify({
        "final_balance": round(capital, 2),
        "total_trades": trade_count,
        "active_positions": len(positions)
    })


# =========================
# SINGLE BACKTEST (UNCHANGED)
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_data(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    df = prepare(df)

    capital = 1000
    position = 0
    entry_price = 0
    peak_price = 0

    trades = []

    for i in range(len(df)):
        row = df.iloc[i]

        if position == 0:
            if (
                row["c"] > row["ma_200"] and
                row["c"] > row["high_break"] and
                row["atr_rising"]
            ):
                position = 1
                entry_price = row["c"]
                peak_price = row["c"]

        else:
            peak_price = max(peak_price, row["c"])
            stop = peak_price - (ATR_MULT * row["atr"])

            if row["c"] < stop:
                pct = (row["c"] - entry_price) / entry_price
                capital *= (1 + pct)
                trades.append(pct)
                position = 0

    if len(trades) == 0:
        return jsonify({"error": "No trades"})

    sharpe = np.mean(trades) / (np.std(trades) + 1e-9)

    return jsonify({
        "symbol": symbol,
        "balance": round(capital, 2),
        "sharpe": round(sharpe, 4),
        "trades": len(trades)
    })


# =========================
# HEALTH
# =========================
@app.route("/")
def home():
    return jsonify({"status": "running"})


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
