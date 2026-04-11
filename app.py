from flask import Flask, request
import pandas as pd
import requests
import os
import sqlite3
from datetime import datetime
from alpaca_trade_api.rest import REST

app = Flask(__name__)

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
MAX_POSITIONS = 3

# =========================
# ENV
# =========================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL")

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED","false") == "true"

api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL)

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
# DATA (REAL)
# =========================
def fetch_data(symbol):
    url = f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
    r = requests.get(url, timeout=10)

    df = pd.read_csv(pd.io.common.StringIO(r.text))
    df.columns = ["date","open","high","low","close","volume"]

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    df["ma"] = df["close"].rolling(50).mean()
    df["momentum"] = df["close"] / df["close"].shift(20)

    return df.dropna()

# =========================
# LOAD ALL DATA
# =========================
def load_data():
    data = {}

    for s in SYMBOLS:
        try:
            df = fetch_data(s)
            if not df.empty:
                data[s] = df
        except:
            pass

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
# AUTO TRADE
# =========================
def execute_trades(signals):

    executed = []

    if not AUTO_TRADING_ENABLED:
        return {"error":"disabled"}

    positions = api.list_positions()
    held = [p.symbol for p in positions]

    for sig in signals:

        if sig["symbol"] in held:
            continue

        if len(held) >= MAX_POSITIONS:
            break

        try:
            api.submit_order(
                symbol=sig["symbol"],
                qty=1,
                side="buy",
                type="market",
                time_in_force="gtc"
            )

            c.execute(
                "INSERT INTO trades VALUES (NULL,?,?,?, ?,?)",
                (sig["symbol"],"BUY",sig["price"],1,datetime.now())
            )
            conn.commit()

            executed.append(sig)

        except Exception as e:
            executed.append({"symbol":sig["symbol"],"error":str(e)})

    return {"executed":executed}

# =========================
# PORTFOLIO
# =========================
@app.route("/portfolio")
def portfolio():

    try:
        positions = api.list_positions()
        result = []

        for p in positions:
            result.append({
                "symbol": p.symbol,
                "qty": p.qty,
                "price": float(p.current_price),
                "pnl": float(p.unrealized_pl)
            })

        return {"positions":result}

    except Exception as e:
        return {"error":str(e)}

# =========================
# TRADE HISTORY
# =========================
@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

# =========================
# SIGNALS
# =========================
@app.route("/signals")
def signals():

    data = load_data()

    if "SPY" not in data:
        return {"error":"data failed"}

    market, sigs = get_signals(data)

    return {
        "market": market,
        "signals": sigs
    }

# =========================
# AUTO TRADE ENDPOINT
# =========================
@app.route("/auto_trade")
def auto_trade():

    data = load_data()
    market, sigs = get_signals(data)

    if market != "bullish":
        return {"note":"bearish market"}

    return execute_trades(sigs)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
