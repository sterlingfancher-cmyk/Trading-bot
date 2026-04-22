import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# =========================
# SECURITY
# =========================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

# =========================
# SETTINGS
# =========================
SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA","AVGO",
    "JPM","BAC","GS","MS",
    "CAT","DE","GE","HON",
    "COST","WMT","HD","MCD",
    "LLY","JNJ","MRK",
    "XOM","CVX",
    "SPY","QQQ","IWM"
]

MAX_POSITION_RISK = 0.05

# =========================
# SAFE FLOAT CONVERSION (CRITICAL FIX)
# =========================
def safe_float(x):
    try:
        return float(np.asarray(x).item())
    except:
        try:
            return float(x)
        except:
            return 0.0

# =========================
# STATE
# =========================
portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None,
    "last_signals": [],
    "step": 60
}

# =========================
# DATA
# =========================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False)

            if df is None or df.empty:
                continue

            prices = np.array(df["Close"], dtype=float)

            if len(prices) < 60:
                continue

            data[s] = prices
        except:
            continue
    return data

# =========================
# STRATEGIES (SIMPLIFIED + RELIABLE)
# =========================
def generate_signals(data, idx):
    scores = []

    for s,p in data.items():
        try:
            ret = safe_float(p[idx] / p[idx-20] - 1)
            scores.append((s, ret))
        except:
            continue

    scores = sorted(scores, key=lambda x: x[1], reverse=True)

    # 🔥 ALWAYS TRADE
    top = scores[:3] if scores else list(data.keys())[:3]

    if not top:
        return [], "no_data"

    return [
        {"symbol": s, "weight": 1/len(top)}
        for s,_ in top
    ], "active"

# =========================
# EXECUTION (FULLY SAFE)
# =========================
def run_paper():
    global portfolio

    try:
        data = load_data()
        if not data:
            return {"error": "no data"}

        lengths = [len(p) for p in data.values()]
        max_len = min(lengths) - 1

        # TIME PROGRESSION
        if portfolio["step"] >= max_len:
            portfolio["step"] = 60

        idx = portfolio["step"]
        portfolio["step"] += 1

        signals, regime = generate_signals(data, idx)
        portfolio["last_signals"] = signals

        # CLOSE OLD POSITIONS
        for s,pos in portfolio["positions"].items():
            if s in data:
                price = safe_float(data[s][idx])
                pnl = safe_float((price - pos["entry_price"]) * pos["shares"])

                portfolio["trades"].append({
                    "symbol": s,
                    "entry": pos["entry_price"],
                    "exit": price,
                    "pnl": round(pnl, 2)
                })

        portfolio["cash"] = safe_float(portfolio["equity"])
        portfolio["positions"] = {}

        new_pos = {}

        for sig in signals:
            s = sig["symbol"]

            if s not in data:
                continue

            price = safe_float(data[s][idx])

            alloc = safe_float(portfolio["cash"] * sig["weight"])
            alloc = min(alloc, portfolio["equity"] * MAX_POSITION_RISK)

            shares = safe_float(alloc / price if price > 0 else 0)

            new_pos[s] = {
                "shares": shares,
                "entry_price": price
            }

        value = 0.0

        for s,pos in new_pos.items():
            price = safe_float(data[s][idx])
            value += safe_float(pos["shares"] * price)

        used = safe_float(sum(
            safe_float(pos["shares"] * pos["entry_price"])
            for pos in new_pos.values()
        ))

        portfolio["cash"] = safe_float(portfolio["cash"] - used)
        portfolio["positions"] = new_pos
        portfolio["equity"] = safe_float(portfolio["cash"] + value)

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())
        portfolio["strategy"] = regime

        return {
            "equity": round(portfolio["equity"], 2),
            "strategy": regime
        }

    except Exception as e:
        return {"error": str(e)}

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "LIVE SYSTEM"}

@app.route("/signals")
def signals():
    return jsonify({
        "strategy": portfolio.get("strategy", "init"),
        "signals": portfolio.get("last_signals", [])
    })

@app.route("/paper/run")
def run():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/paper/metrics")
def metrics():
    eq = portfolio["history"]

    if len(eq) < 5:
        return {"message": "not enough data"}

    returns = np.diff(eq) / eq[:-1]

    sharpe = safe_float(np.mean(returns) / (np.std(returns) + 1e-6) * np.sqrt(252))

    peak = eq[0]
    dd = 0

    for e in eq:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    pnls = [t["pnl"] for t in portfolio["trades"]]
    wins = [p for p in pnls if p > 0]

    return {
        "sharpe": round(sharpe, 2),
        "drawdown_pct": round(dd * 100, 2),
        "trades": len(pnls),
        "win_rate": round(len(wins)/len(pnls)*100, 2) if pnls else 0,
        "total_pnl": round(sum(pnls), 2)
    }

# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
