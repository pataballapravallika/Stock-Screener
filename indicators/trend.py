import pandas as pd


def moving_averages(df):
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()

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
    df["52W_High"] = (
        df["High"]
        .rolling(252)
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