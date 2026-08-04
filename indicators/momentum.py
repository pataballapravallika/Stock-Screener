import pandas as pd


def rsi(close, period=14):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()

    histogram = macd_line - signal

    return macd_line, signal, histogram


def stochastic(df, period=14):
    low = df["Low"].rolling(period).min()
    high = df["High"].rolling(period).max()

    k = 100 * (
        (df["Close"] - low) /
        (high - low)
    )

    d = k.rolling(3).mean()

    return k, d