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
            return None, "No data returned from yfinance"

        df = df.rename(columns={
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "c",
            "Volume": "v"
        })

        df = df.dropna()

        if df.empty:
            return None, "Data empty after cleaning"

        return df, None

    except Exception as e:
        return None, f"Data error: {str(e)}"

# =========================
# STRATEGY
# =========================
def compute_strategy(df):
    try:
        df["ma_fast"] = df["c"].rolling(20).mean()
        df["ma_slow"] = df["c"].rolling(50).mean()
        df["returns"] = df["c"].pct_change()

        df["high_lookback"] = df["h"].rolling(10, min_periods=3).max()

        df = df.dropna().copy()

        if df.empty:
            return None, "Empty after indicators"

        df["signal"] = 0

        prev_high = df["high_lookback"].shift(1).fillna(0)

        df.loc[
            (df["ma_fast"] > df["ma_slow"]) &
            (df["c"] > prev_high * 0.999),
            "signal"
        ] = 1

        df.loc[
            (df["ma_fast"] < df["ma_slow"]) |
            (df["returns"] < -0.002),
            "signal"
        ] = 0

        # Fallback if no trades
        if df["signal"].sum() == 0:
            df.loc[df["ma_fast"] > df["ma_slow"], "signal"] = 1

        df["position"] = df["signal"].shift().fillna(0)
        df["strategy"] = df["position"] * df["returns"]

        return df, None

    except Exception as e:
        return None, f"Strategy error: {str(e)}"

# =========================
# METRICS
# =========================
def calculate_metrics(df, symbol):
    try:
        if df is None or df.empty:
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

    except Exception as e:
        return {"error": f"Metrics error: {str(e)}"}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({"status": "RUNNING"})

@app.route("/backtest/<symbol>")
def backtest(symbol):
    try:
        df, error = get_intraday(symbol)
        if error:
            return jsonify({"error": error})

        df, error = compute_strategy(df)
        if error:
            return jsonify({"error": error})

        return jsonify(calculate_metrics(df, symbol))

    except Exception as e:
        return jsonify({"error": f"Fatal error: {str(e)}"})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
