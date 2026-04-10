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
RISK_PER_TRADE = 0.1
MAX_POSITIONS = 3
COOLDOWN_DAYS = 10


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
    df["atr_change"] = df["atr"].pct_change()

    return df.dropna()


# =========================
# PORTFOLIO ENGINE (COOLDOWN)
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

    last_exit_index = {s: -999 for s in SYMBOLS}

    trade_count = 0

    for i, date in enumerate(all_dates):

        # =========================
        # EXITS
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

                last_exit_index[symbol] = i

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

                trade_count += 1

        # =========================
        # FIND SIGNALS
        # =========================
        signals = []

        for symbol, df in data.items():

            # 🔥 COOLDOWN FILTER
            if i - last_exit_index[symbol] < COOLDOWN_DAYS:
                continue

            if symbol in positions:
                continue

            if date not in df.index:
                continue

            row = df.loc[date]

            trend = row["c"] > row["ma_200"]
            breakout = row["c"] > row["high_break"]
            vol = row["atr_change"] > 0

            if trend and breakout and vol:

                breakout_strength = (row["c"] - row["high_break"]) / row["high_break"]
                vol_strength = row["atr_change"]

                score = breakout_strength + vol_strength

                signals.append((symbol, score, row))

        # =========================
        # TAKE BEST SIGNALS
        # =========================
        signals = sorted(signals, key=lambda x: x[1], reverse=True)

        open_slots = MAX_POSITIONS - len(positions)

        for symbol, score, row in signals[:open_slots]:

            risk_amount = capital * RISK_PER_TRADE

            positions[symbol] = True
            entry_price[symbol] = row["c"]
            peak_price[symbol] = row["c"]
            position_size[symbol] = risk_amount

    return jsonify({
        "final_balance": round(capital, 2),
        "total_trades": trade_count,
        "active_positions": len(positions)
    })


@app.route("/")
def home():
    return jsonify({"status": "running"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
