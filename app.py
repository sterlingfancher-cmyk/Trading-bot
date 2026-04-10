from flask import Flask, jsonify
import requests, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import itertools

app = Flask(__name__)

POLYGON_API_KEY = "L3SUCdmHWD0ctcfwFAsXBD5pFvHumpQi"
ACCOUNT_SIZE = 1000

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
# STRATEGY CORE
# =========================
def run_strategy(df, fast, slow, ret_th, strength_th):

    df = df.copy()

    df["ma_fast"] = df["c"].rolling(fast).mean()
    df["ma_slow"] = df["c"].rolling(slow).mean()
    df["returns"] = df["c"].pct_change()
    df["volatility"] = df["returns"].rolling(10).std()

    df["signal"] = 0.0

    strength = (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]

    df.loc[
        (df["ma_fast"] > df["ma_slow"]) &
        (df["returns"] > ret_th) &
        (strength > strength_th) &
        (df["volatility"] > df["volatility"].rolling(20).mean()),
        "signal"
    ] = strength

    df["signal"] = (df["signal"] / 0.04).clip(0, 1)

    df["cooldown"] = df["signal"].rolling(5).max().shift(1)
    df.loc[df["cooldown"] > 0, "signal"] = 0

    df["position"] = df["signal"].replace(0, np.nan).ffill().fillna(0)

    df.loc[
        (df["returns"] < -0.0025) |
        (df["returns"] > 0.007),
        "position"
    ] = 0

    df = df.dropna()

    if df.empty:
        return None

    df["strategy_returns"] = df["returns"] * df["position"].shift(1)
    returns = df["strategy_returns"].dropna()

    if returns.empty:
        return None

    trades = int((df["position"].diff().abs() > 0).sum())

    if trades < 10:
        return None

    balance = ACCOUNT_SIZE * (returns + 1).cumprod().iloc[-1]

    sharpe = 0
    if returns.std() != 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)

    return {
        "balance": round(balance, 2),
        "sharpe": round(sharpe, 4),
        "trades": trades
    }

# =========================
# NORMAL BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):

    df = get_intraday(symbol)

    if df.empty:
        return jsonify({"error": "No data"})

    result = run_strategy(df, 20, 50, 0.0006, 0.0012)

    if not result:
        return jsonify({"error": "No trades generated"})

    return jsonify(result)

# =========================
# AUTO OPTIMIZER (ADVANCED)
# =========================
@app.route("/optimize/<symbol>")
def optimize(symbol):

    df = get_intraday(symbol)

    if df.empty:
        return jsonify({"error": "No data"})

    fast_range = [10, 15, 20, 25]
    slow_range = [40, 50, 60, 70]
    return_range = [0.0004, 0.0006, 0.0008]
    strength_range = [0.0008, 0.001, 0.0012]

    best = None

    for fast, slow, ret_th, strength_th in itertools.product(
        fast_range, slow_range, return_range, strength_range
    ):

        if fast >= slow:
            continue

        result = run_strategy(df, fast, slow, ret_th, strength_th)

        if not result:
            continue

        score = result["sharpe"]

        if not best or score > best["score"]:
            best = {
                "score": score,
                "params": {
                    "ma_fast": fast,
                    "ma_slow": slow,
                    "return_threshold": ret_th,
                    "strength": strength_th
                },
                "performance": result
            }

    if not best:
        return jsonify({"error": "No viable strategies found"})

    return jsonify(best)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
