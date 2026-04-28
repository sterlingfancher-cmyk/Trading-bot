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
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass

    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": []
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

portfolio = load_state()

# ================= DATA =================
def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]

def load_data(symbols):
    data5, data15 = {}, {}

    for s in symbols:
        try:
            df5 = yf.download(s, period="2d", interval="5m", progress=False)
            df15 = yf.download(s, period="5d", interval="15m", progress=False)

            if df5.empty or df15.empty:
                continue

            c5 = clean(df5["Close"].values)
            c15 = clean(df15["Close"].values)

            if len(c5) > 20 and len(c15) > 20:
                data5[s] = c5
                data15[s] = c15
        except:
            continue

    return data5, data15

# ================= SIGNAL =================
def generate_signals(data5, data15):
    ranked = []

    for s in data5:
        try:
            p5 = data5[s]
            p15 = data15[s]
            px = p5[-1]

            # Trend filters
            if px < np.mean(p5[-20:]):
                continue
            if p15[-1] < np.mean(p15[-20:]):
                continue

            # Relaxed breakout
            range_high = max(p5[-10:])
            if px < range_high * 0.995:
                continue

            # Momentum
            r3 = (px / p5[-3]) - 1
            if r3 <= 0:
                continue

            r12 = (px / p5[-12]) - 1
            score = r3*0.6 + r12*0.4

            if score < 0.0025:
                continue

            ranked.append((s, float(score)))

        except:
            continue

    return sorted(ranked, key=lambda x: x[1], reverse=True)[:5]

# ================= ENGINE =================
def run_engine():
    data5, data15 = load_data(UNIVERSE)

    if not data5:
        return {"error": "no data"}

    # ===== MARK TO MARKET =====
    equity = portfolio["cash"]

    for s, pos in portfolio["positions"].items():
        if s not in data5:
            continue

        px = float(data5[s][-1])
        pos["last_price"] = px
        pos["peak"] = max(pos["peak"], px)

        equity += pos["shares"] * px

    portfolio["equity"] = float(equity)
    portfolio["peak"] = max(portfolio["peak"], portfolio["equity"])

    # ===== SCALE INTO WINNERS (REFINED) =====
    for s, pos in portfolio["positions"].items():
        pnl = (pos["last_price"] - pos["entry"]) / pos["entry"]

        # 🔥 only add if holding strength (not extended)
        pullback_ok = pos["last_price"] >= pos["peak"] * 0.985

        if pnl > 0.0035 and pullback_ok and pos.get("adds", 0) < 3:
            alloc = portfolio["cash"] * 0.3  # 🔥 reduced aggression

            if alloc > 0:
                shares = alloc / pos["last_price"]
                portfolio["cash"] -= alloc
                pos["shares"] += shares
                pos["adds"] = pos.get("adds", 0) + 1

    # ===== EXITS (TIGHTER TRAIL) =====
    for s in list(portfolio["positions"].keys()):
        pos = portfolio["positions"][s]
        px = pos["last_price"]

        pnl = (px - pos["entry"]) / pos["entry"]

        if pnl < -0.02 or px < pos["peak"] * 0.97 or pnl > 0.20:
            portfolio["cash"] += px * pos["shares"]
            del portfolio["positions"][s]

    # ===== ENTRIES =====
    signals = generate_signals(data5, data15)
    used_sectors = set(get_sector(s) for s in portfolio["positions"])

    for s, score in signals:
        if s in portfolio["positions"]:
            continue
        if get_sector(s) in used_sectors:
            continue
        if len(portfolio["positions"]) >= 4:
            break

        px = float(data5[s][-1])

        if score > 0.02:
            alloc_pct = 0.55
        elif score > 0.01:
            alloc_pct = 0.45
        else:
            alloc_pct = 0.35

        alloc = portfolio["cash"] * alloc_pct
        alloc = min(alloc, portfolio["cash"])

        if alloc <= 0:
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
        used_sectors.add(get_sector(s))

    portfolio["history"].append(portfolio["equity"])
    save_state(portfolio)

    return {
        "equity": round(portfolio["equity"],2),
        "cash": round(portfolio["cash"],2),
        "positions": list(portfolio["positions"].keys()),
        "signals_found": len(signals)
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
    <h2>📊 Refined Compounding System</h2>

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
    app.run(host="0.0.0.0", port=port)
