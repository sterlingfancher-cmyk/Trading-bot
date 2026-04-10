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

TRANSACTION_COST = 0.001
MAX_TOTAL_RISK = 0.3

BREAKOUT_LOOKBACK = 5

# =========================
# LOAD DATA ON STARTUP
# =========================
def load_all_data():
    data = {}

    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)

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

            # Indicators
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

            data[symbol] = df.dropna()

        except Exception as e:
            print(f"FAILED: {symbol} -> {e}")

    return data


print("🚀 Loading market data...")
DATA = load_all_data()
print(f"✅ Loaded {len(DATA)} symbols")


# =========================
# PORTFOLIO
# =========================
@app.route("/portfolio")
def portfolio():

    if len(DATA) == 0:
        return jsonify({"error": "No data loaded"})

    spy_df = DATA.get("SPY")
    if spy_df is None:
        return jsonify({"error": "SPY missing"})

    all_dates = sorted(set().union(*[df.index for df in DATA.values()]))

    capital = INITIAL_CAPITAL

    positions = {}
    entry_price = {}
    peak_price = {}
    position_size = {}

    breakout_age = {s: 999 for s in DATA.keys()}

    trade_count = 0

    for date in all_dates:

        # =========================
        # REGIME FILTER
        # =========================
        if date not in spy_df.index:
            continue

        if spy_df.loc[date]["c"] <= spy_df.loc[date]["ma_200"]:
            continue

        # =========================
        # UPDATE BREAKOUT STATE
        # =========================
        for symbol, df in DATA.items():

            if date not in df.index:
                continue

            row = df.loc[date]

            if row["c"] > row["high_break"]:
                breakout_age[symbol] = 0
            else:
                breakout_age[symbol] += 1

        # =========================
        # EXITS
        # =========================
        for symbol in list(positions.keys()):

            df = DATA[symbol]

            if date not in df.index:
                continue

            row = df.loc[date]

            peak_price[symbol] = max(peak_price[symbol], row["c"])
            stop = peak_price[symbol] - (ATR_MULT * row["atr"])

            if row["c"] < stop or row["c"] < row["ma_200"]:

                pct = (row["c"] - entry_price[symbol]) / entry_price[symbol]
                pct -= TRANSACTION_COST

                capital += position_size[symbol] * pct

                del positions[symbol]
                del entry_price[symbol]
                del peak_price[symbol]
                del position_size[symbol]

                trade_count += 1

        # =========================
        # RELATIVE STRENGTH
        # =========================
        rs = []

        for symbol, df in DATA.items():
            if date in df.index:
                rs.append((symbol, df.loc[date]["momentum"]))

        rs = sorted(rs, key=lambda x: x[1], reverse=True)
        top_symbols = [s[0] for s in rs[:TOP_N]]

        total_allocated = sum(position_size.values())
        available_risk = capital * MAX_TOTAL_RISK - total_allocated

        # =========================
        # ENTRIES
        # =========================
        for symbol in top_symbols:

            if symbol in positions:
                continue

            if len(positions) >= MAX_POSITIONS or available_risk <= 0:
                break

            df = DATA[symbol]

            if date not in df.index:
                continue

            row = df.loc[date]
            prev = df.shift(1).loc[date]

            trend = row["c"] > row["ma_200"]
            recent_breakout = breakout_age[symbol] <= BREAKOUT_LOOKBACK

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

    return jsonify({
        "final_balance": round(capital, 2),
        "trades": trade_count,
        "active_positions": len(positions)
    })


@app.route("/")
def home():
    return jsonify({"status": "full-system-live"})
