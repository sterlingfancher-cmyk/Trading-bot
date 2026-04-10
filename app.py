from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf
import time
import os
import requests
import alpaca_trade_api as tradeapi

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 3.0
CACHE_TTL = 300

SYMBOLS = [
    "SPY","QQQ",
    "NVDA","AMD","META","MSFT","AAPL"
]

INITIAL_CAPITAL = 1000
RISK_PER_TRADE = 0.13
MAX_POSITIONS = 4
TOP_N = 4
MAX_TOTAL_RISK = 0.8

# =========================
# API KEYS
# =========================
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")

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
# DATA LOADER (YAHOO + FALLBACK)
# =========================
def safe_download(symbol):

    # ===== TRY YAHOO =====
    for _ in range(2):
        try:
            df = yf.download(
                symbol,
                period="6mo",
                interval="1d",
                progress=False,
                threads=False
            )
            if df is not None and not df.empty:
                return df
        except:
            pass
        time.sleep(0.5)

    # ===== FALLBACK: TWELVE DATA =====
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 120,
            "apikey": TWELVE_API_KEY
        }

        res = requests.get(url, params=params, timeout=5)
        data = res.json()

        if "values" not in data:
            print(f"TwelveData failed: {symbol}")
            return None

        df = pd.DataFrame(data["values"])

        df = df.rename(columns={
            "open": "o",
            "high": "h",
            "low": "l",
            "close": "c",
            "volume": "v"
        })

        df["c"] = df["c"].astype(float)
        df["h"] = df["h"].astype(float)
        df["l"] = df["l"].astype(float)

        df = df.iloc[::-1]
        df.index = pd.to_datetime(df["datetime"])
        df = df.drop(columns=["datetime"])

        return df

    except Exception as e:
        print(f"TwelveData error: {symbol} {e}")
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

    for symbol in SYMBOLS:
        df = safe_download(symbol)

        if df is None or df.empty:
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

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
        "endpoints": ["/signals", "/auto_trade"]
    })

# =========================
# SIGNALS
# =========================
@app.route("/signals")
def signals():

    start_time = time.time()
    data = load_data()
    capital = float(request.args.get("capital", INITIAL_CAPITAL))

    spy_df = data.get("SPY")

    if spy_df is None:
        return jsonify({
            "market": "unknown",
            "signals": [],
            "warning": "All data providers failed"
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

    total_risk_budget = capital * MAX_TOTAL_RISK
    used_risk = 0
    signals = []

    for symbol, _ in rs[:TOP_N]:

        if time.time() - start_time > 8:
            break

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

        signals.append({
            "symbol": symbol,
            "price": round(entry, 2),
            "shares": shares,
            "stop": round(stop, 2)
        })

        used_risk += risk_amount

    return jsonify({
        "date": str(last_date),
        "market": "bullish",
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

    spy_df = data.get("SPY")
    if spy_df is None:
        return jsonify({"error": "No data available"})

    last_date = spy_df.index[-1]

    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({"status": "No trades"})

    executed = []

    for symbol in SYMBOLS:

        df = data.get(symbol)
        if df is None or last_date not in df.index:
            continue

        row = df.loc[last_date]

        if not (row["c"] > row["ma"] and row["c"] > row["high_break"] and row["atr_change"] > 0):
            continue

        try:
            api.submit_order(
                symbol=symbol,
                qty=1,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

            executed.append(symbol)

        except Exception as e:
            executed.append({symbol: str(e)})

    return jsonify({"executed": executed})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
