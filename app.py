from flask import Flask
import pandas as pd
import numpy as np
import os

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]

DATA = {}
DATA_READY = False

# =========================
# DATA GENERATOR (STABLE)
# =========================
def generate_data():
    global DATA, DATA_READY

    dates = pd.date_range(end=pd.Timestamp.today(), periods=200)
    new_data = {}

    for symbol in SYMBOLS:
        # Base price per asset (more realistic)
        base_price = {
            "SPY": 500,
            "QQQ": 450,
            "NVDA": 900,
            "AMD": 180,
            "META": 500
        }.get(symbol, 200)

        # Generate realistic price movement
        price = base_price + np.cumsum(np.random.normal(0, 2, 200))

        df = pd.DataFrame({
            "c": price,
            "h": price + 1,
            "l": price - 1
        }, index=dates)

        # Indicators
        df["ma"] = df["c"].rolling(50).mean()
        df["momentum"] = df["c"] / df["c"].shift(20)

        df = df.dropna()

        new_data[symbol] = df

    DATA = new_data
    DATA_READY = True

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return {
        "status": "running",
        "data_ready": DATA_READY
    }

@app.route("/refresh")
def refresh():
    generate_data()
    return {
        "status": "data refreshed",
        "symbols": list(DATA.keys())
    }

@app.route("/debug")
def debug():
    return {
        "data_ready": DATA_READY,
        "symbols_loaded": list(DATA.keys())
    }

@app.route("/signals")
def signals():

    if not DATA_READY:
        return {"error": "Run /refresh first"}

    spy = DATA["SPY"]
    last = spy.index[-1]

    # Market condition
    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return {"market": "bearish", "signals": []}

    # Rank by momentum
    ranked = sorted(
        [(s, DATA[s].loc[last]["momentum"]) for s in DATA],
        key=lambda x: x[1],
        reverse=True
    )

    signals = []

    for symbol, _ in ranked:
        row = DATA[symbol].loc[last]

        if row["c"] > row["ma"] and row["momentum"] > 1.02:
            signals.append({
                "symbol": symbol,
                "price": round(float(row["c"]), 2),
                "momentum": round(float(row["momentum"]), 3)
            })

    return {
        "market": "bullish",
        "signals": signals
    }

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
