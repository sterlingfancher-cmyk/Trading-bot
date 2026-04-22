import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

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

MAX_POSITION_RISK = 0.05     # per-position cap
MAX_POSITIONS = 3            # portfolio breadth
REBALANCE_TOL = 0.20         # tolerance before resizing (20%)

# =========================
# SAFE FLOAT
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
    "positions": {},   # {symbol: {shares, entry_price}}
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
# SIGNALS (always produce)
# =========================
def generate_signals(data, idx):
    scores = []
    for s, p in data.items():
        try:
            ret = safe_float(p[idx] / p[idx-20] - 1)
            scores.append((s, ret))
        except:
            continue

    scores = sorted(scores, key=lambda x: x[1], reverse=True)
    top = scores[:MAX_POSITIONS] if scores else list(data.keys())[:MAX_POSITIONS]

    if not top:
        return [], "no_data"

    w = 1.0 / len(top)
    return [{"symbol": s, "weight": w} for s, _ in top], "active"

# =========================
# PORTFOLIO HELPERS
# =========================
def mark_to_market(data, idx):
    total = safe_float(portfolio["cash"])
    for s, pos in portfolio["positions"].items():
        if s in data:
            price = safe_float(data[s][idx])
            total += safe_float(pos["shares"] * price)
    portfolio["equity"] = safe_float(total)

def target_value(weight):
    # per-position cap applied here
    return safe_float(min(weight, MAX_POSITION_RISK) * portfolio["equity"])

# =========================
# EXECUTION (STATEFUL)
# =========================
def run_paper():
    global portfolio
    try:
        data = load_data()
        if not data:
            return {"error": "no data"}

        lengths = [len(p) for p in data.values()]
        max_len = min(lengths) - 1

        # time progression
        if portfolio["step"] >= max_len:
            portfolio["step"] = 60

        idx = portfolio["step"]
        portfolio["step"] += 1

        # mark-to-market BEFORE trading
        mark_to_market(data, idx)

        signals, regime = generate_signals(data, idx)
        portfolio["last_signals"] = signals
        portfolio["strategy"] = regime

        target_syms = set(s["symbol"] for s in signals)
        current_syms = set(portfolio["positions"].keys())

        # =========================
        # 1) CLOSE positions not in signals
        # =========================
        for s in list(current_syms - target_syms):
            pos = portfolio["positions"].get(s)
            if s in data and pos:
                price = safe_float(data[s][idx])
                proceeds = safe_float(pos["shares"] * price)
                pnl = safe_float((price - pos["entry_price"]) * pos["shares"])
                portfolio["cash"] = safe_float(portfolio["cash"] + proceeds)
                portfolio["trades"].append({
                    "symbol": s,
                    "entry": pos["entry_price"],
                    "exit": price,
                    "pnl": round(pnl, 2)
                })
                del portfolio["positions"][s]

        # =========================
        # 2) REBALANCE existing positions
        # =========================
        for sig in signals:
            s = sig["symbol"]
            if s not in data:
                continue

            price = safe_float(data[s][idx])
            tgt_val = target_value(sig["weight"])

            if s in portfolio["positions"]:
                pos = portfolio["positions"][s]
                cur_val = safe_float(pos["shares"] * price)

                # only rebalance if deviation > tolerance
                if tgt_val > 0:
                    dev = abs(cur_val - tgt_val) / tgt_val
                else:
                    dev = 0

                if dev > REBALANCE_TOL:
                    # adjust shares
                    desired_shares = safe_float(tgt_val / price if price > 0 else 0)
                    delta_shares = safe_float(desired_shares - pos["shares"])

                    if abs(delta_shares) > 0:
                        delta_cash = safe_float(delta_shares * price)

                        # buy more
                        if delta_shares > 0 and portfolio["cash"] >= delta_cash:
                            portfolio["cash"] = safe_float(portfolio["cash"] - delta_cash)
                            pos["shares"] = safe_float(pos["shares"] + delta_shares)

                        # sell down
                        elif delta_shares < 0:
                            portfolio["cash"] = safe_float(portfolio["cash"] - delta_cash)  # delta_cash is negative
                            pos["shares"] = safe_float(pos["shares"] + delta_shares)

            else:
                # =========================
                # 3) OPEN new positions
                # =========================
                tgt_val = target_value(sig["weight"])
                if price <= 0:
                    continue

                shares = safe_float(tgt_val / price)
                cost = safe_float(shares * price)

                if shares > 0 and portfolio["cash"] >= cost:
                    portfolio["cash"] = safe_float(portfolio["cash"] - cost)
                    portfolio["positions"][s] = {
                        "shares": shares,
                        "entry_price": price
                    }

        # mark-to-market AFTER trading
        mark_to_market(data, idx)

        portfolio["history"].append(portfolio["equity"])
        portfolio["last_run"] = str(datetime.utcnow())

        return {
            "equity": round(portfolio["equity"], 2),
            "strategy": regime,
            "positions": list(portfolio["positions"].keys())
        }

    except Exception as e:
        return {"error": str(e)}

