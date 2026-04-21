import os
import pytz
import numpy as np
import yfinance as yf
from datetime import datetime
from flask import Flask, jsonify

# =========================
# CONFIG
# =========================
SYMBOLS = ["AMD", "NVDA", "META", "AVGO", "INTC"]

RISK_PER_TRADE = 0.02
WEAK_EXIT = -0.015
PROFIT_LOCK = 0.07

BASE_URL = "https://paper-api.alpaca.markets"

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

# =========================
# SAFE ALPACA INIT
# =========================
api = None
try:
    from alpaca_trade_api import REST
    if API_KEY and API_SECRET:
        api = REST(API_KEY, API_SECRET, BASE_URL)
        print("✅ Alpaca connected")
    else:
        print("⚠️ Missing API keys")
except Exception as e:
    print("❌ Alpaca init failed:", e)

# =========================
# APP
# =========================
app = Flask(__name__)

# =========================
# MARKET CHECK
# =========================
def market_open():
    now = datetime.now(pytz.timezone("US/Eastern"))
    return now.weekday() < 5 and 9 <= now.hour < 16

# =========================
# MOMENTUM ENGINE (FIXED)
# =========================
def get_momentum_score(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if df is None or df.empty or len(df) < 30:
            print(f"Fallback scoring for {symbol}")
            return 0

        close = df["Close"].dropna()

        if len(close) < 25:
            return 0

        # Direct return calculations (no pct_change instability)
        r5 = (close.iloc[-1] / close.iloc[-6]) - 1
        r10 = (close.iloc[-1] / close.iloc[-11]) - 1
        r20 = (close.iloc[-1] / close.iloc[-21]) - 1

        returns = close.pct_change().dropna()

        if len(returns) < 20:
            return 0

        vol = returns.iloc[-20:].std()

        score = (r5 * 0.5) + (r10 * 0.3) + (r20 * 0.2) - (vol * 0.5)

        if score is None or np.isnan(score) or np.isinf(score):
            return 0

        return float(score)

    except Exception as e:
        print(f"Momentum error {symbol}: {e}")
        return 0

# =========================
# SIGNAL ENGINE
# =========================
def get_signals():
    ranked = []

    for s in SYMBOLS:
        score = get_momentum_score(s)

        try:
            price_data = yf.Ticker(s).history(period="1d")

            if price_data.empty:
                continue

            price = price_data["Close"].iloc[-1]

            ranked.append({
                "symbol": s,
                "score": score,
                "price": float(price)
            })

        except Exception as e:
            print(f"Price error {s}: {e}")

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

# =========================
# POSITIONS
# =========================
def get_positions():
    if not api:
        return []
    try:
        return api.list_positions()
    except Exception as e:
        print("Position error:", e)
        return []

# =========================
# PROFIT LOCK
# =========================
def handle_profit_lock(p):
    try:
        if float(p.unrealized_plpc) >= PROFIT_LOCK:
            qty = int(float(p.qty) * 0.5)
            if qty > 0:
                print(f"🔒 Profit lock: {p.symbol}")
                api.submit_order(
                    symbol=p.symbol,
                    qty=qty,
                    side="sell",
                    type="market",
                    time_in_force="day"
                )
    except Exception as e:
        print("Profit lock error:", e)

# =========================
# EXIT LOGIC
# =========================
def handle_exits(p):
    try:
        if float(p.unrealized_plpc) <= WEAK_EXIT:
            print(f"❌ Weak exit: {p.symbol}")
            api.submit_order(
                symbol=p.symbol,
                qty=p.qty,
                side="sell",
                type="market",
                time_in_force="day"
            )
    except Exception as e:
        print("Exit error:", e)

# =========================
# ENTRY LOGIC
# =========================
def handle_entries(signals, current_symbols):
    if not api or not signals:
        return

    try:
        account = api.get_account()
        cash = float(account.cash)

        for s in signals[:2]:  # top 2 signals
            if s["symbol"] not in current_symbols:
                qty = int((cash * RISK_PER_TRADE) / s["price"])

                if qty > 0:
                    print(f"🚀 Buying {s['symbol']}")
                    api.submit_order(
                        symbol=s["symbol"],
                        qty=qty,
                        side="buy",
                        type="market",
                        time_in_force="day"
                    )

    except Exception as e:
        print("Entry error:", e)

# =========================
# BOT
# =========================
def run_bot():
    if not api:
        return {"error": "no api"}

    if not market_open():
        return {"status": "market closed"}

    positions = get_positions()
    signals = get_signals()

    current_symbols = [p.symbol for p in positions]

    for p in positions:
        handle_profit_lock(p)
        handle_exits(p)

    handle_entries(signals, current_symbols)

    return {
        "status": "ran",
        "positions": current_symbols,
        "top_signals": signals[:3]
    }

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Bot running"

@app.route("/health")
def health():
    return jsonify({"status": "running"})

@app.route("/debug")
def debug():
    return jsonify({
        "has_key": bool(API_KEY),
        "has_secret": bool(API_SECRET),
        "market_open": market_open(),
        "positions": [p.symbol for p in get_positions()],
        "signals": get_signals()
    })

@app.route("/run")
def run():
    return jsonify(run_bot())

# =========================
# RAILWAY PORT FIX
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
