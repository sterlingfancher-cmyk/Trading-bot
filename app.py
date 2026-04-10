from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 3.0

SYMBOLS = [
    "SPY","QQQ","IWM",
    "XLE","XLK","XLF","XLV","XLI",
    "GLD","SLV",
    "TLT",
    "ARKK","SMH",
    "NVDA","TSLA","AMD","META","MSFT","AAPL"
]

INITIAL_CAPITAL = 1000

RISK_PER_TRADE = 0.13
MAX_POSITIONS = 4
TOP_N = 4
MAX_TOTAL_RISK = 0.8

TRANSACTION_COST = 0.001

DATA = None


# =========================
# LOAD DATA
# =========================
def load_data():
    global DATA

    if DATA is not None:
        return DATA

    data = {}

    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="6mo", interval="1d", progress=False)

            if df is None or df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.rename(columns={
                "Open": "o",
                "High": "h",
                "Low": "l",
                "Close": "c",
                "Volume": "v"
            })

            df["ma"] = df["c"].rolling(100).mean()
            df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

            prev_close = df["c"].shift(1)
            tr = np.maximum(
                df["h"] - df["l"],
                np.maximum(abs(df["h"] - prev_close), abs(df["l"] - prev_close))
            )

            df["atr"] = tr.rolling(14).mean()
            df["atr_change"] = df["atr"].pct_change()
            df["momentum"] = df["c"] / df["c"].shift(20)

            data[symbol] = df.dropna()

        except Exception as e:
            print(f"ERROR loading {symbol}: {e}")

    DATA = data
    return data


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return jsonify({"status": "live-signals-enabled"})


# =========================
# SIGNALS ENDPOINT 🔥
# =========================
@app.route("/signals")
def signals():

    data = load_data()

    signals = []

    spy_df = data.get("SPY")
    if spy_df is None:
        return jsonify({"error": "SPY missing"})

    last_date = spy_df.index[-1]

    # Market regime
    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({
            "date": str(last_date),
            "market": "bearish",
            "signals": []
        })

    # Rank symbols
    rs = []
    for symbol, df in data.items():
        if last_date in df.index:
            rs.append((symbol, df.loc[last_date]["momentum"]))

    rs = sorted(rs, key=lambda x: x[1], reverse=True)
    top_symbols = [s[0] for s in rs[:TOP_N]]

    for symbol in top_symbols:

        df = data[symbol]
        if last_date not in df.index:
            continue

        row = df.loc[last_date]

        trend = row["c"] > row["ma"]
        breakout = row["c"] > row["high_break"]
        vol = row["atr_change"] > 0

        if trend and breakout and vol:

            stop = row["c"] - (ATR_MULT * row["atr"])

            signals.append({
                "symbol": symbol,
                "price": round(row["c"], 2),
                "momentum": round(row["momentum"], 3),
                "stop": round(stop, 2)
            })

    return jsonify({
        "date": str(last_date),
        "market": "bullish",
        "signals": signals
    })


# =========================
# PORTFOLIO (UNCHANGED)
# =========================
@app.route("/portfolio")
def portfolio():

    data = load_data()

    spy_df = data.get("SPY")
    if spy_df is None:
        return jsonify({"error": "SPY missing"})

    all_dates = sorted(set().union(*[df.index for df in data.values()]))

    capital = INITIAL_CAPITAL

    positions = {}
    entry_price = {}
    peak_price = {}
    position_size = {}

    trades = 0

    for date in all_dates:

        if date not in spy_df.index:
            continue

        if spy_df.loc[date]["c"] <= spy_df.loc[date]["ma"]:
            continue

        for symbol in list(positions.keys()):

            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]

            peak_price[symbol] = max(peak_price[symbol], row["c"])
            stop = peak_price[symbol] - (ATR_MULT * row["atr"])

            if row["c"] < stop:

                pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]
                pct -= TRANSACTION_COST

                capital += position_size[symbol] * pct

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

                trades += 1

        rs = []
        for symbol, df in data.items():
            if date in df.index:
                rs.append((symbol, df.loc[date]["momentum"]))

        rs = sorted(rs, key=lambda x: x[1], reverse=True)
        top_symbols = [s[0] for s in rs[:TOP_N]]

        total_allocated = sum(position_size.values())
        available_risk = capital * MAX_TOTAL_RISK - total_allocated

        for symbol in top_symbols:

            if symbol in positions:
                continue

            if len(positions) >= MAX_POSITIONS or available_risk <= 0:
                break

            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]

            trend = row["c"] > row["ma"]
            breakout = row["c"] > row["high_break"]
            vol = row["atr_change"] > 0

            if trend and breakout and vol:

                breakout_strength = (row["c"] - row["high_break"]) / row["high_break"]
                size_multiplier = max(0.5, min(breakout_strength / 0.02, 2))

                risk = min(capital * RISK_PER_TRADE * size_multiplier, available_risk)

                positions[symbol] = True
                entry_price[symbol] = row["c"]
                peak_price[symbol] = row["c"]
                position_size[symbol] = risk

                available_risk -= risk

    return jsonify({
        "final_balance": round(capital, 2),
        "trades": trades,
        "active_positions": len(positions)
    })


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
