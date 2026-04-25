import os, json, traceback
import numpy as np
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

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
_memory = None

def load_state():
    global _memory
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                _memory = json.load(f)
                return _memory
        except:
            pass

    if _memory:
        return _memory

    _memory = {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "errors": [],
        "regime": "neutral"
    }
    return _memory

def save_state(state):
    global _memory
    _memory = state
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except:
        pass

portfolio = load_state()

# ================= DATA =================
def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    arr = arr[~np.isnan(arr)]
    return arr

def load_data(symbols):
    out = {}
    for s in symbols:
        try:
            df = yf.download(s, period="1d", interval="1m", progress=False)
            if df is None or df.empty:
                continue
            c = clean(df["Close"].values)
            if len(c) < 30:
                continue
            out[s] = c
        except:
            continue
    return out

# ================= SIMULATION =================
def simulate(px):
    return float(px * (1 + np.random.normal(0, 0.0015)))

# ================= REGIME =================
def detect_regime(data):
    spy = data.get("SPY")
    if spy is None or len(spy) < 20:
        return "neutral"

    ma = np.mean(spy[-20:])
    px = spy[-1]

    if px > ma * 1.002:
        return "bull"
    elif px < ma * 0.998:
        return "bear"
    return "neutral"

# ================= SIGNAL ENGINE =================
def generate_signals(data, regime):
    ranked = []

    for s, p in data.items():
        try:
            if len(p) < 25:
                continue

            px = p[-1]
            ma20 = np.mean(p[-20:])
            r5 = (px / p[-5]) - 1
            r20 = (px / p[-20]) - 1
            high20 = np.max(p[-20:])
            breakout = (px - high20) / high20
            vol = np.std(np.diff(p[-20:]) / p[-20:-1])

            # ===== REGIME ADAPTIVE FILTER =====
            if regime == "bull":
                if px < ma20 or r5 <= 0 or r20 <= 0:
                    continue

            elif regime == "neutral":
                if r5 <= 0:
                    continue
                if breakout < -0.03:
                    continue

            elif regime == "bear":
                if r5 <= 0 or r20 <= 0:
                    continue
                if px < ma20:
                    continue

            # volatility filter
            if vol < 0.0015:
                continue

            score = r5 * 0.6 + r20 * 0.4
            ranked.append((s, float(score), float(vol)))

        except:
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)

# ================= ENGINE =================
def run_engine():
    try:
        data = load_data(UNIVERSE + ["SPY"])
        if not data:
            return {"error": "no data"}

        portfolio["regime"] = detect_regime(data)

        equity = portfolio["cash"]

        # ===== MARK TO MARKET =====
        for s, pos in portfolio["positions"].items():

            new_px = data[s][-1] if s in data else pos["last_price"]

            # stale detection → simulate
            if abs(new_px - pos["last_price"]) < 1e-8:
                px = simulate(pos["last_price"])
            else:
                px = new_px

            pos["last_price"] = px
            pos["peak"] = max(pos["peak"], px)

            equity += pos["shares"] * px

        portfolio["equity"] = equity
        portfolio["peak"] = max(portfolio["peak"], equity)

        # ===== KILL SWITCH =====
        dd = (equity - portfolio["peak"]) / portfolio["peak"]
        if dd < -0.10:
            portfolio["positions"] = {}
            portfolio["cash"] = equity
            portfolio["trades"].append({"type": "kill"})
            save_state(portfolio)
            return {"risk": "portfolio stopped"}

        # ===== EXITS =====
        for s in list(portfolio["positions"].keys()):
            pos = portfolio["positions"][s]
            px = pos["last_price"]
            entry = pos["entry"]

            pnl = (px - entry) / entry

            if pnl < -0.04 or px < pos["peak"] * 0.95 or pnl > 0.15:
                portfolio["cash"] += px * pos["shares"]
                del portfolio["positions"][s]

        # ===== SIGNALS =====
        sig = generate_signals(data, portfolio["regime"])

        # ===== POSITION LIMITS =====
        if portfolio["regime"] == "bull":
            max_positions = 4
        elif portfolio["regime"] == "neutral":
            max_positions = 2
        else:
            max_positions = 1

        # ===== ENTRIES =====
        for s, score, vol in sig[:max_positions]:

            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= max_positions:
                break

            px = data[s][-1]

            size = min(0.25, 0.06 / (vol + 1e-6))
            alloc = portfolio["equity"] * size

            if portfolio["cash"] < alloc:
                continue

            shares = alloc / px

            portfolio["cash"] -= alloc
            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares,
                "last_price": px,
                "peak": px
            }

            portfolio["trades"].append({
                "sym": s,
                "type": "entry",
                "px": px
            })

        portfolio["history"].append(portfolio["equity"])
        save_state(portfolio)

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig),
            "regime": portfolio["regime"]
        }

    except Exception as e:
        portfolio["errors"].append(traceback.format_exc())
        return {"error": "engine failure", "detail": str(e)}

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status": "SYSTEM LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error": "unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>📊 Adaptive Trading System</h2>

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
