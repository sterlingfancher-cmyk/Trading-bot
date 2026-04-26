import os, json
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

SECTORS = {
    "tech": ["NVDA","AMD","AVGO","TSM","MU","LRCX","ARM","META","MSFT","GOOGL","AMZN"],
    "cyber": ["CRWD","PANW","NET"],
    "consumer": ["TSLA","SHOP","ROKU"],
    "energy": ["XOM","CVX"],
    "defense": ["LHX","NOC","KTOS"],
    "crypto": ["COIN","IBIT","ETHA","GDLC"]
}

def get_sector(sym):
    for k,v in SECTORS.items():
        if sym in v:
            return k
    return "other"

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
        "trades": []
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
    return arr[~np.isnan(arr)]

def load_data(symbols):
    out = {}
    for s in symbols:
        try:
            df = yf.download(s, period="2d", interval="5m", progress=False)
            if df is None or df.empty:
                continue
            c = clean(df["Close"].values)
            if len(c) > 20:
                out[s] = c
        except:
            continue
    return out

# ================= SIM =================
def simulate(px):
    return float(px * (1 + np.random.normal(0, 0.002)))

# ================= SIGNAL =================
def generate_signals(data):
    ranked = []

    for s, p in data.items():
        try:
            if len(p) < 20:
                continue

            px = p[-1]
            ma20 = np.mean(p[-20:])

            if px < ma20:
                continue

            r3 = (px / p[-3]) - 1
            r12 = (px / p[-12]) - 1

            if r3 <= 0:
                continue

            score = r3*0.6 + r12*0.4

            if score < 0.003:
                continue

            ranked.append((s, float(score)))

        except:
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)[:5]

# ================= ENGINE =================
def run_engine():
    data = load_data(UNIVERSE + ["SPY"])
    if not data:
        return {"error": "no data"}

    equity = portfolio["cash"]

    # MARK TO MARKET
    for s, pos in portfolio["positions"].items():
        new_px = data[s][-1] if s in data else pos["last_price"]

        if abs(new_px - pos["last_price"]) < 1e-8:
            px = simulate(pos["last_price"])
        else:
            px = new_px

        pos["last_price"] = px
        pos["peak"] = max(pos["peak"], px)
        equity += pos["shares"] * px

    portfolio["equity"] = equity
    portfolio["peak"] = max(portfolio["peak"], equity)

    # 🔥 SCALE INTO WINNERS (FIXED)
    for s, pos in portfolio["positions"].items():
        pnl = (pos["last_price"] - pos["entry"]) / pos["entry"]

        if pnl > 0.007 and pos.get("adds", 0) < 3:
            alloc = portfolio["equity"] * 0.15

            if portfolio["cash"] >= alloc:
                shares = alloc / pos["last_price"]
                portfolio["cash"] -= alloc
                pos["shares"] += shares
                pos["adds"] = pos.get("adds", 0) + 1

    # 🔥 EXIT LOGIC (TUNED)
    for s in list(portfolio["positions"].keys()):
        pos = portfolio["positions"][s]
        px = pos["last_price"]
        entry = pos["entry"]

        pnl = (px - entry) / entry

        if pnl < -0.02 or px < pos["peak"] * 0.96 or pnl > 0.18:
            portfolio["cash"] += px * pos["shares"]
            del portfolio["positions"][s]

    # ENTRIES
    sig = generate_signals(data)
    used_sectors = set(get_sector(s) for s in portfolio["positions"])

    for s, score in sig:
        if s in portfolio["positions"]:
            continue

        sector = get_sector(s)

        if sector in used_sectors:
            continue

        if len(portfolio["positions"]) >= 3:
            break

        px = data[s][-1]

        if score > 0.02:
            alloc_pct = 0.45
        elif score > 0.01:
            alloc_pct = 0.35
        else:
            alloc_pct = 0.25

        alloc = portfolio["equity"] * alloc_pct

        if portfolio["cash"] < alloc:
            continue

        shares = alloc / px

        portfolio["cash"] -= alloc
        portfolio["positions"][s] = {
            "entry": px,
            "shares": shares,
            "last_price": px,
            "peak": px,
            "adds": 0
        }

        portfolio["trades"].append({"sym": s, "type": "entry", "px": px})
        used_sectors.add(sector)

    portfolio["history"].append(portfolio["equity"])
    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"],2),
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(sig)
    }

# ================= ROUTES =================
@app.route("/")
def home():
    return {"status":"LIVE"}

@app.route("/paper/run")
def run():
    if request.args.get("key") != SECRET_KEY:
        return {"error":"unauthorized"}
    return jsonify(run_engine())

@app.route("/paper/status")
def status():
    return jsonify(portfolio)

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body style="background:#0f172a;color:white;">
    <h2>🚀 Compounding Trading System</h2>

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
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
