from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf
import itertools

app = Flask(__name__)

# =========================
# CONFIG (YOUR EDGE LOCKED)
# =========================
LOOKBACK = 20
ATR_MULT = 2.5

# Portfolio assets
SYMBOLS = ["SPY", "QQQ", "IWM", "XLE", "XLK"]


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
# STRATEGY (YOUR EDGE)
# =========================
def run_strategy(df, lookback, atr_mult):
    df = df.copy()

    df["ma_200"] = df["c"].rolling(200).mean()
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
    df["atr_rising"] = df["atr"] > df["atr"].shift(1)

    df = df.dropna()

    capital = 1000
    position = 0
    entry_price = 0
    peak_price = 0

    trades = []

    for i in range(len(df)):
        row = df.iloc[i]

        trend = row["c"] > row["ma_200"]
        breakout = row["c"] > row["high_break"]
        volatility = row["atr_rising"]

        # ENTRY
        if position == 0:
            if trend and breakout and volatility:
                position = 1
                entry_price = row["c"]
                peak_price = row["c"]

        # EXIT
        else:
            peak_price = max(peak_price, row["c"])
            stop = peak_price - (atr_mult * row["atr"])

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
# SINGLE BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_data(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    result = run_strategy(df, LOOKBACK, ATR_MULT)

    if result is None:
        return jsonify({"error": "No trades"})

    return jsonify({
        "symbol": symbol,
        "balance": round(result["balance"], 2),
        "sharpe": round(result["sharpe"], 4),
        "trades": result["trades"]
    })


# =========================
# 🔥 PORTFOLIO BACKTEST
# =========================
@app.route("/portfolio")
def portfolio():
    results = []
    total_balance = 0
    sharpes = []
    total_trades = 0

    for symbol in SYMBOLS:
        df = get_data(symbol)

        if df is None:
            continue

        result = run_strategy(df, LOOKBACK, ATR_MULT)

        if result is None:
            continue

        results.append({
            "symbol": symbol,
            "balance": round(result["balance"], 2),
            "sharpe": round(result["sharpe"], 4),
            "trades": result["trades"]
        })

        total_balance += result["balance"]
        sharpes.append(result["sharpe"])
        total_trades += result["trades"]

    if len(results) == 0:
        return jsonify({"error": "No valid results"})

    avg_sharpe = sum(sharpes) / len(sharpes)

    return jsonify({
        "portfolio_balance": round(total_balance, 2),
        "average_sharpe": round(avg_sharpe, 4),
        "total_trades": total_trades,
        "assets": results
    })


# =========================
# OPTIMIZER (KEEP FOR TESTING)
# =========================
@app.route("/optimize/<symbol>")
def optimize(symbol):
    df = get_data(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    best = {"score": -999}

    lookback_range = [10, 20, 50]
    atr_range = [1.5, 2.0, 2.5, 3.0]

    for look, atr in itertools.product(lookback_range, atr_range):

        result = run_strategy(df, look, atr)

        if result is None:
            continue

        score = (
            result["sharpe"] * 2 +
            (result["balance"] - 1000) * 0.2 +
            min(result["trades"], 20) * 0.01
        )

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
