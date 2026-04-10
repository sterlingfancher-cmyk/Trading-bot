from flask import Flask, jsonify
import pandas as pd
import numpy as np
import yfinance as yf

app = Flask(__name__)

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

TRANSACTION_COST = 0.001
MAX_TOTAL_RISK = 0.3

BREAKOUT_LOOKBACK = 5


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


def prepare(df):
    df["ma_200"] = df["c"].rolling(200).mean()
    df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(abs(df["h"] - prev_close), abs(df["l"] - prev_close))
    )

    df["atr"] = tr.rolling(14).mean()
    df["atr_change"] = df["atr"].pct_change()
    df["momentum"] = df["c"] / df["c"].shift(50)

    return df.dropna()


@app.route("/portfolio")
def portfolio():

    data = {}
    for symbol in SYMBOLS:
        df = get_data(symbol)
        if df is not None:
            data[symbol] = prepare(df)

    spy_df = prepare(get_data("SPY"))

    all_dates = sorted(set().union(*[df.index for df in data.values()]))

    capital = INITIAL_CAPITAL
    equity_curve = []

    positions = {}
    entry_price = {}
    peak_price = {}
    position_size = {}

    trade_log = []

    breakout_age = {s: 999 for s in SYMBOLS}

    for date in all_dates:

        # REGIME FILTER
        if date not in spy_df.index:
            continue

        if spy_df.loc[date]["c"] <= spy_df.loc[date]["ma_200"]:
            equity_curve.append(capital)
            continue

        # UPDATE BREAKOUT STATE
        for symbol, df in data.items():
            if date not in df.index:
                continue

            row = df.loc[date]

            if row["c"] > row["high_break"]:
                breakout_age[symbol] = 0
            else:
                breakout_age[symbol] += 1

        # EXITS
        for symbol in list(positions.keys()):
            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]

            peak_price[symbol] = max(peak_price[symbol], row["c"])
            stop = peak_price[symbol] - (ATR_MULT * row["atr"])

            if row["c"] < stop or row["c"] < row["ma_200"]:
                pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]
                pct -= TRANSACTION_COST

                capital += position_size[symbol] * pct

                trade_log.append({
                    "symbol": symbol,
                    "entry": entry_price[symbol],
                    "exit": row["c"],
                    "return_pct": round(pct, 4)
                })

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

        # RELATIVE STRENGTH
        rs = []
        for symbol, df in data.items():
            if date in df.index:
                rs.append((symbol, df.loc[date]["momentum"]))

        rs = sorted(rs, key=lambda x: x[1], reverse=True)
        top_symbols = [s[0] for s in rs[:TOP_N]]

        total_allocated = sum(position_size.values())
        available_risk = capital * MAX_TOTAL_RISK - total_allocated

        # ENTRIES (FIXED PULLBACK)
        for symbol in top_symbols:

            if symbol in positions:
                continue

            if len(positions) >= MAX_POSITIONS or available_risk <= 0:
                break

            df = data[symbol]
            if date not in df.index:
                continue

            row = df.loc[date]
            prev = df.shift(1).loc[date]

            trend = row["c"] > row["ma_200"]
            recent_breakout = breakout_age[symbol] <= BREAKOUT_LOOKBACK

            # 🔥 FIXED PULLBACK
            pullback = row["c"] <= row["high_break"] * 1.02
            bounce = row["c"] > prev["c"]
            vol = row["atr_change"] > 0

            if trend and recent_breakout and pullback and bounce and vol:

                risk = min(capital * RISK_PER_TRADE, available_risk)

                positions[symbol] = True
                entry_price[symbol] = row["c"]
                peak_price[symbol] = row["c"]
                position_size[symbol] = risk

                available_risk -= risk

        equity_curve.append(capital)

    returns = pd.Series(equity_curve).pct_change().dropna()

    sharpe = returns.mean() / (returns.std() + 1e-9)
    max_dd = (pd.Series(equity_curve) / pd.Series(equity_curve).cummax() - 1).min()

    return jsonify({
        "final_balance": round(capital, 2),
        "trades": len(trade_log),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 3)
    })


@app.route("/")
def home():
    return jsonify({"status": "final-fixed-system"})
