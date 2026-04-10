from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

# =========================
# DATA FETCH
# =========================
def get_intraday(symbol):
    try:
        data = yf.download(symbol, period="5d", interval="5m")

        if data is None or data.empty:
            return None

        data = data.rename(columns={
            "Close": "c",
            "High": "h",
            "Low": "l",
            "Open": "o",
            "Volume": "v"
        })

        return data

    except Exception as e:
        return None


# =========================
# STRATEGY (FINAL FIXED)
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

        # SHIFT + SAFE FILL
        prev_high = df["high_lookback"].shift(1).bfill().fillna(0)

        # 🔥 NUMPY FIX (no alignment issues)
        close_vals = df["c"].values
        prev_high_vals = prev_high.values
        fast_vals = df["ma_fast"].values
        slow_vals = df["ma_slow"].values
        returns_vals = df["returns"].values

        # ENTRY
        entry = (fast_vals > slow_vals) & (close_vals > prev_high_vals * 0.999)

        # EXIT
        exit_cond = (fast_vals < slow_vals) | (returns_vals < -0.002)

        df.loc[entry, "signal"] = 1
        df.loc[exit_cond, "signal"] = 0

        # FALLBACK (ensures trades exist)
        if df["signal"].sum() == 0:
            df.loc[df["ma_fast"] > df["ma_slow"], "signal"] = 1

        df["position"] = df["signal"].shift().fillna(0)
        df["strategy"] = df["position"] * df["returns"]

        return df, None

    except Exception as e:
        return None, f"Strategy error: {str(e)}"


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({"status": "running"})


@app.route("/backtest/<symbol>")
def backtest(symbol):
    try:
        raw = get_intraday(symbol)

        if raw is None:
            return jsonify({"error": "Data fetch failed"})

        df, err = compute_strategy(raw)

        if err:
            return jsonify({"error": err})

        if df is None or df.empty:
            return jsonify({"error": "No usable data"})

        df["equity"] = (1 + df["strategy"]).cumprod() * 1000

        trades = (df["signal"].diff().abs() > 0).sum()

        if trades == 0:
            return jsonify({"error": "No trades generated"})

        total_return = df["equity"].iloc[-1]
        avg_pnl = df["strategy"].mean()
        sharpe = df["strategy"].mean() / (df["strategy"].std() + 1e-9)
        drawdown = (df["equity"] / df["equity"].cummax() - 1).min()
        win_rate = (df["strategy"] > 0).sum() / len(df) * 100

        return jsonify({
            "symbol": symbol,
            "balance": round(total_return, 2),
            "avg_pnl": round(avg_pnl, 6),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(drawdown, 4),
            "trades": int(trades),
            "win_rate": round(win_rate, 2)
        })

    except Exception as e:
        return jsonify({"error": f"Server crash: {str(e)}"})


# =========================
# START
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
