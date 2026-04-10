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
    df = yf.download(symbol, period="60d", interval="15m", progress=False)

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
# STRATEGY (FIXED BREAKOUT)
# =========================
def run_strategy(df, lookback, atr_mult):
    df = df.copy()

    # 🔥 FIXED: shift to avoid lookahead bias
    df["high_break"] = df["h"].rolling(lookback).max().shift(1)

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(
            abs(df["h"] - prev_close),
            abs(df["l"] - prev_close)
        )
    )
    df["atr"] = tr.rolling(14).mean()

    df = df.dropna()

    capital = 1000
    position = 0
    entry_price = 0

    trades = []

    for i in range(len(df)):
        row = df.iloc[i]

        # 🔥 LOOSENED ENTRY
        if position == 0:
            if row["c"] > row["high_break"] * 0.998:
                position = 1
                entry_price = row["c"]

        else:
            stop = entry_price - (atr_mult * row["atr"])

            if row["c"] < stop:
                pct = (row["c"] - entry_price) / entry_price
                capital *= (1 + pct)
                trades.append(pct)
                position = 0

    if len(trades) == 0:
        return None

    sharpe = np.mean(trades) / (np.std(trades) + 1e-9)

    return {
        "balance": capital,
        "sharpe": sharpe,
        "trades": len(trades)
    }


# =========================
# BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    result = run_strategy(df, 20, 1.5)

    if result is None:
        return jsonify({"error": "No trades"})

    return jsonify({
        "symbol": symbol,
        "balance": round(result["balance"], 2),
        "sharpe": round(result["sharpe"], 4),
        "trades": result["trades"]
    })


# =========================
# OPTIMIZER
# =========================
@app.route("/optimize/<symbol>")
def optimize(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    best = {"score": -999}

    lookback_range = [10, 15, 20, 30]
    atr_range = [1.0, 1.5, 2.0]

    for look, atr in itertools.product(lookback_range, atr_range):

        result = run_strategy(df, look, atr)

        if result is None:
            continue

        score = (
            result["sharpe"] * 2 +
            (result["balance"] - 1000) * 0.1 +
            min(result["trades"], 25) * 0.02
        )

        if result["trades"] < 5:
            score *= 0.5

        if score > best["score"]:
            best = {
                "score": round(score, 4),
                "balance": round(result["balance"], 2),
                "sharpe": round(result["sharpe"], 4),
                "trades": result["trades"],
                "params": {
                    "lookback": look,
                    "atr_mult": atr
                }
            }

    return jsonify(best)


@app.route("/")
def home():
    return jsonify({"status": "running"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
