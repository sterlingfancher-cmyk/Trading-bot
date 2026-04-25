def run_engine():
    try:
        data = load_data(UNIVERSE + ["SPY"])

        if not data:
            return {"error": "no data"}

        portfolio["regime"] = detect_regime(data)

        eq = portfolio["cash"]

        # ===== MARK TO MARKET (SMART SIMULATION) =====
        for s, pos in portfolio["positions"].items():

            if s in data:
                new_px = data[s][-1]
            else:
                new_px = pos["last_price"]

            # 🔥 KEY FIX: detect stale price
            if abs(new_px - pos["last_price"]) < 1e-8:
                px = simulate_price(pos["last_price"])
                simulated = True
            else:
                px = new_px
                simulated = False

            pos["last_price"] = px
            pos["peak"] = max(pos.get("peak", px), px)

            eq += pos["shares"] * px

        portfolio["equity"] = eq
        portfolio["peak"] = max(portfolio["peak"], eq)

        # ===== RISK ENGINE =====
        dd = (portfolio["equity"] - portfolio["peak"]) / portfolio["peak"]

        if dd < -0.10:
            portfolio["positions"] = {}
            portfolio["cash"] = portfolio["equity"]
            portfolio["trades"].append({"type": "kill_switch"})
            return {"risk": "portfolio liquidated"}

        # ===== POSITION MANAGEMENT =====
        for s in list(portfolio["positions"].keys()):
            pos = portfolio["positions"][s]
            px = pos["last_price"]
            entry = pos["entry"]

            pnl = (px - entry) / entry

            if pnl < -0.05 or px < pos["peak"] * 0.95 or pnl > 0.12:
                portfolio["cash"] += px * pos["shares"]
                del portfolio["positions"][s]

        # ===== SIGNALS =====
        sig = generate_signals(data)

        max_positions = 5 if portfolio["regime"] == "bull" else 3

        for s, score, vol in sig:
            if s in portfolio["positions"]:
                continue

            if len(portfolio["positions"]) >= max_positions:
                break

            px = data[s][-1]

            risk_adj = min(0.2, 0.05 / (vol + 1e-6))
            alloc = portfolio["equity"] * risk_adj

            if portfolio["cash"] < alloc:
                continue

            shares = alloc / px

            portfolio["cash"] -= alloc
            portfolio["positions"][s] = {
                "entry": px,
                "shares": shares,
                "last_price": px,
                "peak": px
            }

            portfolio["trades"].append({
                "sym": s,
                "type": "entry",
                "px": px
            })

        portfolio["history"].append(portfolio["equity"])
        save_state(portfolio)

        return {
            "equity": round(portfolio["equity"], 2),
            "positions": list(portfolio["positions"].keys()),
            "signals_found": len(sig)
        }

    except Exception as e:
        portfolio["errors"].append(traceback.format_exc())
        return {"error": "engine failure", "detail": str(e)}
