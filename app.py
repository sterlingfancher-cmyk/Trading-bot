import os
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# =========================
# SETTINGS
# =========================
SYMBOLS = [
    "AAPL","MSFT","NVDA","AMD","META","GOOGL","AMZN","TSLA","AVGO","CRM",
    "PANW","SNOW","NOW","ZS","CRWD","MDB","NET","SHOP",
    "JPM","BAC","GS","MS","C","WFC",
    "CAT","DE","GE","BA","HON","UPS","FDX",
    "COST","WMT","HD","MCD","NKE","SBUX",
    "LLY","JNJ","PFE","MRK","ABBV","TMO",
    "XOM","CVX","SLB",
    "SPY","QQQ","IWM"
]

MAX_POSITION_RISK = 0.05
MAX_POSITION_SIZE = 0.4

MAX_DRAWDOWN = -0.10
MAX_DAILY_LOSS = -0.03
COOLDOWN_CYCLES = 2

# =========================
# STATE
# =========================
portfolio = {
    "cash": 10000,
    "equity": 10000,
    "positions": {},
    "history": [],
    "trades": [],
    "last_run": None,
    "strategy": None,
    "cooldown": 0,
    "last_equity": 10000,
    "last_signals": []
}

# =========================
# DATA
# =========================
def load_data():
    data = {}
    for s in SYMBOLS:
        try:
            df = yf.download(s, period="6mo", interval="1d", progress=False)
            if df.empty:
                continue
            prices = np.array(df["Close"])
            volumes = np.array(df["Volume"])

            if len(prices) < 60:
                continue
            if np.mean(volumes[-20:]) < 1_000_000:
                continue
            if prices[-1] < 10:
                continue

            data[s] = prices
        except:
            continue
    return data

def get_vol(prices, i):
    r = np.diff(prices[i-20:i]) / prices[i-20:i-1]
    return np.std(r) + 1e-6

# =========================
# REGIME
# =========================
def get_regime():
    try:
        df = yf.download("SPY", period="3mo", progress=False)
        p = np.array(df["Close"])
        ma20 = np.mean(p[-20:])
        ma50 = np.mean(p[-50:])
        strength = (ma20 - ma50) / ma50

        if strength > 0.02: return "bull_strong", 0.8
        if strength > 0: return "bull_weak", 0.6
        if strength > -0.02: return "neutral", 0.5
        return "bear", 0
    except:
        return "neutral", 0.5

# =========================
# STRATEGIES
# =========================
def momentum(data, idx):
    scores = []
    for s,p in data.items():
        ret = (p[idx]/p[idx-20])-1
        vol = get_vol(p, idx)
        scores.append((s, ret/vol))
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def mean_reversion(data, idx):
    scores = []
    for s,p in data.items():
        z = (p[idx]-np.mean(p[idx-20:idx]))/np.std(p[idx-20:idx])
        if z < -0.7:
            scores.append((s, abs(z)))
    return sorted(scores, key=lambda x:x[1], reverse=True)[:3]

def short_strategy(data, idx):
    scores = []
    for s,p in data.items():
        ret = (p[idx]/p[idx-20])-1
        scores.append((s, ret))
    return sorted(scores, key=lambda x:x[1])[:3]

# =========================
# SIGNAL ENGINE
# =========================
def generate_signals_with_data(data):
    if len(data) < 5:
        return [], "none"

    idx = min(len(p) for p in data.values()) - 1
    regime, w = get_regime()

    if regime == "bear":
        shorts = short_strategy(data, idx)
        total = sum(abs(x[1]) for x in shorts)
        return [{"symbol":s,"weight":abs(v)/total,"side":"short"} for s,v in shorts], "bear_short"

    mom = momentum(data, idx)
    mr = mean_reversion(data, idx)

    combined = {}
    for s,v in mom:
        combined[s] = combined.get(s,0)+v*w
    for s,v in mr:
        combined[s] = combined.get(s,0)+v*(1-w)

    top = sorted(combined.items(), key=lambda x:x[1], reverse=True)[:3
