import os
import pandas as pd
import numpy as np
from flask import Flask, jsonify
import yfinance as yf

app = Flask(__name__)

# =========================
# DATA FETCH
# =========================
def get_intraday(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        df = df.rename(columns={
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "c",
            "Volume": "v"
        })
        df = df.dropna()
        return df
    except:
        return pd.DataFrame()

# =========================
# STRATEGY
# =========================
def compute_strategy(df, fast=20, slow=50, entry=0.0002, exit_profit=0.002, stop_loss=-0.002):

    df["ma_fast"] = df["c"].rolling(fast).mean()
    df["ma_slow"] = df["c"].rolling(slow).mean()
    df["returns"] = df["c"].pct_change()

    df["signal"] = 0

    strength = (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]

    # ENTRY
    df.loc[
        (df["ma_fast"] > df["ma_slow"]) &
        (df["returns"] > entry) &
        (strength > entry),
        "signal"
    ] = 1

    # EXIT
    df.loc[
        (df["returns"] < stop_loss) |
        (df["returns"] > exit_profit),
        "signal"
    ] = 0

    df["position"] = df["signal"].shift().fillna(0)
    df["strategy"] = df["position"] * df["returns"]

    return df

# =========================
# METRICS
# =========================
def calculate_metrics(df, symbol):
    if df.empty or "strategy" not in df:
        return {"error": "No data"}

    total_return = df["strategy"].sum()
    trades = (df["signal"].diff().abs() > 0).sum()

    wins = df[df["strategy"] > 0]
    win_rate = len(wins) / len(df) if len(df) > 0 else 0

    sharpe = 0
    if df["strategy"].std() != 0:
        sharpe = df["strategy"].mean() / df["strategy"].std()

    drawdown = (df["strategy"].cumsum().min())

    return {
        "symbol": symbol,
        "balance": round(1000 * (1 + total_return), 2),
        "avg_pnl": round(df["strategy"].mean(), 6),
        "trades": int(trades),
        "win_rate": round(win_rate * 100, 2),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(drawdown, 4)
    }

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return jsonify({"status": "RUNNING"})

@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_intraday(symbol)

    if df.empty:
        return jsonify({"error": "No data fetched"})

    df = compute_strategy(df)
    results = calculate_metrics(df, symbol)

    return jsonify(results)

@app.route("/optimize/<symbol>")
def optimize(symbol):
    df = get_intraday(symbol)

    if df.empty:
        return jsonify({"error": "No data fetched"})

    best = None

    for fast in [10, 20]:
        for slow in [30, 50]:
            for entry in [0.0001, 0.0002]:
                df_test = compute_strategy(df.copy(), fast, slow, entry)
                results = calculate_metrics(df_test, symbol)

                if "error" in results:
                    continue

                if best is None or results["sharpe"] > best["sharpe"]:
                    best = results

    return jsonify(best if best else {"error": "No valid strategy found"})

# =========================
# RUN (RAILWAY FIX)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
