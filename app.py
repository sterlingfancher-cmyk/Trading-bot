from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf
import time
import os

import alpaca_trade_api as tradeapi

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 3.0
CACHE_TTL = 300

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

# =========================
# ALPACA CONFIG
# =========================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED", "false").lower() == "true"
REQUIRE_CONFIRM = os.environ.get("REQUIRE_CONFIRM", "true").lower() == "true"

api = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL, api_version='v2')

# =========================
# CACHE
# =========================
DATA = None
LAST_FETCH = 0

# =========================
# SAFE DOWNLOAD (FIXED)
# =========================
def safe_download(symbol):
    for i in range(3):
        try:
            df = yf.download(
                symbol,
                period="6mo",
                interval="1d",
                progress=False,
                threads=False  # 🔥 critical fix
            )

            if df is not None and not df.empty:
                return df

        except Exception as e:
            print(f"{symbol} attempt {i+1} failed: {e}")

        time.sleep(1)

    return None

# =========================
# LOAD DATA
# =========================
def load_data():
    global DATA, LAST_FETCH

    now = time.time()

    if DATA is not None and (now - LAST_FETCH) < CACHE_TTL:
        return DATA

    data = {}

    symbols_ordered = ["SPY"] + [s for s in SYMBOLS if s != "SPY"]

    for symbol in symbols_ordered:
        df = safe_download(symbol)

        if df is None or df.empty:
            print(f"FAILED: {symbol}")
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

    print(f"Loaded symbols: {list(data.keys())}")

    DATA = data
    LAST_FETCH = now

    return data

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "live",
        "endpoints": ["/signals", "/portfolio", "/auto_trade"]
    })

# =========================
# SIGNALS
# =========================
@app.route("/signals")
def signals():

    data = load_data()
    capital = float(request.args.get("capital", INITIAL_CAPITAL))

    spy_df = data.get("SPY")

    if spy_df is None:
        return jsonify({
            "date": None,
            "market": "unknown",
            "signals": [],
            "warning": "SPY failed to load - retry"
        })

    last_date = spy_df.index[-1]

    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({
            "date": str(last_date),
            "market": "bearish",
            "signals": []
        })

    rs = []
    for symbol, df in data.items():
        if last_date in df.index:
            rs.append((symbol, df.loc[last_date]["momentum"]))

    rs = sorted(rs, key=lambda x: x[1], reverse=True)
    top_symbols = [s[0] for s in rs[:TOP_N]]

    total_risk_budget = capital * MAX_TOTAL_RISK
    used_risk = 0
    positions_taken = 0

    signals = []

    for symbol in top_symbols:

        if positions_taken >= MAX_POSITIONS:
            break

        df = data.get(symbol)
        if df is None or last_date not in df.index:
            continue

        row = df.loc[last_date]

        if not (row["c"] > row["ma"] and row["c"] > row["high_break"] and row["atr_change"] > 0):
            continue

        entry = row["c"]
        stop = entry - (ATR_MULT * row["atr"])
        risk_per_share = entry - stop

        if risk_per_share <= 0:
            continue

        risk_amount = capital * RISK_PER_TRADE

        if used_risk + risk_amount > total_risk_budget:
            risk_amount = total_risk_budget - used_risk

        if risk_amount <= 0:
            break

        shares = int(risk_amount / risk_per_share)

        if shares <= 0:
            continue

        signals.append({
            "symbol": symbol,
            "price": round(entry, 2),
            "stop": round(stop, 2),
            "shares": shares,
            "position_size": round(shares * entry, 2),
            "risk_amount": round(risk_amount, 2)
        })

        used_risk += risk_amount
        positions_taken += 1

    return jsonify({
        "date": str(last_date),
        "market": "bullish",
        "capital": capital,
        "signals": signals
    })

# =========================
# AUTO TRADE
# =========================
@app.route("/auto_trade")
def auto_trade():

    if not AUTO_TRADING_ENABLED:
        return jsonify({"error": "Auto trading disabled"})

    if REQUIRE_CONFIRM and request.args.get("confirm") != "true":
        return jsonify({"error": "Add ?confirm=true"})

    if api is None:
        return jsonify({"error": "Alpaca not configured"})

    data = load_data()
    capital = float(request.args.get("capital", INITIAL_CAPITAL))

    spy_df = data.get("SPY")

    if spy_df is None:
        return jsonify({"error": "SPY missing"})

    last_date = spy_df.index[-1]

    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({"status": "No trades - bearish"})

    current_positions = {p.symbol for p in api.list_positions()}

    executed = []
    used_risk = 0
    total_risk_budget = capital * MAX_TOTAL_RISK

    rs = [(s, d.loc[last_date]["momentum"]) for s, d in data.items() if last_date in d.index]
    rs = sorted(rs, key=lambda x: x[1], reverse=True)

    for symbol, _ in rs[:TOP_N]:

        if symbol in current_positions:
            continue

        df = data[symbol]
        row = df.loc[last_date]

        if not (row["c"] > row["ma"] and row["c"] > row["high_break"] and row["atr_change"] > 0):
            continue

        entry = row["c"]
        stop = entry - (ATR_MULT * row["atr"])
        risk_per_share = entry - stop

        if risk_per_share <= 0:
            continue

        risk_amount = capital * RISK_PER_TRADE

        if used_risk + risk_amount > total_risk_budget:
            risk_amount = total_risk_budget - used_risk

        shares = int(risk_amount / risk_per_share)

        if shares <= 0:
            continue

        try:
            api.submit_order(
                symbol=symbol,
                qty=shares,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

            executed.append({"symbol": symbol, "shares": shares})

            used_risk += risk_amount

        except Exception as e:
            executed.append({"symbol": symbol, "error": str(e)})

    return jsonify({
        "executed_trades": executed,
        "total_risk_used": round(used_risk, 2)
    })

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
