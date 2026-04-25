import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
import traceback
import random

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True

# ================= CONFIG =================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
SIMULATION_MODE = True  # set False when you want real-only behavior

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

MAX_POSITIONS = 4
BASE_RISK = 0.02           # 2% equity risk budget per idea (used in caps)
TRAIL_STOP = 0.02          # 2% trailing stop
TAKE_PROFIT = 0.02         # take 50% at +2%
PYRAMID_STEP = 0.01        # add when +1% from last add
PYRAMID_ADD_PCT = 0.01     # add 1% equity per pyramid
MAX_PYRAMID_ADDS = 2
DRAWDOWN_LIMIT = -0.06     # pause if -6% from peak
MAX_ALLOC_PCT = 0.25       # max 25% of equity per position
MAX_ORDER_PCT_CASH = 0.50  # don't use more than 50% of cash per new order

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

# ================= STATE =================
portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},  # {sym: {shares, entry, last_price, peak, adds}}
    "history": [],
    "trades": [],
    "regime": "neutral",
    "last_update": None,
    "errors": []
}

# ================= SAFE SCALAR =================
def sf(x):
    try:
        return float(np.asarray(x).flatten()[-1])
    except:
        return 0.0

# ================= DATA =================
def synthetic_series(n=60, start=100.0):
    steps = np.random.normal(0, 0.002, size=n)
    prices = [start]
    for s in steps:
        prices.append(prices[-1] * (1 + s))
    return np.array(prices[1:], dtype=float)

def load_data(symbols):
    data = {}
    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)
            if df is None or df.empty or len(df) < 25:
                closes = synthetic_series()
                lows = closes * 0.999
            else:
                closes = df["Close"].dropna().values.astype(float)
                lows = df["Low"].dropna().values.astype(float)

            if SIMULATION_MODE:
                closes = closes * (1 + np.random.normal(0, 0.002, len(closes)))

            data[s] = {"close": np.array(closes), "low": np.array(lows)}
        except Exception as e:
            portfolio["errors"].append(f"[DATA] {s}: {e}")
            closes = synthetic_series()
            lows = closes * 0.999
            data[s] = {"close": closes, "low": lows}
    return data

# ================= REGIME =================
def detect_regime(data):
    try:
        spy = data.get("SPY")
        if not spy:
            return "neutral"
        p = spy["close"]
        if len(p) < 20:
            return "neutral"
        ma = np.mean(p[-20:])
        last = sf(p[-1])
        if last > ma * 1.002:
            return "bull"
        elif last < ma * 0.998:
            return "bear"
        else:
            return "neutral"
    except:
        return "neutral"

# ================= SIGNALS =================
def generate_signals(data):
    ranked = []
    for s, d in data.items():
        try:
            p = d["close"]
            if len(p) < 20:
                continue
            ret = (sf(p[-1]) / sf(p[-5])) - 1
            breakout = (sf(p[-1]) - np.max(p[-20:])) / (np.max(p[-20:]) + 1e-9)
            vol = np.std(np.diff(p[-20:]) / (p[-20:-1] + 1e-9)) + 1e-6
            score = float(ret + breakout + random.uniform(0, 0.01))
            ranked.append((s, score, vol))
        except Exception as e:
            portfolio["errors"].append(f"[SIGNAL] {s}: {e}")
    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= SIZING =================
def compute_order_notional(equity, cash):
    # capital-based sizing with caps
    alloc = equity * MAX_ALLOC_PCT
    cash_cap = cash * MAX_ORDER_PCT_CASH
    return max(0.0, min(alloc, cash_cap))

