from flask import Flask, request
import pandas as pd
import numpy as np
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
MAX_POSITIONS = 3

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED","false") == "true"

# =========================
# ALPACA INIT (NO SILENT FAIL)
# =========================
api = None
alpaca_error = None

ALPACA_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

try:
    if ALPACA_KEY and ALPACA_SECRET:
        from alpaca_trade_api.rest import REST

        api = REST(
            ALPACA_KEY.strip(),
            ALPACA_SECRET.strip(),
            ALPACA_URL.strip(),
            api_version='v2'
        )

        # FORCE test (will throw real error)
        account = api.get_account()
        print("✅ Alpaca connected:", account.status)

    else:
        alpaca_error = "Missing keys"

except Exception as e:
    alpaca_error = str(e)
    api = None
    print("❌ Alpaca init error:", alpaca_error)

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("trades.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    side TEXT,
    price REAL,
    qty INTEGER,
    timestamp TEXT
)
""")
conn.commit()

# =========================
# DATA
# =========================
def load_data():
    dates = pd.date_range(end=pd.Timestamp.today(), periods=200)
    data = {}

    for symbol in SYMBOLS:
        base = {
            "SPY":500,"QQQ":450,"NVDA":900,"AMD":180,"META":500
        }.get(symbol,200)

        price = base + np.cumsum(np.random.normal(0,2,200))

        df = pd.DataFrame({"close": price}, index=dates)

        df["ma"] = df["close"].rolling(50).mean()
        df["momentum"] = df["close"] / df["close"].shift(20)
        df = df.dropna()

        data[symbol] = df

    return data

# =========================
# SIGNAL ENGINE
# =========================
def get_signals(data):
    spy = data["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["close"] <= spy.loc[last]["ma"]:
        return "bearish", []

    ranked = sorted(
        [(s, data[s].loc[last]["momentum"]) for s in data],
        key=lambda x: x[1],
        reverse=True
    )

    signals = []

    for s,_ in ranked[:5]:
        row = data[s].loc[last]

        if row["close"] > row["ma"] and row["momentum"] > 1.02:
            signals.append({
                "symbol": s,
                "price": round(float(row["close"]),2)
            })

    return "bullish", signals

# =========================
# ROUTES
# =========================

@app.route("/env_check")
def env_check():
    return {
        "key_exists": bool(ALPACA_KEY),
        "secret_exists": bool(ALPACA_SECRET),
        "base_url": ALPACA_URL
    }

@app.route("/alpaca_test")
def alpaca_test():

    if api is None:
        return {
            "error": "alpaca failed to initialize",
            "details": alpaca_error
        }

    try:
        account = api.get_account()
        return {
            "status": account.status,
            "buying_power": account.buying_power
        }
    except Exception as e:
        return {"error": str(e)}

@app.route("/signals")
def signals():
    data = load_data()
    market, sigs = get_signals(data)

    return {"market": market, "signals": sigs}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
