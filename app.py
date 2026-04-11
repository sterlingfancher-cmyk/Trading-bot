from flask import Flask
import pandas as pd
import numpy as np
import os

app = Flask(__name__)

SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]

DATA = {}
DATA_READY = False

# =========================
# LOCAL DATA GENERATOR (NO INTERNET NEEDED)
# =========================
def generate_data():
    global DATA, DATA_READY

    dates = pd.date_range(end=pd.Timestamp.today(), periods=200)

    new_data = {}

    for symbol in SYMBOLS:
        price = np.linspace(100, 200, 200) + np.random.normal(0, 2, 200)

        df = pd.DataFrame({
            "c": price,
            "h": price + 1,
            "l": price - 1
        }, index=dates)

        df["ma"] = df["c"].rolling(50).mean()
        df["momentum"] = df["c"] / df["c"].shift(20)
        df = df.dropna()

        new_data[symbol] = df

    DATA = new_data
    DATA_READY = True

generate_data()

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():
    return {
        "data_ready": DATA_READY,
        "symbols_loaded": list(DATA.keys())
    }

@app.route("/signals")
def signals():

    if not DATA_READY:
        return {"error":"no data"}

    spy = DATA["SPY"]
    last = spy.index[-1]

    if spy.loc[last]["c"] <= spy.loc[last]["ma"]:
        return {"market":"bearish","signals":[]}

    ranked = sorted(
        [(s, DATA[s].loc[last]["momentum"]) for s in DATA],
        key=lambda x: x[1],
        reverse=True
    )

    signals = []

    for s,_ in ranked:
        row = DATA[s].loc[last]

        if row["c"] > row["ma"] and row["momentum"] > 1.02:
            signals.append({
                "symbol": s,
                "price": round(float(row["c"]),2)
            })

    return {"market":"bullish","signals":signals}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
