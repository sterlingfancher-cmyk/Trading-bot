from flask import Flask
import os

app = Flask(__name__)

# =========================
# ROOT (MUST WORK FIRST)
# =========================
@app.route("/")
def home():
    return {"status": "running"}

# =========================
# ENV CHECK (VERIFY VARIABLES)
# =========================
@app.route("/env_check")
def env_check():
    return {
        "key_exists": bool(os.environ.get("ALPACA_API_KEY")),
        "secret_exists": bool(os.environ.get("ALPACA_SECRET_KEY")),
        "base_url": os.environ.get("ALPACA_BASE_URL")
    }

# =========================
# ALPACA TEST
# =========================
@app.route("/alpaca_test")
def alpaca_test():
    try:
        from alpaca_trade_api.rest import REST

        api = REST(
            os.environ.get("ALPACA_API_KEY"),
            os.environ.get("ALPACA_SECRET_KEY"),
            "https://paper-api.alpaca.markets",
            api_version="v2"
        )

        account = api.get_account()

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
