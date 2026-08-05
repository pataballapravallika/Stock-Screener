import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.combined_score import combined_score
from scoring.config import BacktestConfig, DEFAULT_BACKTEST_CONFIG


def _extract_trades(
    positions: pd.Series,
    returns: pd.Series,
    dates: pd.Series,
) -> List[dict]:
    trades = []
    in_trade = False
    entry_idx = None
    entry_price = None
    entry_date = None

    for i in range(len(positions)):
        pos = positions.iloc[i]
        ret = returns.iloc[i] if i < len(returns) else 0.0
        dt = dates.iloc[i] if hasattr(dates, "iloc") else dates[i]

        if not in_trade and pos == 1:
            in_trade = True
            entry_idx = i
            entry_date = dt
            entry_price = None
        elif in_trade and pos == 0:
            in_trade = False
            exit_idx = i
            exit_date = dt
            trade_return = 0.0

            if entry_idx is not None and entry_idx < len(returns):
                trade_return = (
                    returns.iloc[entry_idx:exit_idx].sum()
                    if exit_idx > entry_idx
                    else 0.0
                )

            trades.append({
                "entry_date": entry_date,
                "exit_date": exit_date,
                "return": trade_return,
                "entry_idx": entry_idx,
                "exit_idx": exit_idx,
            })

    if in_trade and entry_idx is not None:
        trade_return = (
            returns.iloc[entry_idx:].sum()
            if entry_idx < len(returns)
            else 0.0
        )
        trades.append({
            "entry_date": entry_date,
            "exit_date": dates.iloc[-1] if hasattr(dates, "iloc") else dates[-1],
            "return": trade_return,
            "entry_idx": entry_idx,
            "exit_idx": len(positions) - 1,
        })

    return trades


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100000.0,
    config: Optional[BacktestConfig] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any], List[dict]]:
    from scoring.config import ScoringConfig, DEFAULT_CONFIG
    if config is None:
        config = DEFAULT_BACKTEST_CONFIG
    if scoring_config is None:
        scoring_config = DEFAULT_CONFIG

    data = df.copy()
    data = compute_technical_indicators(data)

    data["Date"] = pd.to_datetime(data["Date"])

    if config.start_date:
        data = data[data["Date"] >= config.start_date].copy()

    if len(data) < 200:
        return pd.DataFrame(), {"error": "Insufficient data for backtest"}, []

    results = []
    signals = []
    positions = []
    dates = []

    for i in range(len(data)):
        row = data.iloc[i]
        current_date = row["Date"]

        historical = data.iloc[: i + 1]
        if len(historical) < 200:
            signals.append(0)
            positions.append(0)
            dates.append(current_date)
            continue

        tech_result = score_technical(row, config=scoring_config)

        if tech_result["signal"] == "BUY":
            signals.append(1)
        elif tech_result["signal"] == "SELL":
            signals.append(-1)
        else:
            signals.append(0)

        if i == 0:
            positions.append(0)
        else:
            positions.append(signals[i - 1] if signals[i - 1] >= 0 else 0)

        dates.append(current_date)
        results.append({
            "Date": current_date,
            "Open": row.get("Open"),
            "High": row.get("High"),
            "Low": row.get("Low"),
            "Close": row["Close"],
            "Volume": row.get("Volume"),
            "Signal": signals[-1],
            "Position": positions[-1],
            "Technical_Score": tech_result["percentage"],
        })

    backtest_df = pd.DataFrame(results)
    backtest_df["Market_Return"] = backtest_df["Close"].pct_change()

    transaction_cost = config.transaction_cost / 100.0
    trades_executed = (backtest_df["Position"] != backtest_df["Position"].shift(1)).astype(int)
    backtest_df["Transaction_Cost"] = trades_executed * transaction_cost
    backtest_df["Strategy_Return"] = (
        backtest_df["Position"] * backtest_df["Market_Return"] - backtest_df["Transaction_Cost"]
    )

    equity_curve = [initial_capital]
    for ret in backtest_df["Strategy_Return"].fillna(0):
        equity_curve.append(equity_curve[-1] * (1 + ret))
    backtest_df["Strategy_Equity"] = equity_curve[1:]

    bh_curve = [initial_capital]
    for ret in backtest_df["Market_Return"].fillna(0):
        bh_curve.append(bh_curve[-1] * (1 + ret))
    backtest_df["BuyHold_Equity"] = bh_curve[1:]

    trades = _extract_trades(
        backtest_df["Position"],
        backtest_df["Strategy_Return"],
        backtest_df["Date"],
    )

    metrics = calculate_metrics(backtest_df, trades, initial_capital)

    return backtest_df, metrics, trades


