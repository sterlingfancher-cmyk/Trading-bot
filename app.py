from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

# =========================
# DATA
# =========================
def get_intraday(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m")

        if df is None or df.empty:
            return None

        # Fix multi-index
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns={
            "Close": "c",
            "High": "h",
            "Low": "l",
            "Open": "o",
            "Volume": "v"
        })

        return df

    except:
        return None


# =========================
# STRATEGY (BREAKOUT + PULLBACK)
# =========================
def compute_strategy(df):
    try:
        df = df.copy()

        df["ma_fast"] = df["c"].rolling(10).mean()
        df["ma_slow"] = df["c"].rolling(30).mean()
        df["returns"] = df["c"].pct_change()

        df["recent_high"] = df["h"].rolling(15).max()

        df = df.dropna()

        if df.empty:
            return None, "Empty after indicators"

        df["signal"] = 0

        # Breakout happened recently
        breakout = df["c"] > df["recent_high"].shift(1)

        # Pullback after breakout
        pullback = df["c"] < df["ma_fast"]

        # Recovery (price turning back up)
        recovery = df["returns"] > 0

        # Trend filter
        trend = df["ma_fast"] > df["ma_slow"]

        # ENTRY (refined)
        df.loc[
            trend & breakout & pullback & recovery,
            "signal"
        ] = 1

        # EXIT
        df.loc[
            (df["ma_fast"] < df["ma_slow"]) |
            (df["returns"] < -0.002) |
            (df["returns"] > 0.01),
            "signal"
        ] = 0

        df["position"] = df["signal"].shift(1).fillna(0)
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

        trades = int((df["signal"].diff().abs() > 0).sum())

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
            "trades": trades,
            "win_rate": round(win_rate, 2)
        })

    except Exception as e:
        return jsonify({"error": f"Server crash: {str(e)}"})


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
