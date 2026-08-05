import numpy as np


def total_return(equity, initial_capital):
    if equity is None or len(equity) == 0 or initial_capital == 0:
        return 0
    return (equity.iloc[-1] / initial_capital) - 1


def cagr(equity, initial_capital, trading_days):
    if equity is None or len(equity) == 0 or initial_capital == 0 or trading_days == 0:
        return 0
    years = trading_days / 252.0
    if years <= 0:
        return 0
    return (equity.iloc[-1] / initial_capital) ** (1 / years) - 1


def annualized_volatility(returns):
    if returns is None or len(returns) == 0:
        return 0
    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0
    return std * np.sqrt(252)


def max_drawdown(equity):
    if equity is None or len(equity) == 0:
        return 0
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    return drawdown.min()


def sharpe_ratio(returns, risk_free_rate=0.05):
    if returns is None or len(returns) == 0:
        return 0
    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0
    return (returns.mean() * 252 - risk_free_rate) / (std * np.sqrt(252))


def win_rate_from_trades(trade_returns):
    if not trade_returns:
        return 0
    positive = sum(1 for r in trade_returns if r > 0)
    return positive / len(trade_returns)


def avg_trade_return(trade_returns):
    if not trade_returns:
        return 0
    return np.mean(trade_returns)


def best_trade(trade_returns):
    if not trade_returns:
        return 0
    return max(trade_returns)


def worst_trade(trade_returns):
    if not trade_returns:
        return 0
    return min(trade_returns)
