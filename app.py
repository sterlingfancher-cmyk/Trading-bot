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

        except Exception:
            continue

    return data

# =========================
# ANALYZER
# =========================
def analyze_signals():
    data = load_data()
    results = []

    for s, prices in data.items():

        momentum_scores = []
        mean_rev_scores = []
        vol_scores = []
        future_returns = []

        for i in range(30, len(prices) - 5):

            # SIGNALS
            momentum = (prices[i] - prices[i-20]) / prices[i-20]
            mean_rev = (prices[i] - np.mean(prices[i-10:i])) / np.mean(prices[i-10:i])
            returns = np.diff(prices[i-20:i]) / prices[i-20:i-1]
            vol = np.std(returns)

            # FUTURE RETURN (5-day forward)
            future = (prices[i+5] - prices[i]) / prices[i]

            momentum_scores.append(momentum)
            mean_rev_scores.append(mean_rev)
            vol_scores.append(vol)
            future_returns.append(future)

        if len(future_returns) > 20:
            try:
                corr_momentum = np.corrcoef(momentum_scores, future_returns)[0,1]
                corr_meanrev = np.corrcoef(mean_rev_scores, future_returns)[0,1]
                corr_vol = np.corrcoef(vol_scores, future_returns)[0,1]

                results.append({
                    "symbol": s,
                    "momentum_corr": round(float(corr_momentum), 3),
                    "mean_reversion_corr": round(float(corr_meanrev), 3),
                    "volatility_corr": round(float(corr_vol), 3)
                })
            except Exception:
                continue

    return results

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return {"status": "live analyzer"}

@app.route("/health")
def health():
    return {"status": "running"}

@app.route("/analyze")
def analyze():
    try:
        return jsonify(analyze_signals())
    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