# =========================
# METRICS
# =========================
def get_metrics():
    eq = portfolio["history"]
    if len(eq) < 5:
        return {"message": "not enough data"}

    r = np.diff(eq) / eq[:-1]
    sharpe = safe_float(np.mean(r) / (np.std(r) + 1e-6) * np.sqrt(252))

    peak = eq[0]
    dd = 0.0
    for e in eq:
        peak = max(peak, e)
        dd = min(dd, (e - peak) / peak)

    pnls = [t["pnl"] for t in portfolio["trades"]]
    wins = [p for p in pnls if p > 0]

    return {
        "sharpe": round(sharpe, 2),
        "drawdown_pct": round(dd * 100, 2),
        "trades": len(pnls),
        "win_rate": round(len(wins) / len(pnls) * 100, 2) if pnls else 0,
        "total_pnl": round(sum(pnls), 2)
    }

# =========================
# DASHBOARD (lightweight)
# =========================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {background:#0f172a;color:white;font-family:Arial}
.grid {display:grid;grid-template-columns:1fr 1fr;gap:15px}
.card {background:#1e293b;padding:15px;border-radius:10px}
</style>
</head>
<body>

<h2>📊 Trading Dashboard</h2>

<div class="grid">
<div class="card"><canvas id="eq"></canvas></div>
<div class="card"><canvas id="dd"></canvas></div>
<div class="card"><pre id="signals"></pre></div>
<div class="card"><pre id="metrics"></pre></div>
</div>

<script>
let eqChart, ddChart;

function calcDD(eq){
 let peak=eq[0];
 return eq.map(e=>{
  peak=Math.max(peak,e);
  return (e-peak)/peak*100;
 });
}

async function load(){
 let p = await fetch('/paper/status').then(r=>r.json());
 let m = await fetch('/paper/metrics').then(r=>r.json());

 document.getElementById('signals').innerText =
  JSON.stringify(p.last_signals,null,2);

 document.getElementById('metrics').innerText =
  JSON.stringify(m,null,2);

 let eq = (p.history && p.history.length>1) ? p.history : [10000,10000];
 let dd = calcDD(eq);

 if(eqChart) eqChart.destroy();
 eqChart = new Chart(document.getElementById('eq'),{
  type:'line',
  data:{labels:eq.map((_,i)=>i),datasets:[{label:'Equity',data:eq}]}
 });

 if(ddChart) ddChart.destroy();
 ddChart = new Chart(document.getElementById('dd'),{
  type:'line',
  data:{labels:dd.map((_,i)=>i),datasets:[{label:'Drawdown %',data:dd}]}
 });
}

load();
setInterval(load,10000);
</script>

</body>
</html>
""")

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "LIVE SYSTEM"}

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
    return jsonify(get_metrics())

# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