def calculate_metrics(
    data: pd.DataFrame,
    trades: List[dict],
    initial_capital: float,
) -> Dict[str, Any]:
    strategy_final = data["Strategy_Equity"].iloc[-1] if not data.empty else initial_capital
    bh_final = data["BuyHold_Equity"].iloc[-1] if not data.empty else initial_capital

    strategy_return = (strategy_final / initial_capital) - 1
    bh_return = (bh_final / initial_capital) - 1

    days = len(data)
    years = days / 252.0 if days > 0 else 1.0

    cagr_strategy = (strategy_final / initial_capital) ** (1 / years) - 1 if years > 0 else 0
    cagr_bh = (bh_final / initial_capital) ** (1 / years) - 1 if years > 0 else 0

    strategy_returns = data["Strategy_Return"].dropna()
    annualized_volatility = strategy_returns.std() * np.sqrt(252) if len(strategy_returns) > 0 else 0

    risk_free_rate = 0.05
    sharpe = (
        (strategy_returns.mean() * 252 - risk_free_rate) / (strategy_returns.std() * np.sqrt(252))
        if strategy_returns.std() != 0
        else 0
    )

    equity = data["Strategy_Equity"]
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_drawdown = drawdown.min() if not drawdown.empty else 0

    completed_trades = [t for t in trades if t["exit_idx"] < len(data)]
    num_trades = len(completed_trades)
    trade_returns = [t["return"] for t in completed_trades]

    win_rate = (
        sum(1 for r in trade_returns if r > 0) / len(trade_returns)
        if len(trade_returns) > 0
        else 0
    )

    avg_trade_return = np.mean(trade_returns) if len(trade_returns) > 0 else 0
    best_trade = max(trade_returns) if len(trade_returns) > 0 else 0
    worst_trade = min(trade_returns) if len(trade_returns) > 0 else 0

    holding_periods = []
    for t in completed_trades:
        if t["entry_date"] is not None and t["exit_date"] is not None:
            hp = (t["exit_date"] - t["entry_date"]).days
            holding_periods.append(hp)
    avg_holding_period = np.mean(holding_periods) if holding_periods else 0

    return {
        "Initial Capital": initial_capital,
        "Strategy Final Value": round(strategy_final, 2),
        "Buy Hold Final Value": round(bh_final, 2),
        "Strategy Total Return": f"{strategy_return*100:.2f}%",
        "Buy Hold Total Return": f"{bh_return*100:.2f}%",
        "Strategy CAGR": f"{cagr_strategy*100:.2f}%",
        "Buy Hold CAGR": f"{cagr_bh*100:.2f}%",
        "Annualized Volatility": f"{annualized_volatility*100:.2f}%",
        "Sharpe Ratio": round(sharpe, 2),
        "Max Drawdown": f"{max_drawdown*100:.2f}%",
        "Number of Trades": num_trades,
        "Win Rate": f"{win_rate*100:.2f}%",
        "Avg Trade Return": f"{avg_trade_return*100:.2f}%",
        "Best Trade": f"{best_trade*100:.2f}%",
        "Worst Trade": f"{worst_trade*100:.2f}%",
        "Avg Holding Period (days)": round(avg_holding_period, 1),
        "Trades": trades,
    }
