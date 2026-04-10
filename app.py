from flask import Flask, jsonify
import requests, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

app = Flask(__name__)

# =========================
# CONFIG
# =========================
POLYGON_API_KEY = "L3SUCdmHWD0ctcfwFAsXBD5pFvHumpQi"
ACCOUNT_SIZE = 1000

# =========================
# HEALTH CHECK
# =========================
@app.route("/")
def home():
    return jsonify({"status": "RUNNING"})

# =========================
# DATA
# =========================
def get_intraday(symbol):
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=5)

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start.date()}/{end.date()}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_API_KEY}"

        r = requests.get(url)
        data = r.json()

        if "results" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["results"])

        if df.empty or "c" not in df.columns:
            return pd.DataFrame()

        return df

    except:
        return pd.DataFrame()

# =========================
# STRATEGY (IMPROVED)
# =========================
def compute_strategy(df):

    df["ma_fast"] = df["c"].rolling(20).mean()
    df["ma_slow"] = df["c"].rolling(50).mean()
    df["returns"] = df["c"].pct_change()

    # 🔥 NEW: volatility filter
    df["volatility"] = df["returns"].rolling(10).std()

    # remove low volatility (chop)
    df = df[df["volatility"] > df["volatility"].rolling(50).mean()]

    df["signal"] = 0.0

    strength = (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]

    # 🔥 IMPROVED ENTRY (stronger filters)
    df.loc[
        (df["ma_fast"] > df["ma_slow"]) &
        (df["returns"] > 0.001) &
        (strength > 0.002) &
        (df["c"] > df["c"].rolling(20).mean()),
        "signal"
    ] = strength

    # SCALE
    df["signal"] = (df["signal"] / 0.04).clip(0, 1)

    # EXIT
    df.loc[
        (df["returns"] < -0.0025) |
        (df["returns"] > 0.005),
        "signal"
    ] = 0

    df = df.dropna(subset=["ma_fast", "ma_slow", "returns"])

    if df.empty:
        return pd.DataFrame()

    # POSITION
    df["position"] = df["signal"].replace(0, np.nan).ffill().fillna(0)

    # RETURNS
    df["strategy_returns"] = df["returns"] * df["position"].shift(1)
    df["strategy_returns"] = df["strategy_returns"].clip(-0.01, 0.02)

    return df

# =========================
# BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    try:
        df = get_intraday(symbol)

        if df.empty:
            return jsonify({"error": "No market data"})

        df = compute_strategy(df)

        if df.empty:
            return jsonify({"error": "Strategy produced no usable data"})

        returns = df["strategy_returns"].dropna()

        if returns.empty:
            return jsonify({"error": "No returns generated"})

        trades = int((df["signal"].diff().abs() > 0).sum())

        avg_pnl = round(returns.mean() * 100, 4)
        balance = round(ACCOUNT_SIZE * (returns + 1).cumprod().iloc[-1], 2)

        sharpe = 0
        if returns.std() != 0:
            sharpe = round((returns.mean() / returns.std()) * np.sqrt(252), 4)

        cum = (returns + 1).cumprod()
        peak = cum.cummax()
        drawdown = (cum - peak) / peak
        max_dd = round(drawdown.min() * 100, 2)

        win_rate = round((returns > 0).mean() * 100, 2)

        return jsonify({
            "symbol": symbol.upper(),
            "trades": trades,
            "avg_pnl": avg_pnl,
            "balance": balance,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# RUN (RAILWAY)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
