from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf
import itertools

app = Flask(__name__)

# =========================
# DATA
# =========================
def get_intraday(symbol):
    df = yf.download(symbol, period="5d", interval="5m")

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Close": "c",
        "High": "h",
        "Low": "l",
        "Open": "o",
        "Volume": "v"
    })

    return df


# =========================
# STRATEGY
# =========================
def run_strategy(df, fast, slow, atr_mult_sl, atr_mult_tp, vol_thresh):

    df = df.copy()

    df["ma_fast"] = df["c"].rolling(fast).mean()
    df["ma_slow"] = df["c"].rolling(slow).mean()

    # ATR
    df["tr"] = np.maximum(
        df["h"] - df["l"],
        np.maximum(
            abs(df["h"] - df["c"].shift(1)),
            abs(df["l"] - df["c"].shift(1))
        )
    )
    df["atr"] = df["tr"].rolling(14).mean()

    df["returns"] = df["c"].pct_change()
    df["vol"] = df["returns"].rolling(10).std()

    df = df.dropna()

    position = 0
    entry_price = 0
    entry_atr = 0

    results = []

    for i in range(len(df)):
        row = df.iloc[i]

        if position == 0:
            if (
                row["ma_fast"] > row["ma_slow"] and
                row["vol"] > vol_thresh
            ):
                position = 1
                entry_price = row["c"]
                entry_atr = row["atr"]
                results.append(0)
            else:
                results.append(0)

        else:
            change = row["c"] - entry_price

            stop = -atr_mult_sl * entry_atr
            target = atr_mult_tp * entry_atr

            if (
                change <= stop or
                change >= target or
                row["ma_fast"] < row["ma_slow"]
            ):
                position = 0
                results.append(change / entry_price)
            else:
                results.append(0)

    df["strategy"] = results

    total_return = df["strategy"].sum()
    sharpe = df["strategy"].mean() / (df["strategy"].std() + 1e-9)

    return total_return, sharpe


# =========================
# OPTIMIZER
# =========================
@app.route("/optimize/<symbol>")
def optimize(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "No data"})

    best = {
        "balance": 0,
        "sharpe": -999,
        "params": {}
    }

    fast_range = [5, 8, 10, 12]
    slow_range = [20, 30, 40]
    sl_range = [1.0, 1.5, 2.0]
    tp_range = [2.0, 2.5, 3.0]
    vol_range = [0.0005, 0.001, 0.0015]

    for fast, slow, sl, tp, vol in itertools.product(
        fast_range, slow_range, sl_range, tp_range, vol_range
    ):
        if fast >= slow:
            continue

        ret, sharpe = run_strategy(df, fast, slow, sl, tp, vol)
        balance = 1000 * (1 + ret)

        if sharpe > best["sharpe"]:
            best = {
                "balance": round(balance, 2),
                "sharpe": round(sharpe, 4),
                "params": {
                    "fast": fast,
                    "slow": slow,
                    "atr_sl": sl,
                    "atr_tp": tp,
                    "vol_thresh": vol
                }
            }

    return jsonify(best)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
