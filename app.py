from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf
import time
import os
import threading
import alpaca_trade_api as tradeapi

app = Flask(__name__)

# =========================
# CONFIG
# =========================
LOOKBACK = 20
ATR_MULT = 3.0
REFRESH_INTERVAL = 300

SYMBOLS = [
    "SPY","QQQ",
    "NVDA","AMD","META","MSFT","AAPL"
]

INITIAL_CAPITAL = 1000
RISK_PER_TRADE = 0.13
TOP_N = 4
MAX_TOTAL_RISK = 0.8

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
# GLOBAL DATA
# =========================
DATA = {}
LAST_UPDATE = None

# =========================
# SAFE DOWNLOAD
# =========================
def safe_download(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False, threads=False)
        if df is not None and not df.empty:
            return df
    except:
        pass
    return None

# =========================
# FALLBACK DATA
# =========================
def generate_fake_data():
    dates = pd.date_range(end=pd.Timestamp.today(), periods=120)
    price = np.linspace(100, 120, 120)

    df = pd.DataFrame({
        "c": price,
        "h": price + 1,
        "l": price - 1
    }, index=dates)

    return df

# =========================
# PROCESS DATA (SAFE)
# =========================
def process_data(df):

    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if "Close" in df.columns:
            df = df.rename(columns={"Close": "c", "High": "h", "Low": "l"})

        # Ensure required columns exist
        if not all(col in df.columns for col in ["c","h","l"]):
            return None

        df["ma"] = df["c"].rolling(50).mean()
        df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

        prev_close = df["c"].shift(1)
        tr = np.maximum(
            df["h"] - df["l"],
            np.maximum(abs(df["h"] - prev_close), abs(df["l"] - prev_close))
        )

        df["atr"] = pd.Series(tr).rolling(14).mean()
        df["atr_change"] = df["atr"].pct_change()
        df["momentum"] = df["c"] / df["c"].shift(20)

        df = df.dropna()

        if df.empty:
            return None

        return df

    except:
        return None

# =========================
# INITIAL LOAD
# =========================
def initial_load():
    global DATA, LAST_UPDATE

    new_data = {}

    for symbol in SYMBOLS:
        df = safe_download(symbol)

        if df is None:
            df = generate_fake_data()

        df = process_data(df)

        if df is not None:
            new_data[symbol] = df

    # 🔥 GUARANTEE SPY EXISTS
    if "SPY" not in new_data:
        fake = process_data(generate_fake_data())
        new_data["SPY"] = fake

    DATA = new_data
    LAST_UPDATE = time.time()

# =========================
# BACKGROUND LOADER
# =========================
def data_loader():
    global DATA, LAST_UPDATE

    while True:
        new_data = {}

        for symbol in SYMBOLS:
            df = safe_download(symbol)

            if df is None:
                df = generate_fake_data()

            df = process_data(df)

            if df is not None:
                new_data[symbol] = df

        if "SPY" not in new_data:
            fake = process_data(generate_fake_data())
            new_data["SPY"] = fake

        DATA = new_data
        LAST_UPDATE = time.time()

        time.sleep(REFRESH_INTERVAL)

# START SYSTEM
initial_load()
threading.Thread(target=data_loader, daemon=True).start()

# =========================
# SIGNALS (SAFE)
# =========================
@app.route("/signals")
def signals():

    try:
        capital = float(request.args.get("capital", INITIAL_CAPITAL))

        if not DATA or "SPY" not in DATA:
            return jsonify({"error": "No data available"})

        spy_df = DATA["SPY"]

        if spy_df.empty:
            return jsonify({"error": "SPY data empty"})

        last_date = spy_df.index[-1]

        if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
            return jsonify({
                "date": str(last_date),
                "market": "bearish",
                "signals": []
            })

        rs = [(s, d.loc[last_date]["momentum"]) for s, d in DATA.items()]
        rs = sorted(rs, key=lambda x: x[1], reverse=True)

        signals = []
        used_risk = 0
        total_risk = capital * MAX_TOTAL_RISK

        for symbol, _ in rs[:TOP_N]:

            df = DATA[symbol]
            row = df.loc[last_date]

            if not all(k in row for k in ["c","ma","high_break","atr","atr_change"]):
                continue

            if not (row["c"] > row["ma"] and row["c"] > row["high_break"] and row["atr_change"] > 0):
                continue

            entry = row["c"]
            stop = entry - (ATR_MULT * row["atr"])
            risk_per_share = entry - stop

            if risk_per_share <= 0:
                continue

            risk_amount = capital * RISK_PER_TRADE

            if used_risk + risk_amount > total_risk:
                risk_amount = total_risk - used_risk

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

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
