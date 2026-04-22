import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META",
    "AMZN","GOOGL","TSLA","AVGO","CRM"
]

# =========================
# GLOBAL STATE
# =========================
portfolio = {
    "cash": 10000,
    "equity": 10000,
    "positions": {},
    "history": [],
    "trades": []
}

# =========================
# LOAD DATA
# =========================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="1y", interval="1d", progress=False)
            if df is None or df.empty:
                continue

            prices = np.array(df["Close"]).reshape(-1)
            prices = prices[np.isfinite(prices)]

            if len(prices) > 100:
                data[s] = prices.astype(float)
        except:
            continue

    return data

# =========================
# VOL
# =========================
def get_vol(prices, i):
    returns = np.diff(prices[i-20:i]) / prices[i-20:i-1]
    return np.std(returns) + 1e-6

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals():
    data = load_data()
    idx = min(len(p) for p in data.values()) - 1

    scores = []

    for s, prices in data.items():
        if idx < 20:
            continue

        window = prices[idx-20:idx]
        mean = np.mean(window)
        std = np.std(window)

        if std < 1e-6:
            continue

        z = (prices[idx] - mean) / std

        if z < -0.7:
            vol = get_vol(prices, idx)
            strength = abs(z) / vol
            scores.append((s, z, strength))

    if len(scores) < 2:
        return []

    scores.sort(key=lambda x: x[1])
    bottom = scores[:3]

    strengths = [(s, strength) for s, _, strength in bottom]
    total = sum(x[1] for x in strengths)
    n = len(strengths)

    signals = []
    for s, strength in strengths:
        equal_w = 1 / n
        strength_w = strength / total
        weight = 0.5 * equal_w + 0.5 * strength_w

        signals.append({
            "symbol": s,
            "weight": round(weight, 3)
        })

    return signals

# =========================
# PAPER TRADING
# =========================
def run_paper():
    global portfolio

    data = load_data()
    signals = generate_signals()
    idx = min(len(p) for p in data.values()) - 1

    # close positions
    for s, pos in portfolio["positions"].items():
        price = data[s][idx]
        pnl = (price - pos["entry_price"]) * pos["shares"]

        portfolio["trades"].append({
            "symbol": s,
            "entry": pos["entry_price"],
            "exit": price,
            "pnl": round(pnl, 2)
        })

    if not signals:
        portfolio["history"].append(portfolio["equity"])
        return {"message": "no trades"}

    capital = portfolio["equity"]
    new_positions = {}

    for sig in signals:
        s = sig["symbol"]
        weight = sig["weight"]
        price = data[s][idx]

        allocation = capital * weight
        shares = allocation / price

        new_positions[s] = {
            "shares": shares,
            "entry_price": price
        }

    portfolio["positions"] = new_positions

    total = 0
    for s, pos in new_positions.items():
        price = data[s][idx]
        total += pos["shares"] * price

    portfolio["equity"] = total
    portfolio["history"].append(total)

    return {
        "equity": round(total, 2),
        "positions": list(new_positions.keys())
    }

# =========================
# METRICS
# =========================
def get_metrics():
    trades = portfolio["trades"]

    if not trades:
        return {"message": "no trades yet"}

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]

    equity = portfolio["history"]

    peak = equity[0] if equity else 10000
    dd = 0

    for e in equity:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins)/len(trades)*100, 2),
        "total_pnl": round(sum(pnls), 2),
        "max_drawdown_pct": round(dd * 100, 2)
    }

# =========================
# BACKTEST (FIXED)
# =========================
def simulate_segment(data, start, end):
    capital = 10000
    equity_curve = []
    positions = {}

    holding_period = 3
    rebalance_counter = 0
    cost = 0.001

    for i in range(start, end):

        rebalance_counter += 1

        if rebalance_counter >= holding_period:

            scores = []

            for s, prices in data.items():
                if i < 20:
                    continue

                window = prices[i-20:i]
                mean = np.mean(window)
                std = np.std(window)

                if std < 1e-6:
                    continue

                z = (prices[i] - mean) / std

                if z < -0.7:
                    vol = get_vol(prices, i)
                    strength = abs(z) / vol
                    scores.append((s, z, strength))

            if len(scores) >= 2:
                scores.sort(key=lambda x: x[1])
                bottom = scores[:3]

                strengths = [(s, strength) for s, _, strength in bottom]
                total = sum(x[1] for x in strengths)
                n = len(strengths)

                positions = {}

                for s, strength in strengths:
                    equal_w = 1 / n
                    strength_w = strength / total
                    weight = 0.5 * equal_w + 0.5 * strength_w

                    allocation = capital * weight
                    price = data[s][i]
                    shares = allocation / price

                    positions[s] = shares

                capital *= (1 - cost)
                rebalance_counter = 0

        # mark-to-market (CRITICAL)
        total_value = 0
        for s, shares in positions.items():
            price = data[s][i]
            total_value += shares * price

        if positions:
            capital = total_value

        equity_curve.append(capital)

    if len(equity_curve) < 5:
        return None

    ret = (equity_curve[-1] - 10000) / 10000

    peak = equity_curve[0]
    dd = 0

    for e in equity_curve:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    return {"return": ret, "drawdown": dd}

def walk_forward():
    data = load_data()

    length = min(len(p) for p in data.values())

    train = 60
    test = 20

    results = []
    i = 30

    while i + train + test < length:
        start = i + train
        end = start + test

        res = simulate_segment(data, start, end)
        if res:
            results.append(res)

        i += test

    returns = [r["return"] for r in results]
    dds = [r["drawdown"] for r in results]

    return {
        "segments": len(results),
        "avg_return_pct": round(np.mean(returns)*100, 2),
        "worst_drawdown_pct": round(min(dds)*100, 2),
        "consistency_pct": round(
            (sum(1 for r in returns if r > 0)/len(returns))*100, 2
        )
    }

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "FULL SYSTEM RESTORED"}

@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/signals")
def signals():
    return jsonify({"signals": generate_signals()})

@app.route("/paper/run")
def paper_run():
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/paper/history")
def history():
    return jsonify(portfolio["history"])

@app.route("/paper/metrics")
def metrics():
    return jsonify(get_metrics())

@app.route("/walkforward")
def wf():
    return jsonify(walk_forward())

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
