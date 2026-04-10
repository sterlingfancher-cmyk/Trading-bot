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
RISK_PER_TRADE = 0.1   # 10%
MAX_POSITIONS = 3


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
# PREP
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
# 🔥 PORTFOLIO ENGINE (UPGRADED)
# =========================
@app.route("/portfolio")
def portfolio():

    data = {}

    for symbol in SYMBOLS:
        df = get_data(symbol)
        if df is None:
            continue
        data[symbol] = prepare(df)

    all_dates = sorted(set().union(*[df.index for df in data.values()]))

    capital = INITIAL_CAPITAL

    positions = {}
    entry_price = {}
    peak_price = {}
    position_size = {}

    trade_count = 0

    for date in all_dates:

        # =========================
        # CHECK EXITS FIRST
        # =========================
        for symbol in list(positions.keys()):

            df = data[symbol]

            if date not in df.index:
                continue

            row = df.loc[date]

            peak_price[symbol] = max(peak_price[symbol], row["c"])
            stop = peak_price[symbol] - (ATR_MULT * row["atr"])

            if row["c"] < stop:
                pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]

                capital += position_size[symbol] * pct

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

                trade_count += 1

        # =========================
        # CHECK ENTRIES
        # =========================
        open_slots = MAX_POSITIONS - len(positions)

        if open_slots <= 0:
            continue

        for symbol, df in data.items():

            if symbol in positions:
                continue

            if date not in df.index:
                continue

            row = df.loc[date]

            trend = row["c"] > row["ma_200"]
            breakout = row["c"] > row["high_break"]
            vol = row["atr_rising"]

            if trend and breakout and vol:

                # 🔥 POSITION SIZING
                risk_amount = capital * RISK_PER_TRADE

                positions[symbol] = True
                entry_price[symbol] = row["c"]
                peak_price[symbol] = row["c"]
                position_size[symbol] = risk_amount

                if len(positions) >= MAX_POSITIONS:
                    break

    return jsonify({
        "final_balance": round(capital, 2),
        "total_trades": trade_count,
        "active_positions": len(positions)
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
