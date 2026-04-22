import os
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# ROOT (CONFIRM LIVE FILE)
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "LIVE CHECK",
        "file": __file__,
        "message": "If you see this, Railway is running THIS file"
    })

# =========================
# HEALTH
# =========================
@app.route("/health")
def health():
    return jsonify({
        "status": "running"
    })

# =========================
# ANALYZE TEST ROUTE
# =========================
@app.route("/analyze")
def analyze():
    return jsonify({
        "status": "analyze route confirmed"
    })

# =========================
# RUN
# =========================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
