from flask import Flask, request
import pandas as pd
import numpy as np
import os
import sqlite3
from datetime import datetime
import subprocess
import sys

app = Flask(__name__)

# =========================
# FORCE INSTALL
# =========================
try:
    from alpaca.trading.client import TradingClient
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "alpaca-py"])
    from alpaca.trading.client import TradingClient

# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY","QQQ","NVDA","AMD","META"]
MAX_POSITIONS = 3

AUTO_TRADING_ENABLED = os.environ.get("AUTO_TRADING_ENABLED","false") == "true"

# =========================
# ALPACA
# =========================
client = TradingClient(
    api_key=os.environ.get("ALPACA_API_KEY"),
    secret_key=os.environ.get("ALPACA_SECRET_KEY"),
    paper=True
)

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
# DATA (SIMULATED FOR NOW)
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
def get_signals():
    data = load_data()

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
# EXECUTE TRADE (MANUAL)
# =========================
def execute_trade(symbol):

    try:
        positions = client.get_all_positions()
        held = [p.symbol for p in positions]

        if symbol in held:
            return {"error":"already holding"}

        if len(held) >= MAX_POSITIONS:
            return {"error":"max positions reached"}

        order = client.submit_order(
            symbol=symbol,
            qty=1,
            side="buy",
            type="market",
            time_in_force="gtc"
        )

        c.execute(
            "INSERT INTO trades VALUES (NULL,?,?,?,?,?)",
            (symbol,"BUY",0,1,datetime.now())
        )
        conn.commit()

        return {"status":"executed","symbol":symbol}

    except Exception as e:
        return {"error":str(e)}

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return {"status":"running"}

@app.route("/signals")
def signals():
    market, sigs = get_signals()
    return {"market":market,"signals":sigs}

@app.route("/trade")
def trade():
    symbol = request.args.get("symbol")

    if not symbol:
        return {"error":"symbol required"}

    return execute_trade(symbol.upper())

@app.route("/portfolio")
def portfolio():
    try:
        positions = client.get_all_positions()

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

@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
