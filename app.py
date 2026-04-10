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
    try:
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

    except Exception as e:
        print("DATA ERROR:", e)
        return None


# =========================
# STRATEGY (REGIME FILTER)
# =========================
def run_strategy(df, fast, slow, sl_mult, vol_thresh, trend_thresh):
    try:
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

        # 🔥 NEW: trend strength filter
        df["trend_strength"] = abs(df["ma_fast"] - df["ma_slow"]) / df["c"]

        df = df.dropna()

        capital = 1000
        position = 0
        entry_price = 0
        entry_atr = 0
        peak_price = 0

        trades = []

        for i in range(len(df)):
            row = df.iloc[i]

            # ENTRY
            if position == 0:
                if (
                    row["ma_fast"] > row["ma_slow"] and
                    row["vol"] > vol_thresh and
                    row["trend_strength"] > trend_thresh
                ):
                    position = 1
                    entry_price = row["c"]
                    entry_atr = row["atr"]
                    peak_price = row["c"]

            # EXIT
            else:
                peak_price = max(peak_price, row["c"])
                trailing_stop = peak_price - (sl_mult * entry_atr)

                if (
                    row["c"] <= trailing_stop or
                    row["ma_fast"] < row["ma_slow"]
                ):
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

    except Exception as e:
        return {"error": str(e)}


# =========================
# BACKTEST
# =========================
@app.route("/backtest/<symbol>")
def backtest(symbol):
    df = get_intraday(symbol)

    if df is None:
        return jsonify({"error": "Data fetch failed"})

    result = run_strategy(df, 10, 30, 1.5, 0.0005, 0.001)

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
    vol_range = [0.0002, 0.0005, 0.0008]
    trend_range = [0.0005, 0.001, 0.002]

    for fast, slow, sl, vol, trend in itertools.product(
        fast_range, slow_range, sl_range, vol_range, trend_range
    ):
        if fast >= slow:
            continue

        result = run_strategy(df, fast, slow, sl, vol, trend)

        if result is None:
            continue

        score = (
            result["sharpe"] * 2 +
            (result["balance"] - 1000) * 0.1 +
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
                    "vol_thresh": vol,
                    "trend_thresh": trend
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
