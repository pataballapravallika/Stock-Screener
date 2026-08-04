import numpy as np


def total_return(equity):
    return (
        equity.iloc[-1] /
        equity.iloc[0]
    ) - 1


def max_drawdown(equity):

    peak = equity.cummax()

    drawdown = (
        equity - peak
    ) / peak

    return drawdown.min()


def sharpe_ratio(returns):

    if returns.std() == 0:
        return 0

    return (
        np.sqrt(252) *
        returns.mean() /
        returns.std()
    )


def win_rate(returns):

    trades = returns[returns != 0]

    if len(trades) == 0:
        return 0

    return (
        trades > 0
    ).mean()