# ================= ENGINE =================
def run_engine():
    global portfolio
    try:
        data = load_data(UNIVERSE + ["SPY"])
        if not data:
            return {"error": "no data"}

        # ===== regime =====
        reg = detect_regime(data)
        portfolio["regime"] = reg

        # ===== equity update =====
        eq = portfolio["cash"]
        for s, pos in portfolio["positions"].items():
            if s in data:
                px = sf(data[s]["close"][-1])
                eq += pos["shares"] * px
        portfolio["equity"] = float(eq)
        portfolio["peak"] = max(portfolio["peak"], portfolio["equity"])

        # ===== drawdown guard =====
        dd = (portfolio["equity"] - portfolio["peak"]) / (portfolio["peak"] + 1e-9)
        if dd < DRAWDOWN_LIMIT:
            portfolio["history"].append(portfolio["equity"])
            portfolio["last_update"] = str(datetime.utcnow())
            return {"status": "PAUSED_DRAWDOWN", "equity": round(portfolio["equity"], 2)}

        # ===== trailing stops =====
        for s, pos in list(portfolio["positions"].items()):
            if s not in data:
                continue
            px = sf(data[s]["close"][-1])
            pos["peak"] = max(pos.get("peak", pos["entry"]), px)
            if (px - pos["peak"]) / (pos["peak"] + 1e-9) < -TRAIL_STOP:
                portfolio["cash"] += pos["shares"] * px
                portfolio["trades"].append({"sym": s, "type": "stop", "px": px})
                del portfolio["positions"][s]

        # ===== partial take-profit =====
        for s, pos in list(portfolio["positions"].items()):
            if s not in data:
                continue
            px = sf(data[s]["close"][-1])
            if (px - pos["entry"]) / (pos["entry"] + 1e-9) >= TAKE_PROFIT:
                sell = pos["shares"] * 0.5
                if sell > 0:
                    portfolio["cash"] += sell * px
                    pos["shares"] -= sell
                    pos["last_price"] = px
                    portfolio["trades"].append({"sym": s, "type": "take_profit", "px": px})

        # ===== pyramiding =====
        for s, pos in list(portfolio["positions"].items()):
            if s not in data:
                continue
            if pos.get("adds", 0) >= MAX_PYRAMID_ADDS:
                continue
            px = sf(data[s]["close"][-1])
            last = pos.get("last_price", pos["entry"])
            if (px - last) / (last + 1e-9) >= PYRAMID_STEP:
                add_notional = min(portfolio["equity"] * PYRAMID_ADD_PCT, portfolio["cash"])
                if add_notional > 0:
                    add_shares = add_notional / (px + 1e-9)
                    portfolio["cash"] -= add_notional
                    pos["shares"] += add_shares
                    pos["last_price"] = px
                    pos["adds"] = pos.get("adds", 0) + 1
                    portfolio["trades"].append({"sym": s, "type": "pyramid", "px": px})

        # ===== entries =====
        sig = generate_signals(data)
        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue
            if len(portfolio["positions"]) >= MAX_POSITIONS:
                break

            # regime filter: avoid longs in bear unless very strong score
            if reg == "bear" and score <= 0:
                continue

            px = sf(data[s]["close"][-1])
            notional = compute_order_notional(portfolio["equity"], portfolio["cash"])
            if notional <= 0:
                continue

            shares = notional / (px + 1e-9)
            if shares <= 0:
                continue

            portfolio["cash"] -= notional
            portfolio["positions"][s] = {
                "shares": float(shares),
                "entry": float(px),
                "last_price": float(px),
                "peak": float(px),
                "adds": 0
            }
            portfolio["trades"].append({"sym": s, "type": "entry", "px": px})

        # ===== finalize =====
        portfolio["history"].append(float(portfolio["equity"]))
        portfolio["last_update"] = str(datetime.utcnow())

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "regime": portfolio["regime"],
            "signals_found": len(sig)
        }

    except Exception as e:
        err = f"[ENGINE] {e}\n{traceback.format_exc()}"
        portfolio["errors"].append(err)
        return {"error": "engine failure", "detail": str(e)}

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
<html>
<head>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {background:#0f172a;color:white;font-family:Arial}
.card {background:#1e293b;padding:15px;border-radius:10px;margin:10px}
</style>
</head>
<body>

<h2>📊 Stable System Dashboard</h2>

<div class="card"><canvas id="chart"></canvas></div>
<div class="card"><pre id="data"></pre></div>

<script>
let chart;

async function refresh(){
  const res = await fetch('/paper/status');
  const d = await res.json();
  document.getElementById('data').innerText = JSON.stringify(d,null,2);

  const eq = (d.history && d.history.length > 1) ? d.history : [10000,10000];
  const ctx = document.getElementById('chart');

  if (!chart){
    chart = new Chart(ctx,{
      type:'line',
      data:{
        labels:eq.map((_,i)=>i),
        datasets:[{label:'Equity', data:eq}]
      },
      options:{animation:false}
    });
  } else {
    chart.data.labels = eq.map((_,i)=>i);
    chart.data.datasets[0].data = eq;
    chart.update();
  }
}
refresh();
setInterval(refresh,3000);
</script>

</body>
</html>
""")

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "SYSTEM LIVE"}

@app.route("/health")
def health():
    return {"ok": True, "time": str(datetime.utcnow())}

@app.route("/paper/run")
def run():
    try:
        if request.args.get("key") != SECRET_KEY:
            return {"error": "unauthorized"}
        return jsonify(run_engine())
    except Exception as e:
        return {"error": "route failure", "detail": str(e)}

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/logs")
def logs():
    return jsonify(portfolio["errors"][-20:])

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
