import yfinance as yf
import pandas as pd


def fetch_prices(symbol, period="max"):
    df = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        actions=False,
        progress=False
    )

    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df["Symbol"] = symbol

    return df