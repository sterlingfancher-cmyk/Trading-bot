import os
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
import traceback
import random

app = Flask(__name__)

SECRET_KEY = os.environ.get("RUN_KEY", "changeme")

UNIVERSE = [
    "NVDA","AMD","AVGO","TSM","MU","LRCX","ARM",
    "META","AMZN","GOOGL","MSFT","SNOW","PLTR","CRWD","PANW","NET",
    "TSLA","SHOP","COIN","ROKU",
    "RKLB","KTOS","LHX","NOC",
    "XOM","CVX",
    "IBIT","ETHA","GDLC"
]

portfolio = {
    "cash": 10000.0,
    "equity": 10000.0,
    "peak": 10000.0,
    "positions": {},
    "history": [],
    "trades": [],
    "regime": "neutral",
    "errors": []
}

# ================= SAFE ARRAY =================
def clean_series(arr):
    arr = np.asarray(arr)

    # Flatten ANY weird shapes
    if arr.ndim > 1:
        arr = arr[:, -1]

    arr = arr.astype(float)
    arr = arr[~np.isnan(arr)]

    return arr

# ================= DATA =================
def load_data(symbols):
    data = {}

    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)

            if df is None or df.empty:
                raise ValueError("Empty data")

            close = clean_series(df["Close"].values)

            if len(close) < 25:
                raise ValueError("Not enough data")

            data[s] = {"close": close}

        except Exception as e:
            portfolio["errors"].append(f"[DATA] {s}: {str(e)}")

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
        last = p[-1]

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

            p = clean_series(p)

            # Ensure 1D
            if p.ndim != 1:
                continue

            ret = (p[-1] / p[-5]) - 1
            breakout = (p[-1] - np.max(p[-20:])) / (np.max(p[-20:]) + 1e-9)

            diff = np.diff(p[-20:])
            base = p[-20:-1]

            if len(diff) != len(base):
                continue

            vol = np.std(diff / (base + 1e-9)) + 1e-6

            score = float(ret + breakout + random.uniform(0, 0.01))

            ranked.append((s, score, vol))

        except Exception as e:
            portfolio["errors"].append(f"[SIGNAL] {s}: {str(e)}")

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    try:
        data = load_data(UNIVERSE + ["SPY"])

        if not data:
            return {"error": "no data"}

        portfolio["regime"] = detect_regime(data)

        # ===== equity =====
        eq = portfolio["cash"]
        for s, pos in portfolio["positions"].items():
            if s in data:
                px = data[s]["close"][-1]
                eq += pos["shares"] * px

        portfolio["equity"] = eq
        portfolio["peak"] = max(portfolio["peak"], eq)

        # ===== signals =====
        sig = generate_signals(data)

        # ===== entries =====
        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= 4:
                break

            px = data[s]["close"][-1]

            allocation = portfolio["equity"] * 0.2

            if portfolio["cash"] < allocation:
                continue

            shares = allocation / px

            portfolio["cash"] -= allocation

            portfolio["positions"][s] = {
                "shares": shares,
                "entry": px
            }

            portfolio["trades"].append({
                "sym": s,
                "type": "entry",
                "px": px
            })

        portfolio["history"].append(portfolio["equity"])

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig)
        }

    except Exception as e:
        portfolio["errors"].append(traceback.format_exc())
        return {"error": "engine failure", "detail": str(e)}

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "APP LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/logs")
def logs():
    return jsonify(portfolio["errors"][-20:])

@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>📊 Stable Dashboard</h2>

    <canvas id="chart"></canvas>
    <pre id="data"></pre>

    <script>
    let chart;

    async function load(){
        const res = await fetch('/paper/status');
        const d = await res.json();

        document.getElementById('data').innerText = JSON.stringify(d,null,2);

        let hist = d.history.length > 1 ? d.history : [10000,10000];

        if(!chart){
            chart = new Chart(document.getElementById('chart'),{
                type:'line',
                data:{
                    labels: hist.map((_,i)=>i),
                    datasets:[{label:'Equity', data:hist}]
                }
            });
        } else {
            chart.data.labels = hist.map((_,i)=>i);
            chart.data.datasets[0].data = hist;
            chart.update();
        }
    }

    load();
    setInterval(load,3000);
    </script>
    </body>
    </html>
    """)

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
