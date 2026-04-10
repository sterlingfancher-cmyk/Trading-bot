from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf
import itertools

app = Flask(__name__)

# =========================
# DATA FETCH
# =========================
def get_intraday(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)

        if df is None or df.empty:
            return None

        # Flatten multi-index
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns={
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "c",
            "Volume": "v"
        })

        df = df[["o", "h", "l", "c", "v"]].dropna()

        return df

    except Exception as e:
        print("DATA ERROR:", e)
        return None


# =========================
# STRATEGY ENGINE
# =========================
def run_strategy(df, fast, slow, atr_mult_sl, atr_mult_tp, vol_thresh):
    try:
        df = df.copy()

        # Indicators
        df["ma_fast"] = df["c"].rolling(fast).mean()
        df["ma_slow"] = df["c"].rolling(slow).mean()

        prev_close = df["c"].shift(1)
        tr1 = df["h"] - df["l"]
        tr2 = (df["h"] - prev_close).abs()
        tr3 = (df["l"] - prev_close).abs()

        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
        df["atr"] = df["tr"].rolling(14).mean()

        df["returns"] = df["c"].pct_change()
        df["vol"] = df["returns"].rolling(10).std()

        df = df.dropna()

        if df.empty:
            return None

        position = 0
        entry_price = 0
        entry_atr = 0

        strategy_returns = []

        for i in range(len(df)):
            row = df.iloc[i]

            # ENTRY
            if position == 0:
                if (
                    row["ma_fast"] > row["ma_slow"] and
                    row["vol"] > vol_thresh
                ):
                    position = 1
                    entry_price = row["c"]
                    entry_atr = row["atr"]
                    strategy_returns.append(0)
                else:
                    strategy_returns.append(0)

            # EXIT
            else:
                move = row["c"] - entry_price

                stop = -atr_mult_sl * entry_atr
                target = atr_mult_tp * entry_atr

                if (
                    move <= stop or
                    move >= target or
                    row["ma_fast"] < row["ma_slow"]
                ):
                    ret = move / entry_price
                    strategy_returns.append(ret)
                    position = 0
                else:
                    strategy_returns.append(0)

        df["strategy"] = strategy_returns

        total_return = df["strategy"].sum()
        sharpe = df["strategy"].mean() / (df["strategy"].std() + 1e-9)
        trades = int((df["strategy"] != 0).sum())

        return {
            "total_return": total_return,
            "sharpe": sharpe,
            "trades": trades
        }

    except Exception as e:
        return {"error": str(e)}


# =========================
# BACKTEST ROUTE
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    result = run_strategy(
        df,
        fast=10,
        slow=30,
        atr_mult_sl=1.5,
        atr_mult_tp=2.5,
        vol_thresh=0.0005
    )

    if result is None or "error" in result:
        return jsonify({"error": result})

    balance = 1000 * (1 + result["total_return"])

    return jsonify({
        "symbol": symbol,
        "balance": round(balance, 2),
        "sharpe": round(result["sharpe"], 4),
        "trades": result["trades"]
    })


# =========================
# OPTIMIZER ROUTE (FIXED)
# =========================
@app.route("/optimize/<symbol>")
def optimize(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    best = {
        "score": -999,
        "balance": 0,
        "sharpe": 0,
        "trades": 0,
        "params": {}
    }

    # 🔥 Expanded search space
    fast_range = [5, 6, 8, 10, 12]
    slow_range = [15, 20, 25, 30, 40]
    sl_range = [1.0, 1.5, 2.0]
    tp_range = [2.0, 2.5, 3.0]
    vol_range = [0.0002, 0.0005, 0.0008]

    for fast, slow, sl, tp, vol in itertools.product(
        fast_range, slow_range, sl_range, tp_range, vol_range
    ):
        if fast >= slow:
            continue

        result = run_strategy(df, fast, slow, sl, tp, vol)

        if result is None or "error" in result:
            continue

        balance = 1000 * (1 + result["total_return"])

        # 🔥 Balanced scoring
        score = (
            result["sharpe"] * 2 +
            result["total_return"] * 50 +
            min(result["trades"], 25) * 0.02
        )

        # 🔥 Penalize low trades
        if result["trades"] < 8:
            score *= 0.5

        if score > best["score"]:
            best = {
                "score": round(score, 4),
                "balance": round(balance, 2),
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
# HEALTH CHECK
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
