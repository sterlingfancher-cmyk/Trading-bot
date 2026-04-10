def compute_strategy(df):
    try:
        df["ma_fast"] = df["c"].rolling(20).mean()
        df["ma_slow"] = df["c"].rolling(50).mean()
        df["returns"] = df["c"].pct_change()

        df["high_lookback"] = df["h"].rolling(10, min_periods=3).max()

        df = df.dropna().copy()

        if df.empty:
            return None, "Empty after indicators"

        df["signal"] = 0

        # FIX: ALIGN DATA
        prev_high = df["high_lookback"].shift(1)

        # Align explicitly
        df["c"], prev_high = df["c"].align(prev_high, axis=0)

        # Fill NaNs after align
        prev_high = prev_high.fillna(method="bfill").fillna(0)

        df.loc[
            (df["ma_fast"] > df["ma_slow"]) &
            (df["c"] > prev_high * 0.999),
            "signal"
        ] = 1

        df.loc[
            (df["ma_fast"] < df["ma_slow"]) |
            (df["returns"] < -0.002),
            "signal"
        ] = 0

        # fallback if no trades
        if df["signal"].sum() == 0:
            df.loc[df["ma_fast"] > df["ma_slow"], "signal"] = 1

        df["position"] = df["signal"].shift().fillna(0)
        df["strategy"] = df["position"] * df["returns"]

        return df, None

    except Exception as e:
        return None, f"Strategy error: {str(e)}"
