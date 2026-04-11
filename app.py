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
# ALPACA INIT (SAFE + TESTED)
# =========================
api = None

ALPACA_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

if ALPACA_KEY and ALPACA_SECRET:
    try:
        from alpaca_trade_api.rest import REST

        api = REST(
            ALPACA_KEY.strip(),
            ALPACA_SECRET.strip(),
            ALPACA_URL.strip(),
            api_version='v2'
        )

        # Test connection on startup
        account = api.get_account()
        print("✅ Alpaca connected:", account.status)

    except Exception as e:
        print("❌ Alpaca failed:", str(e))
        api = None
else:
    print("⚠️ Alpaca keys missing")

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
# DATA (ALWAYS WORKS)
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
# AUTO TRADE
# =========================
def execute_trades(signals):

    if not AUTO_TRADING_ENABLED:
        return {"status":"disabled"}

    if api is None:
        return {"error":"alpaca not connected"}

    try:
        positions = api.list_positions()
        held = [p.symbol for p in positions]
    except Exception as e:
        return {"error":str(e)}

    executed = []

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
# ROUTES
# =========================

@app.route("/")
def home():
    return {"status":"running"}

@app.route("/signals")
def signals():
    data = load_data()
    market, sigs = get_signals(data)

    return {
        "market": market,
        "signals": sigs
    }

@app.route("/auto_trade")
def auto_trade():
    data = load_data()
    market, sigs = get_signals(data)

    if market != "bullish":
        return {"note":"bearish"}

    return execute_trades(sigs)

@app.route("/portfolio")
def portfolio():

    if api is None:
        return {"error":"alpaca not connected"}

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

@app.route("/history")
def history():
    df = pd.read_sql("SELECT * FROM trades", conn)
    return df.to_dict(orient="records")

@app.route("/alpaca_test")
def alpaca_test():

    if api is None:
        return {"error":"alpaca not initialized"}

    try:
        account = api.get_account()
        return {
            "status": account.status,
            "buying_power": account.buying_power
        }
    except Exception as e:
        return {"error":str(e)}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
