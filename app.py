from flask import Flask
import os
import subprocess
import sys

app = Flask(__name__)

# Force install alpaca if missing
try:
    import alpaca
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "alpaca-py"])

@app.route("/")
def home():
    return {"status": "running"}

@app.route("/alpaca_test")
def alpaca_test():
    try:
        from alpaca.trading.client import TradingClient

        key = os.environ.get("ALPACA_API_KEY")
        secret = os.environ.get("ALPACA_SECRET_KEY")

        client = TradingClient(
            api_key=key,
            secret_key=secret,
            paper=True
        )

        account = client.get_account()

        return {
            "status": account.status,
            "buying_power": account.buying_power,
            "account_number": account.account_number
        }

    except Exception as e:
        return {
            "error": str(e),
            "key_prefix": key[:4] if key else None,
            "key_length": len(key) if key else 0,
            "secret_length": len(secret) if secret else 0
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
