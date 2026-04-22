import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA",
    "JPM","BAC","GS","MS",
    "CAT","DE","GE",
    "COST","WMT","HD",
    "LLY","JNJ",
    "XOM","CVX",
    "SPY","QQQ"
]

BASE_RISK = 0.02
MAX_HEAT = 0.25
MAX_POSITIONS = 4

def safe_float(x):
    try:
        return float(np.asarray(x).item())
    except:
        return float(x)

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "step": 60,
    "last_signals": [],
    "strategy": None
}

# ================= DATA =================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", progress=False)
            if df is None or df.empty:
                continue
            prices = np.array(df["Close"], dtype=float)
            if len(prices) > 60:
                data[s] = prices
        except:
            continue
    return data

# ================= REGIME =================
def get_regime(data):
    spy = data.get("SPY")
    if spy is None:
        return "neutral"
    return "bull" if np.mean(spy[-20:]) > np.mean(spy[-50:]) else "bear"

# ================= VOL =================
def get_vol(p, idx):
    r = np.diff(p[idx-20:idx]) / p[idx-20:idx-1]
    return safe_float(np.std(r)) + 1e-6

# ================= SIGNAL ENGINE (FIXED) =================
def generate_signals(data, idx, regime):
    scores = []

    for s,p in data.items():
        try:
            ret = (p[idx]/p[idx-20]) - 1
            vol = get_vol(p, idx)
            score = ret / vol

            if regime == "bear":
                score = -score

            scores.append((s, safe_float(score), vol))
        except:
            continue

    scores = sorted(scores, key=lambda x:x[1], reverse=True)

    # 🔥 ALWAYS TRADE FIX
    if not scores:
        fallback = list(data.keys())[:MAX_POSITIONS]
        return [(s, 0.01, 0.02) for s in fallback]

    return scores[:MAX_POSITIONS]

# ================= RISK =================
def drawdown_factor():
    dd = (portfolio["equity"] - portfolio["peak"]) / portfolio["peak"]
    return max(0.3, 1 + dd * 3)

# ================= EXECUTION =================
def run_paper():
    global portfolio

    try:
        data = load_data()
        if not data:
            return {"error":"no data"}

        lengths = [len(p) for p in data.values()]
        max_len = min(lengths) - 1

        if portfolio["step"] >= max_len:
            portfolio["step"] = 60

        idx = portfolio["step"]
        portfolio["step"] += 1

        regime = get_regime(data)
        signals = generate_signals(data, idx, regime)

        portfolio["last_signals"] = signals
        portfolio["strategy"] = regime

        # ===== MARK TO MARKET =====
        equity = portfolio["cash"]
        for s,pos in portfolio["positions"].items():
            if s in data:
                price = safe_float(data[s][idx])
                pnl = (price - pos["entry"]) * pos["shares"]
                if pos["side"] == "short":
                    pnl = (pos["entry"] - price) * pos["shares"]
                equity += pos["shares"] * price

        portfolio["equity"] = safe_float(equity)
        portfolio["peak"] = max(portfolio["peak"], portfolio["equity"])

        # ===== RISK UNIT =====
        risk_unit = portfolio["equity"] * BASE_RISK * drawdown_factor()

        # ===== CLOSE OLD =====
        current = set(portfolio["positions"].keys())
        target = set(s[0] for s in signals)

        for s in list(current - target):
            pos = portfolio["positions"][s]
            price = safe_float(data[s][idx])

            pnl = (price - pos["entry"]) * pos["shares"]
            if pos["side"] == "short":
                pnl = (pos["entry"] - price) * pos["shares"]

            portfolio["cash"] += pos["shares"] * price
            portfolio["trades"].append({"symbol": s, "pnl": round(pnl,2)})
            del portfolio["positions"][s]

        # ===== OPEN NEW =====
        total_alloc = 0

        for s,score,vol in signals:
            if s in portfolio["positions"]:
                continue

            price = safe_float(data[s][idx])
            position_size = min(risk_unit / vol, portfolio["equity"] * BASE_RISK)

            if total_alloc + position_size > portfolio["equity"] * MAX_HEAT:
                continue

            shares = position_size / price
            side = "long" if regime == "bull" else "short"

            if portfolio["cash"] >= position_size:
                portfolio["cash"] -= position_size
                total_alloc += position_size
                portfolio["positions"][s] = {
                    "shares": shares,
                    "entry": price,
                    "side": side
                }

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())

        return {"equity": round(portfolio["equity"],2), "regime": regime}

    except Exception as e:
        return {"error": str(e)}

# ================= METRICS =================
@app.route("/paper/metrics")
def metrics():
    eq = portfolio["history"]
    if len(eq) < 5:
        return {"message":"not enough data"}

    r = np.diff(eq)/eq[:-1]
    sharpe = np.mean(r)/(np.std(r)+1e-6)*np.sqrt(252)

    peak = eq[0]
    dd = 0
    for e in eq:
        peak = max(peak,e)
        dd = min(dd,(e-peak)/peak)

    pnls = [t["pnl"] for t in portfolio["trades"]]
    wins = [p for p in pnls if p > 0]

    return {
        "sharpe": round(sharpe,2),
        "drawdown_pct": round(dd*100,2),
        "trades": len(pnls),
        "win_rate": round(len(wins)/len(pnls)*100,2) if pnls else 0,
        "total_pnl": round(sum(pnls),2)
    }

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:#111;color:white;font-family:Arial">
    <h2>Institutional Dashboard</h2>
    <pre id="data"></pre>
    <script>
    async function load(){
        let s = await fetch('/paper/status').then(r=>r.json());
        let m = await fetch('/paper/metrics').then(r=>r.json());
        document.getElementById('data').innerText =
        "STATUS:\\n"+JSON.stringify(s,null,2)+"\\n\\nMETRICS:\\n"+JSON.stringify(m,null,2);
    }
    load();
    setInterval(load,5000);
    </script>
    </body>
    </html>
    """)

@app.route("/")
def home():
    return {"status":"CAPITAL ENGINE LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_paper())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
