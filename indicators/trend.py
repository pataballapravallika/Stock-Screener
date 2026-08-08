import pandas as pd


def moving_averages(df):
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()

    # Exponential moving averages (presets)
    for span in [9, 21, 50, 100, 150, 200]:
        col = f"EMA{span}"
        df[col] = df["Close"].ewm(span=span, adjust=False).mean()

    return df


def bollinger_bands(df, period=20):
    middle = df["Close"].rolling(period).mean()
    std = df["Close"].rolling(period).std()

    df["BB_Middle"] = middle
    df["BB_Upper"] = middle + (2 * std)
    df["BB_Lower"] = middle - (2 * std)

    return df


def vwap(df):
    typical = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3

    df["VWAP"] = (
        (typical * df["Volume"]).cumsum() /
        df["Volume"].cumsum()
    )

    return df


def high_52_week(df):
    window_size = min(252, len(df)) if len(df) > 0 else 1
    df["52W_High"] = (
        df["High"]
        .rolling(window_size, min_periods=1)
        .max()
    )

    df["Distance_52W_High"] = (
        (df["Close"] - df["52W_High"])
        / df["52W_High"]
    ) * 100

    return df


def breakout(df, period=20):
    previous_high = (
        df["High"]
        .rolling(period)
        .max()
        .shift(1)
    )

    df["Breakout"] = df["Close"] > previous_high

    return df


def breakout_status(df, period=20, near_pct=0.02):
    """Classify breakout status with a simple heuristic.

    Statuses: Confirmed Breakout, Near Breakout, Retest, Base Building, Breakout Failed
    """
    previous_high = df["High"].rolling(period).max().shift(1)
    status = []
    for i in range(len(df)):
        try:
            close = df.iloc[i]["Close"]
            ph = previous_high.iloc[i]
            if ph is None or ph != ph:  # NaN
                status.append("Base Building")
                continue
            if close > ph:
                status.append("Confirmed Breakout")
            elif close >= ph * (1 - near_pct):
                status.append("Near Breakout")
            else:
                # simple retest detection: if within last period price crossed above and fell back
                if i >= 1 and df.iloc[i-1].get("Close", 0) > ph and close < ph:
                    status.append("Retest")
                else:
                    status.append("Base Building")
        except Exception:
            status.append("Base Building")

    df["BreakoutStatus"] = status
    return df