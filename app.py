from flask import Flask
import pandas as pd
import requests
import os

app = Flask(__name__)

SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
DATA = {}
DATA_READY = False

# =========================
# REAL DATA FETCH (ROBUST)
# =========================
def fetch_data(symbol):
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            print(f"❌ HTTP error {symbol}")
            return None

        from io import StringIO
        df = pd.read_csv(StringIO(r.text))

        df.columns = ["date","open","high","low","close","volume"]

        df["c"] = df["close"]
        df["h"] = df["high"]
        df["l"] = df["low"]

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        df["ma"] = df["c"].rolling(50).mean()
        df["momentum"] = df["c"] / df["c"].shift(20)

        return df.dropna().tail(200)

    except Exception as e:
        print(f"❌ Fetch failed {symbol}: {e}")
        return None

# =========================
# LOAD DATA
# =========================
def load_data():
    global DATA, DATA_READY

    new_data = {}

    for symbol in SYMBOLS:
        df = fetch_data(symbol)

        if df is not None and not df.empty:
            new_data[symbol] = df
            print(f"✅ Loaded {symbol}")

    if new_data:
        DATA = new_data
        DATA_READY = True
        print("🚀 REAL DATA READY")
    else:
        print("🚨 FAILED TO LOAD DATA")

# =========================
# ROUTES
# =========================
@app.route("/debug")
def debug():

    if not DATA_READY:
        load_data()

    return {
        "data_ready": DATA_READY,
        "symbols_loaded": list(DATA.keys())
    }

@app.route("/signals")
def signals():

    if not DATA_READY:
        load_data()

    if not DATA_READY:
        return {"error":"data failed"}

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

    for s,_ in ranked[:5]:
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
