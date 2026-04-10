@app.route("/signals")
def signals():

    data = load_data()

    signals = []
    warnings = []

    capital = INITIAL_CAPITAL  # 🔥 base capital for sizing

    spy_df = data.get("SPY")

    if spy_df is None:
        return jsonify({
            "date": None,
            "market": "unknown",
            "signals": [],
            "warning": "SPY data unavailable"
        })

    last_date = spy_df.index[-1]

    # Market regime
    if spy_df.loc[last_date]["c"] <= spy_df.loc[last_date]["ma"]:
        return jsonify({
            "date": str(last_date),
            "market": "bearish",
            "signals": []
        })

    # Rank symbols
    rs = []
    for symbol, df in data.items():
        try:
            if last_date in df.index:
                rs.append((symbol, df.loc[last_date]["momentum"]))
        except:
            warnings.append(f"{symbol} data issue")

    rs = sorted(rs, key=lambda x: x[1], reverse=True)
    top_symbols = [s[0] for s in rs[:TOP_N]]

    for symbol in top_symbols:

        df = data.get(symbol)

        if df is None or last_date not in df.index:
            continue

        row = df.loc[last_date]

        trend = row["c"] > row["ma"]
        breakout = row["c"] > row["high_break"]
        vol = row["atr_change"] > 0

        if trend and breakout and vol:

            entry = row["c"]
            stop = entry - (ATR_MULT * row["atr"])

            risk_per_share = entry - stop

            if risk_per_share <= 0:
                continue

            # 🔥 POSITION SIZING
            risk_amount = capital * RISK_PER_TRADE
            shares = int(risk_amount / risk_per_share)

            position_value = shares * entry

            signals.append({
                "symbol": symbol,
                "price": round(entry, 2),
                "momentum": round(row["momentum"], 3),
                "stop": round(stop, 2),
                "shares": shares,
                "position_size": round(position_value, 2),
                "risk_amount": round(risk_amount, 2)
            })

    return jsonify({
        "date": str(last_date),
        "market": "bullish",
        "signals": signals,
        "warnings": warnings
    })
