from flask import Flask, request, jsonify
import requests, csv, os, json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib

app = Flask(__name__)

def compute_strategy(df):

    # Indicators
    df["ma_fast"] = df["c"].rolling(10).mean()
    df["ma_slow"] = df["c"].rolling(30).mean()
    df["volatility"] = df["c"].pct_change().rolling(10).std()
    df["returns"] = df["c"].pct_change()

    # Initialize signal
    df["signal"] = 0

    # Entry: Trend + Pullback + Low volatility
    df.loc[
        (df["ma_fast"] > df["ma_slow"]) &           # uptrend
        (df["returns"] < 0) &                       # pullback
        (df["volatility"] < df["volatility"].rolling(50).mean()),
        "signal"
    ] = 1

    # Exit: trend breaks
    df.loc[
        (df["ma_fast"] < df["ma_slow"]),
        "signal"
    ] = 0

    df = df.dropna()

    # Strategy returns (position-based, not constant flipping)
    df["position"] = df["signal"].replace(0, None).ffill().fillna(0)
    df["strategy_returns"] = df["returns"] * df["position"].shift(1)

    return df

@app.route('/')
def home():
    return jsonify({"status": "running"})
    
TRADIER_API_KEY = "YOUR_TRADIER_API_KEY"
POLYGON_API_KEY = "L3SUCdmHWD0ctcfwFAsXBD5pFvHumpQi"
ACCOUNT_ID = "YOUR_ACCOUNT_ID"

BASE_URL = "https://api.tradier.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

MODEL_FILE = "model.pkl"
DATA_FILE = "training_data.csv"
TRADES_FILE = "trades.csv"
POSITIONS_FILE = "positions.json"

ACCOUNT_SIZE = 1000
BASE_RISK = 0.03
MAX_TRADES = 3

trade_count = 0

def now():
    return datetime.utcnow().isoformat()

def load_positions():
    if not os.path.exists(POSITIONS_FILE):
        return {}
    with open(POSITIONS_FILE, "r") as f:
        return json.load(f)

def save_positions(p):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(p, f)

def get_intraday(symbol):
    end = datetime.utcnow()
    start = end - timedelta(days=5)

    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start.date()}/{end.date()}"
    
    r = requests.get(url, params={"apiKey": POLYGON_API_KEY}).json()

    if "results" not in r:
        return pd.DataFrame()

    df = pd.DataFrame(r["results"])

    if df.empty or "c" not in df.columns:
        return pd.DataFrame()

    return df

def compute_indicators(df):
    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()

    delta = df["c"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    df["atr"] = (df["h"] - df["l"]).rolling(14).mean()
    df["vwap"] = (df["c"] * df["v"]).cumsum() / df["v"].cumsum()
    return df.dropna()

def signal(row):
    return (row["c"] > row["vwap"] and row["ema9"] > row["ema21"]) or (row["rsi"] > 70 or row["rsi"] < 30)

def predict(row):
    if not os.path.exists(MODEL_FILE):
        return 1.0
    model = joblib.load(MODEL_FILE)
    X = [[row["rsi"], row["atr"], row["v"], abs(row["ema9"]-row["ema21"])]]
    return model.predict_proba(X)[0][1]

def calc_size(price):
    risk = ACCOUNT_SIZE * BASE_RISK
    stop = price * 0.3
    return max(1, int(risk / stop))

def place_trade(symbol, qty, price):
    return requests.post(
        f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders",
        headers=HEADERS,
        data={
            "class":"option",
            "symbol":symbol,
            "side":"buy_to_open",
            "quantity":qty,
            "type":"limit",
            "price":price,
            "duration":"day",
            "advanced":"otooco",
            "stop":round(price*0.7,2),
            "limit":round(price*1.5,2)
        }
    ).json()

@app.route('/webhook', methods=['POST'])
def webhook():
    global trade_count

    if trade_count >= MAX_TRADES:
        return jsonify({"status":"limit"})

    data = request.json
    symbol = data.get("ticker")
    action = data.get("action")

    df = compute_indicators(get_intraday(symbol))
    row = df.iloc[-1]

    if not signal(row):
        return jsonify({"status":"no signal"})

    prob = predict(row)
    if prob < 0.6:
        return jsonify({"status":"ml filtered","prob":prob})

    trade_count += 1

    return jsonify({
        "status":"ready",
        "symbol": symbol,
        "prob": prob
    })

@app.route('/backtest/<symbol>')
def backtest(symbol):
    try:
        raw = get_intraday(symbol)

        if raw.empty:
            return jsonify({"error": "No valid data from Polygon"})

        df = raw.copy()

        df = compute_strategy(df)
        if df.empty:
            return jsonify({"error": "Strategy returned no data"})

        trades = (df["signal"].diff().abs() >0).sum()
        avg_pnl = round(df["strategy_returns"].mean() * 100, 4) if not df["strategy_returns"].empty else 0
        balance = round(1000 * (df["strategy_returns"] + 1).cumprod().iloc[-1], 2)

        return jsonify({
            "symbol": symbol,
            "trades": int(trades),
            "avg_pnl": avg_pnl,
            "balance": balance
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
