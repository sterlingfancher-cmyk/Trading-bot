from flask import Flask
import os

app = Flask(__name__)

# =========================
# ROOT
# =========================
@app.route("/")
def home():
    return {"status": "running"}

# =========================
# ENV CHECK
# =========================
@app.route("/env_check")
def env_check():
    return {
        "key_exists": bool(os.environ.get("ALPACA_API_KEY")),
        "secret_exists": bool(os.environ.get("ALPACA_SECRET_KEY"))
    }

# =========================
# RAW KEY CHECK
# =========================
@app.route("/raw_key")
def raw_key():
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")

    return {
        "key_length": len(key),
        "secret_length": len(secret),
        "key_starts_with": key[:4]
    }

# =========================
# ALPACA TEST (NEW SDK)
# =========================
@app.route("/alpaca_test")
def alpaca_test():
    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=os.environ.get("ALPACA_API_KEY"),
            secret_key=os.environ.get("ALPACA_SECRET_KEY"),
            paper=True
        )

        account = client.get_account()

        return {
            "status": account.status,
            "buying_power": account.buying_power
        }

    except Exception as e:
        return {"error": str(e)}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
