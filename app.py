import os, json, traceback
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
STATE_FILE = "state.json"

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

# ================= STATE =================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "errors": [],
        "regime": "neutral"
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

portfolio = load_state()

# ================= DATA CLEAN =================
def clean(arr):
    arr = np.asarray(arr)
    if arr.ndim > 1:
        arr = arr[:, -1]
    arr = arr.astype(float)
    arr = arr[~np.isnan(arr)]
    return arr

# ================= DATA =================
def load_data(symbols):
    out = {}
    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)
            if df is None or df.empty:
                continue
            c = clean(df["Close"].values)
            if len(c) < 25:
                continue
            out[s] = c
        except Exception as e:
            portfolio["errors"].append(f"{s}:{str(e)}")
    return out

# ================= REGIME =================
def regime(data):
    spy = data.get("SPY")
    if spy is None or len(spy) < 20:
        return "neutral"

    ma = np.mean(spy[-20:])
    px = spy[-1]

    if px > ma * 1.002: return "bull"
    if px < ma * 0.998: return "bear"
    return "neutral"

# ================= SIGNAL =================
def signals(data):
    ranked = []
    for s, p in data.items():
        try:
            if len(p) < 20:
                continue

            r5 = (p[-1] / p[-5]) - 1
            r20 = (p[-1] / p[-20]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / np.max(p[-20:])
            vol = np.std(np.diff(p[-20:]) / p[-20:-1])

            score = r5*0.4 + r20*0.4 + breakout*0.2

            ranked.append((s, float(score), float(vol)))

        except Exception as e:
            portfolio["errors"].append(f"SIGNAL {s}:{str(e)}")

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    try:
        data = load_data(UNIVERSE + ["SPY"])
        if not data:
            return {"error":"no data"}

        portfolio["regime"] = regime(data)

        # ==== update equity ====
        eq = portfolio["cash"]
        for s, pos in portfolio["positions"].items():
            if s in data:
                px = data[s][-1]
                eq += pos["shares"] * px

        portfolio["equity"] = eq
        portfolio["peak"] = max(portfolio["peak"], eq)

        # ==== exits (risk control) ====
        for s in list(portfolio["positions"].keys()):
            if s not in data:
                continue

            px = data[s][-1]
            entry = portfolio["positions"][s]["entry"]

            pnl = (px - entry) / entry

            # stop loss
            if pnl < -0.05:
                portfolio["cash"] += px * portfolio["positions"][s]["shares"]
                del portfolio["positions"][s]

            # take profit
            elif pnl > 0.10:
                portfolio["cash"] += px * portfolio["positions"][s]["shares"]
                del portfolio["positions"][s]

        sig = signals(data)

        # ==== entries ====
        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= 5:
                break

            px = data[s][-1]
            alloc = portfolio["equity"] * 0.2

            if portfolio["cash"] < alloc:
                continue

            shares = alloc / px

            portfolio["cash"] -= alloc
            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares
            }

        portfolio["history"].append(portfolio["equity"])
        save_state(portfolio)

        return {
            "equity": round(portfolio["equity"],2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig)
        }

    except Exception as e:
        portfolio["errors"].append(traceback.format_exc())
        return {"error":"engine fail","detail":str(e)}

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status":"APP LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/dashboard")
def dash():
    return render_template_string("""
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>📊 Institutional Dashboard</h2>
    <canvas id="c"></canvas>
    <pre id="d"></pre>
    <script>
    let chart;
    async function load(){
        const r = await fetch('/paper/status');
        const j = await r.json();
        document.getElementById('d').innerText = JSON.stringify(j,null,2);

        let h = j.history.length>1?j.history:[10000,10000];

        if(!chart){
            chart = new Chart(document.getElementById('c'),{
                type:'line',
                data:{labels:h.map((_,i)=>i),
                datasets:[{label:'Equity',data:h}]}
            });
        } else {
            chart.data.labels = h.map((_,i)=>i);
            chart.data.datasets[0].data = h;
            chart.update();
        }
    }
    load();
    setInterval(load,3000);
    </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
