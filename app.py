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
    df = yf.download(symbol, period="5d", interval="5m", progress=False)
    df = df.rename(columns={
        "Open": "o",
        "High": "h",
        "Low": "l",
        "Close": "c",
        "Volume": "v"
    })
    return df.dropna()

# =========================
# STRATEGY (FIXED VERSION)
# =========================
def compute_strategy(df):

    # Indicators
    df["ma_fast"] = df["c"].rolling(20).mean()
    df["ma_slow"] = df["c"].rolling(60).mean()
    df["returns"] = df["c"].pct_change()

    # Trend strength
    df["trend"] = (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]

    # Volatility filter
    df["volatility"] = df["returns"].rolling(10).std()

    df["signal"] = 0

    # =========================
    # ENTRY (MORE RELIABLE)
    # =========================
    df.loc[
        (df["trend"] > 0.001) &                        # stronger trend
        (df["ma_fast"] > df["ma_slow"]) &              # trend direction
        (df["ma_fast"].shift(1) > df["ma_slow"].shift(1)) &  # confirmation (not just crossing)
        (df["volatility"] > 0.0005),                   # avoid dead zones
        "signal"
    ] = 1

    # =========================
    # HOLD POSITIONS LONGER
    # =========================
    cooldown = 12  # MUCH stronger filter
    for i in range(1, len(df)):
        if df["signal"].iloc[i] == 1:
            df.iloc[i:i+cooldown, df.columns.get_loc("signal")] = 1

    # =========================
    # BETTER EXIT LOGIC
    # =========================
    df.loc[
        (df["returns"] < -0.004) |   # stop loss
        (df["returns"] > 0.01),      # take profit
        "signal"
    ] = 0

    # Position
    df["position"] = df["signal"].shift().fillna(0)
    df["strategy"] = df["position"] * df["returns"]

    return df

# =========================
# METRICS
# =========================
def calculate_metrics(df, symbol):

    total_return = df["strategy"].sum()
    trades = (df["signal"].diff().abs() > 0).sum()

    win_rate = (df["strategy"] > 0).mean()

    sharpe = 0
    if df["strategy"].std() != 0:
        sharpe = df["strategy"].mean() / df["strategy"].std()

    drawdown = df["strategy"].cumsum().min()

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
    df = compute_strategy(df)
    return jsonify(calculate_metrics(df, symbol))

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
