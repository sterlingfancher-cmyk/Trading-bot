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
    df = yf.download(symbol, period="5d", interval="5m", progress=False)

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
# STRATEGY (WITH EQUITY)
# =========================
def run_strategy(df, fast, slow, sl_mult, tp_mult, vol_thresh):
    df = df.copy()

    df["ma_fast"] = df["c"].rolling(fast).mean()
    df["ma_slow"] = df["c"].rolling(slow).mean()

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(
            abs(df["h"] - prev_close),
            abs(df["l"] - prev_close)
        )
    )
    df["atr"] = tr.rolling(14).mean()

    df["returns"] = df["c"].pct_change()
    df["vol"] = df["returns"].rolling(10).std()

    df = df.dropna()

    capital = 1000
    risk_per_trade = 0.1  # 10% capital per trade

    position = 0
    entry_price = 0
    entry_atr = 0

    equity_curve = []
    trade_results = []

    for i in range(len(df)):
        row = df.iloc[i]

        if position == 0:
            if row["ma_fast"] > row["ma_slow"] and row["vol"] > vol_thresh:
                position = 1
                entry_price = row["c"]
                entry_atr = row["atr"]

        else:
            move = row["c"] - entry_price
            stop = -sl_mult * entry_atr
            target = tp_mult * entry_atr

            if move <= stop or move >= target or row["ma_fast"] < row["ma_slow"]:
                pct_return = move / entry_price

                trade_return = capital * risk_per_trade * pct_return
                capital += trade_return

                trade_results.append(pct_return)
                position = 0

        equity_curve.append(capital)

    if len(trade_results) == 0:
        return None

    sharpe = np.mean(trade_results) / (np.std(trade_results) + 1e-9)

    return {
        "balance": capital,
        "sharpe": sharpe,
        "trades": len(trade_results)
    }


# =========================
# BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    result = run_strategy(df, 10, 30, 1.5, 2.5, 0.0005)

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

    fast_range = [5, 8, 10, 12]
    slow_range = [15, 20, 30, 40]
    sl_range = [1.0, 1.5, 2.0]
    tp_range = [2.0, 2.5, 3.0]
    vol_range = [0.0002, 0.0005, 0.0008]

    for fast, slow, sl, tp, vol in itertools.product(
        fast_range, slow_range, sl_range, tp_range, vol_range
    ):
        if fast >= slow:
            continue

        result = run_strategy(df, fast, slow, sl, tp, vol)

        if result is None:
            continue

        score = (
            result["sharpe"] * 2 +
            (result["balance"] - 1000) * 0.05 +
            min(result["trades"], 25) * 0.02
        )

        if result["trades"] < 8:
            score *= 0.5

        if score > best["score"]:
            best = {
                "score": round(score, 4),
                "balance": round(result["balance"], 2),
                "sharpe": round(result["sharpe"], 4),
                "trades": result["trades"],
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
