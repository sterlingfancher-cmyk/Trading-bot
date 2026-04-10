import os
import pandas as pd
import numpy as np
from flask import Flask, jsonify
import yfinance as yf

app = Flask(__name__)

# =========================
# DATA
# =========================
def get_intraday(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "c",
            "Volume": "v"
        })

        return df.dropna()

    except:
        return pd.DataFrame()

# =========================
# IMPROVED STRATEGY
# =========================
def compute_strategy(df):

    df["ma_fast"] = df["c"].rolling(10).mean()
    df["ma_slow"] = df["c"].rolling(30).mean()
    df["returns"] = df["c"].pct_change()

    # Momentum filter
    df["momentum"] = df["returns"].rolling(3).mean()

    df = df.dropna().copy()

    if df.empty:
        return pd.DataFrame()

    df["signal"] = 0

    # ENTRY (trend + momentum)
    df.loc[
        (df["ma_fast"] > df["ma_slow"]) &
        (df["momentum"] > 0),
        "signal"
    ] = 1

    # EXIT (trend break OR stop/target)
    df.loc[
        (df["ma_fast"] < df["ma_slow"]) |
        (df["returns"] < -0.0025) |
        (df["returns"] > 0.008),
        "signal"
    ] = 0

    df["position"] = df["signal"].shift().fillna(0)
    df["strategy"] = df["position"] * df["returns"]

    return df

# =========================
# METRICS
# =========================
def calculate_metrics(df, symbol):

    if df.empty:
        return {"error": "No trades generated"}

    total_return = df["strategy"].sum()
    trades = int((df["signal"].diff().abs() > 0).sum())
    win_rate = float((df["strategy"] > 0).mean())

    sharpe = 0
    if df["strategy"].std() != 0:
        sharpe = df["strategy"].mean() / df["strategy"].std()

    drawdown = df["strategy"].cumsum().min()

    return {
        "symbol": symbol,
        "balance": round(1000 * (1 + total_return), 2),
        "avg_pnl": round(df["strategy"].mean(), 6),
        "trades": trades,
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
        return jsonify({"error": "No data"})

    df = compute_strategy(df)

    if df.empty:
        return jsonify({"error": "Strategy failed"})

    return jsonify(calculate_metrics(df, symbol))

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
