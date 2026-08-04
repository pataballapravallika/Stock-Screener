import pandas as pd
import numpy as np


def atr(df, period=14):

    previous_close = df["Close"].shift(1)

    tr = pd.concat([
        df["High"] - df["Low"],
        abs(df["High"] - previous_close),
        abs(df["Low"] - previous_close)
    ], axis=1).max(axis=1)

    df["ATR"] = tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    return df


def adr(df, period=20):
    daily_range = (
        (df["High"] - df["Low"]) /
        df["Low"]
    ) * 100

    df["ADR"] = daily_range.rolling(period).mean()

    return df


def supertrend(df, period=10, multiplier=3):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    previous_close = close.shift()

    tr = pd.concat([
        high - low,
        abs(high - previous_close),
        abs(low - previous_close)
    ], axis=1).max(axis=1)

    atr_value = tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    hl2 = (high + low) / 2

    upper = hl2 + multiplier * atr_value
    lower = hl2 - multiplier * atr_value

    final_upper = upper.copy()
    final_lower = lower.copy()

    trend = pd.Series(
        index=df.index,
        dtype=float
    )

    trend.iloc[0] = 1

    for i in range(1, len(df)):

        if close.iloc[i] > final_upper.iloc[i - 1]:
            trend.iloc[i] = 1

        elif close.iloc[i] < final_lower.iloc[i - 1]:
            trend.iloc[i] = -1

        else:
            trend.iloc[i] = trend.iloc[i - 1]

            if trend.iloc[i] == 1:
                final_lower.iloc[i] = max(
                    lower.iloc[i],
                    final_lower.iloc[i - 1]
                )

            else:
                final_upper.iloc[i] = min(
                    upper.iloc[i],
                    final_upper.iloc[i - 1]
                )

    df["SuperTrend"] = trend
    df["SuperTrend_Line"] = final_lower.where(
        trend == 1,
        final_upper
    )

    return df