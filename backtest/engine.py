import pandas as pd

from backtest.metrics import (
    total_return,
    max_drawdown,
    sharpe_ratio,
    win_rate
)


def run_backtest(df, initial_capital=100000):

    data = df.copy()

    # Example strategy:
    # price above MA200
    # MA50 above MA200
    # RSI between 50-70
    # MACD bullish

    data["Signal"] = (
        (data["Close"] > data["MA200"]) &
        (data["MA50"] > data["MA200"]) &
        (data["RSI"] > 50) &
        (data["RSI"] < 70) &
        (data["MACD"] > data["MACD_Signal"])
    ).astype(int)

    # CRITICAL:
    # Shift signal to avoid using today's closing
    # information to trade at today's close.
    data["Position"] = data["Signal"].shift(1).fillna(0)

    data["Market_Return"] = (
        data["Close"].pct_change()
    )

    data["Strategy_Return"] = (
        data["Position"] *
        data["Market_Return"]
    )

    data["Equity"] = (
        initial_capital *
        (1 + data["Strategy_Return"].fillna(0)).cumprod()
    )

    metrics = {
        "Total Return": total_return(data["Equity"]),
        "Win Rate": win_rate(data["Strategy_Return"]),
        "Max Drawdown": max_drawdown(data["Equity"]),
        "Sharpe Ratio": sharpe_ratio(
            data["Strategy_Return"].dropna()
        )
    }

    return data, metrics