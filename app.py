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
# STRATEGY (TREND + RISK MGMT)
# =========================
def compute_strategy(df):
    try:
        df = df.copy()

        df["ma_fast"] = df["c"].rolling(10).mean()
        df["ma_slow"] = df["c"].rolling(30).mean()

        df = df.dropna()

        if df.empty:
            return None, "Empty after indicators"

        position = 0
        entry_price = 0

        stop_loss = 0.003   # 0.3%
        take_profit = 0.008 # 0.8%

        signals = []
        returns = []

        for i in range(len(df)):
            row = df.iloc[i]

            if position == 0:
                # ENTRY
                if row["ma_fast"] > row["ma_slow"]:
                    position = 1
                    entry_price = row["c"]
                    signals.append(1)
                    returns.append(0)
                else:
                    signals.append(0)
                    returns.append(0)

            else:
                price_change = (row["c"] - entry_price) / entry_price

                # EXIT CONDITIONS
                if (
                    price_change <= -stop_loss or
                    price_change >= take_profit or
                    row["ma_fast"] < row["ma_slow"]
                ):
                    position = 0
                    signals.append(0)
                    returns.append(price_change)
                else:
                    signals.append(1)
                    returns.append(0)

        df["signal"] = signals
        df["strategy"] = returns

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

        trades = int((df["strategy"] != 0).sum())

        total_return = df["equity"].iloc[-1]
        avg_pnl = df["strategy"].mean()

        sharpe = df["strategy"].mean() / (df["strategy"].std() + 1e-9)
        drawdown = (df["equity"] / df["equity"].cummax() - 1).min()
        win_rate = (df["strategy"] > 0).sum() / max(1, trades) * 100

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
