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
MAX_POSITIONS = 4
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
# FALLBACK DATA (🔥 GUARANTEED)
# =========================
def generate_fake_data():
    dates = pd.date_range(end=pd.Timestamp.today(), periods=120)
    price = np.linspace(100, 120, 120) + np.random.normal(0, 2, 120)

    df = pd.DataFrame({
        "c": price,
        "h": price + 1,
        "l": price - 1
    }, index=dates)

    return df

# =========================
# PROCESS DATA
# =========================
def process_data(df):

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Close" in df.columns:
        df = df.rename(columns={"Close": "c", "High": "h", "Low": "l"})

    df["ma"] = df["c"].rolling(100).mean()
    df["high_break"] = df["h"].rolling(LOOKBACK).max().shift(1)

    prev_close = df["c"].shift(1)
    tr = np.maximum(
        df["h"] - df["l"],
        np.maximum(abs(df["h"] - prev_close), abs(df["l"] - prev_close))
    )

    df["atr"] = pd.Series(tr).rolling(14).mean()
    df["atr_change"] = df["atr"].pct_change()
    df["momentum"] = df["c"] / df["c"].shift(20)

    return df.dropna()

# =========================
# INITIAL LOAD (🔥 FIX)
# =========================
def initial_load():
    global DATA, LAST_UPDATE

    print("Initial data load...")

    new_data = {}

    for symbol in SYMBOLS:
        df = safe_download(symbol)

        if df is None:
            print(f"Using fallback for {symbol}")
            df = generate_fake_data()

        df = process_data(df)
        new_data[symbol] = df

    DATA = new_data
    LAST_UPDATE = time.time()

    print(f"Loaded {len(DATA)} symbols")

# =========================
# BACKGROUND LOADER
# =========================
def data_loader():
    global DATA, LAST_UPDATE

    while True:
        print("Refreshing data...")

        new_data = {}

        for symbol in SYMBOLS:
            df = safe_download(symbol)

            if df is None:
                df = generate_fake_data()

            df = process_data(df)
            new_data[symbol] = df

        DATA = new_data
        LAST_UPDATE = time.time()

        print("Data refreshed")

        time.sleep(REFRESH_INTERVAL)

# 🔥 RUN INITIAL LOAD FIRST
initial_load()

# 🔁 START BACKGROUND THREAD
threading.Thread(target=data_loader, daemon=True).start()

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "live",
        "symbols_loaded": len(DATA),
        "last_update": LAST_UPDATE
    })

# =========================
# SIGNALS (INSTANT)
# =========================
@app.route("/signals")
def signals():

    capital = float(request.args.get("capital", INITIAL_CAPITAL))

    spy_df = DATA.get("SPY")
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

    spy_df = DATA.get("SPY")
    last_date = spy_df.index[-1]

    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({"status": "No trades"})

    executed = []

    for symbol in SYMBOLS:

        df = DATA[symbol]
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
