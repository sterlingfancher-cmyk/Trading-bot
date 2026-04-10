from flask import Flask, request, jsonify
import requests, csv, os, json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib

app = Flask(__name__)

def compute_strategy(df):
    print("RUNNING COMPUTE STRATEGY") 
    
    df["ma_fast"] = df["c"].rolling(20).mean()
    df["ma_slow"] = df["c"].rolling(50).mean()
    df["returns"] = df["c"].pct_change()

    df["signal"] = 0.0

    # ENTRY
    strength = (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]

    print("Max return:", df["returns"].max())
    print("Max strength:", strength.max())
    
    df.loc[
    (
        (df["ma_fast"] > df["ma_slow"]) &  #trend
        (df["returns"] > 0.0003) &
        (strength > 0.0003) 
    ),   
        "signal"
    ] = strength

    print("Signal min/max:", df["signal"].min(), df["signal"].max())
    # APPLY SCALING HERE
    df["signal"] = (df["signal"] / 0.04).clip(0, 1)

    #EXIT
    df.loc[
    (   
        (df["returns"] < -0.0025) | #stop loss
        (df["returns"] > 0.005)
    ),
        "signal"
    ] = 0

    # Only drop rows where indicators are missing
    df = df.dropna(subset=["ma_fast", "ma_slow", "returns"])
    if df.empty:
        return df

    # Build position (carry forward)
    df["position"] = df["signal"].replace(0, None).ffill().fillna(0)

    # Strategy returns
    df["strategy_returns"] = df["returns"] * df["position"].shift(1)
    df["strategy_returns"] = df["strategy_returns"].clip(lower=-0.01, upper=0.02)
    df["strategy_returns"] = df["strategy_returns"].where(df["strategy_returns"].abs()>0.0002, 0)

    # Volatility filter
    df["volatility"] = df["returns"].rolling(10).std()
    (df["volatility"] < df["volatility"].rolling(50).mean())                                         

    # FINAL safety check (DO NOT REMOVE EVERYTHING)
    if len(df) < 5:
        return pd.DataFrame()  # triggers your error safely

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

    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start.date()}/{end.date()}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_API_KEY}"

    r = requests.get(url)
    data = r.json()

    if "results" not in data:
        return pd.DataFrame()

    df = pd.DataFrame(data["results"])

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
            return jsonify({"error": "RAW DATA EMPTY"})

        # TEMP DEBUG - REMOVE AFTER TEST
        debug = {
            "rows":len(raw),
            "columns": list(raw.columns),
            "sample": raw.head(3).to_dict()
        }
        print(debug)    # logs to Railway logs

        df = raw.copy()
        df = compute_strategy(df)
        
        if df.empty:
            return jsonify({"error": "Strategy returned no data"})

        trades = (df["signal"].diff().abs() > 0).sum()

        returns = df["strategy_returns"].dropna()

        avg_pnl = round(returns.mean() * 100, 4) if not returns.empty else 0
        balance = round(1000 * (returns + 1).cumprod().iloc[-1], 2) if not returns.empty else 1000

        # NEW METRICS
        sharpe = round((returns.mean() / returns.std()) * np.sqrt(252), 4) if returns.std() != 0 else 0

        cum_returns = (returns + 1).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        max_drawdown = round(drawdown.min() * 100, 2)

        win_rate = round((returns > 0).mean() * 100, 2)

        return jsonify({
            "symbol": symbol,
            "trades": int(trades),
            "avg_pnl": avg_pnl,
            "balance": balance,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
