from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 2.5

SYMBOLS = [
    "SPY", "QQQ", "IWM",
    "XLE", "XLK", "XLF", "XLV",
    "XLI", "XLP", "XLY",
    "GLD", "SLV",
    "TLT",
    "ARKK",
    "SMH"
]

INITIAL_CAPITAL = 1000
RISK_PER_TRADE = 0.1
MAX_POSITIONS = 3
TOP_N = 3

BREAKOUT_THRESHOLD = 0.01
TRANSACTION_COST = 0.001
MAX_TOTAL_RISK = 0.3


# =========================
# DATA
# =========================
def get_data(symbol):
    df = yf.download(symbol, period="5y", interval="1d", progress=False)

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
# PREP
# =========================
def prepare(df):
    df["ma_200"] = df["c"].rolling(200).mean()
    df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(
            abs(df["h"] - prev_close),
            abs(df["l"] - prev_close)
        )
    )

    df["atr"] = tr.rolling(14).mean()
    df["atr_change"] = df["atr"].pct_change()
    df["momentum"] = df["c"] / df["c"].shift(50)

    return df.dropna()


# =========================
# PORTFOLIO ENGINE
# =========================
@app.route("/portfolio")
def portfolio():

    data = {}
    for symbol in SYMBOLS:
        df = get_data(symbol)
        if df is not None:
            data[symbol] = prepare(df)

    # 🔥 SPY regime filter data
    spy_df = prepare(get_data("SPY"))

    all_dates = sorted(set().union(*[df.index for df in data.values()]))

    capital = INITIAL_CAPITAL
    equity_curve = []

    positions = {}
    entry_price = {}
    peak_price = {}
    position_size = {}

    trade_log = []

    for date in all_dates:

        # =========================
        # 🔥 MARKET REGIME FILTER
        # =========================
        if date not in spy_df.index:
            continue

        spy_row = spy_df.loc[date]

        market_trend = spy_row["c"] > spy_row["ma_200"]

        if not market_trend:
            equity_curve.append(capital)
            continue

        # =========================
        # EXITS
        # =========================
        for symbol in list(positions.keys()):

            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]

            peak_price[symbol] = max(peak_price[symbol], row["c"])
            stop = peak_price[symbol] - (ATR_MULT * row["atr"])
            trend_break = row["c"] < row["ma_200"]

            if row["c"] < stop or trend_break:
                pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]
                pct -= TRANSACTION_COST

                pnl = position_size[symbol] * pct
                capital += pnl

                trade_log.append({
                    "symbol": symbol,
                    "entry": entry_price[symbol],
                    "exit": row["c"],
                    "return_pct": round(pct, 4),
                    "pnl": round(pnl, 2)
                })

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

        # =========================
        # RELATIVE STRENGTH
        # =========================
        rs_list = []

        for symbol, df in data.items():
            if date in df.index:
                rs_list.append((symbol, df.loc[date]["momentum"]))

        rs_list = sorted(rs_list, key=lambda x: x[1], reverse=True)
        top_symbols = [s[0] for s in rs_list[:TOP_N]]

        # =========================
        # RISK CONTROL
        # =========================
        total_allocated = sum(position_size.values())
        available_risk = capital * MAX_TOTAL_RISK - total_allocated

        # =========================
        # ENTRIES
        # =========================
        for symbol in top_symbols:

            if symbol in positions:
                continue

            if len(positions) >= MAX_POSITIONS:
                break

            if available_risk <= 0:
                break

            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]

            trend = row["c"] > row["ma_200"]
            vol = row["atr_change"] > 0
            breakout_strength = (row["c"] - row["high_break"]) / row["high_break"]

            if trend and vol and breakout_strength > BREAKOUT_THRESHOLD:

                base_risk = capital * RISK_PER_TRADE

                size_multiplier = breakout_strength / BREAKOUT_THRESHOLD
                size_multiplier = max(0.5, min(size_multiplier, 2))

                risk_amount = min(base_risk * size_multiplier, available_risk)

                positions[symbol] = True
                entry_price[symbol] = row["c"]
                peak_price[symbol] = row["c"]
                position_size[symbol] = risk_amount

                available_risk -= risk_amount

        equity_curve.append(capital)

    # =========================
    # METRICS
    # =========================
    returns = pd.Series(equity_curve).pct_change().dropna()

    sharpe = returns.mean() / (returns.std() + 1e-9)
    max_dd = (pd.Series(equity_curve) / pd.Series(equity_curve).cummax() - 1).min()

    wins = [t for t in trade_log if t["return_pct"] > 0]
    win_rate = len(wins) / len(trade_log) if trade_log else 0

    return jsonify({
        "final_balance": round(capital, 2),
        "total_trades": len(trade_log),
        "win_rate": round(win_rate, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 3),
        "active_positions": len(positions),
        "recent_trades": trade_log[-5:]
    })


@app.route("/")
def home():
    return jsonify({"status": "production-ready"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
