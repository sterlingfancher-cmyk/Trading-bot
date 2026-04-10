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

    except:
        return None


# =========================
# RSI FUNCTION
# =========================
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


# =========================
# STRATEGY (MEAN REVERSION)
# =========================
def run_strategy(df, fast, slow, rsi_low, rsi_high, sl_mult):
    try:
        df = df.copy()

        df["ma_fast"] = df["c"].rolling(fast).mean()
        df["ma_slow"] = df["c"].rolling(slow).mean()
        df["rsi"] = compute_rsi(df["c"])

        prev_close = df["c"].shift(1)
        tr = np.maximum(
            df["h"] - df["l"],
            np.maximum(
                abs(df["h"] - prev_close),
                abs(df["l"] - prev_close)
            )
        )
        df["atr"] = tr.rolling(14).mean()

        df = df.dropna()

        capital = 1000
        position = 0
        entry_price = 0
        entry_atr = 0

        trades = []

        for i in range(len(df)):
            row = df.iloc[i]

            # ENTRY (dip in uptrend)
            if position == 0:
                if (
                    row["ma_fast"] > row["ma_slow"] and
                    row["rsi"] < rsi_low
                ):
                    position = 1
                    entry_price = row["c"]
                    entry_atr = row["atr"]

            # EXIT
            else:
                move = row["c"] - entry_price
                stop = -sl_mult * entry_atr

                if (
                    move <= stop or
                    row["rsi"] > rsi_high or
                    row["ma_fast"] < row["ma_slow"]
                ):
                    pct = move / entry_price
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

    result = run_strategy(df, 10, 30, 30, 60, 1.5)

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

    fast_range = [8, 10, 12]
    slow_range = [20, 30, 40]
    rsi_low_range = [25, 30, 35]
    rsi_high_range = [55, 60, 65]
    sl_range = [1.0, 1.5, 2.0]

    for fast, slow, rl, rh, sl in itertools.product(
        fast_range, slow_range, rsi_low_range, rsi_high_range, sl_range
    ):
        if fast >= slow:
            continue

        result = run_strategy(df, fast, slow, rl, rh, sl)

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
                    "rsi_low": rl,
                    "rsi_high": rh,
                    "atr_sl": sl
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
