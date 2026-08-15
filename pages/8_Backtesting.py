import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from backtest.engine import run_backtest, calculate_metrics
from backtest.metrics import (
    total_return,
    cagr,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    win_rate_from_trades,
    avg_trade_return,
    best_trade,
    worst_trade,
)
from scoring.config import (
    ScoringConfig,
    BacktestConfig,
    DEFAULT_CONFIG,
    DEFAULT_BACKTEST_CONFIG,
)
from scoring.technical_score import compute_technical_indicators, score_technical

st.set_page_config(page_title="Backtesting", layout="wide")

COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Technologies": "HCLTECH.NS",
}

STRATEGIES = [
    "Buy on BUY Signal, Sell on SELL Signal",
    "Buy on BUY Signal, Hold Otherwise",
    "Mean Reversion (RSI < 30 Buy, RSI > 70 Sell)",
    "Trend Following (MA Crossover)",
    "Breakout Strategy (Buy on 20D Breakout)",
]

st.title("Backtesting")
st.caption("Strategy builder, historic simulation, and performance metrics")

with st.sidebar.expander("Backtest Settings", expanded=True):
    company = st.selectbox("Company", list(COMPANIES.keys()), key="bt_company")
    symbol = COMPANIES[company]

    initial_capital = st.number_input("Initial Capital", min_value=1000, value=100000, step=1000, key="bt_capital")
    strategy = st.selectbox("Strategy", STRATEGIES, key="bt_strategy")
    period = st.selectbox("Data Period", ["1y", "2y", "5y", "10y", "max"], index=1, key="bt_period")
    transaction_cost = st.number_input("Transaction Cost (%)", min_value=0.0, value=0.1, step=0.01, key="bt_cost")
    stop_loss = st.number_input("Stop Loss (%)", min_value=0.0, value=5.0, step=0.5, key="bt_sl")
    take_profit = st.number_input("Take Profit (%)", min_value=0.0, value=10.0, step=0.5, key="bt_tp")

period_map = {"1y": "1y", "2y": "2y", "5y": "5y", "10y": "10y", "max": "max"}
data_period = period_map[period]

@st.cache_data(ttl=3600)
def load_backtest_data(symbol, period):
    df = fetch_prices(symbol, period=period)
    return df

df = load_backtest_data(symbol, data_period)

if df.empty:
    st.error("No data available for this ticker.")
    st.stop()

df = compute_technical_indicators(df)

st.subheader(f"Backtest: {company} ({symbol})")
st.caption(f"Strategy: {strategy} | Period: {period} | Capital: ₹{initial_capital:,.0f}")

st.divider()

signals = []
close_prices = df["Close"].values
dates = df["Date"].values

for i in range(len(df)):
    row = df.iloc[i]
    if strategy == "Buy on BUY Signal, Sell on SELL Signal":
        res = score_technical(row)
        sig = res["signal"]
        if sig == "BUY":
            signals.append(1)
        elif sig == "SELL":
            signals.append(0)
        else:
            signals.append(signals[-1] if len(signals) > 0 else 0)
    elif strategy == "Buy on BUY Signal, Hold Otherwise":
        res = score_technical(row)
        sig = res["signal"]
        if sig == "BUY":
            signals.append(1)
        else:
            signals.append(1 if len(signals) > 0 and signals[-1] == 1 else 0)
    elif strategy == "Mean Reversion (RSI < 30 Buy, RSI > 70 Sell)":
        rsi_val = row.get("RSI", 50)
        if pd.notna(rsi_val):
            if rsi_val < 35:
                signals.append(1)
            elif rsi_val > 65:
                signals.append(0)
            else:
                signals.append(signals[-1] if len(signals) > 0 else 0)
        else:
            signals.append(signals[-1] if len(signals) > 0 else 0)
    elif strategy == "Trend Following (MA Crossover)":
        if pd.notna(row.get("MA50")) and pd.notna(row.get("MA200")):
            signals.append(1 if row["MA50"] > row["MA200"] else 0)
        else:
            signals.append(signals[-1] if len(signals) > 0 else 0)
    elif strategy == "Breakout Strategy (Buy on 20D Breakout)":
        if row.get("Breakout", False):
            signals.append(1)
        else:
            signals.append(0 if len(signals) == 0 else signals[-1])
    else:
        signals.append(0)

df["Signal"] = signals

equity_curve = [initial_capital]
position = 0
entry_price = 0.0
entry_idx = None
trades = []

for i in range(len(df)):
    price = close_prices[i]
    dt = dates[i]
    sig = signals[i]

    sl_triggered = False
    tp_triggered = False

    if position == 1 and entry_price > 0:
        ret_since_entry = (price - entry_price) / entry_price * 100.0
        if stop_loss > 0 and ret_since_entry <= -stop_loss:
            sl_triggered = True
        elif take_profit > 0 and ret_since_entry >= take_profit:
            tp_triggered = True

    if position == 0:
        if sig == 1:
            position = 1
            entry_price = price
            entry_idx = i
            cost = equity_curve[-1] * (transaction_cost / 100.0)
            equity_curve.append(equity_curve[-1] - cost)
        else:
            equity_curve.append(equity_curve[-1])
    elif position == 1:
        if sig == 0 or sl_triggered or tp_triggered:
            position = 0
            exit_price = price
            trade_ret = (exit_price - entry_price) / entry_price
            cost = equity_curve[-1] * (transaction_cost / 100.0)

            prev_price = close_prices[i - 1] if i > 0 else price
            daily_ret = (price - prev_price) / prev_price if prev_price > 0 else 0
            new_eq = equity_curve[-1] * (1 + daily_ret) - cost
            equity_curve.append(new_eq)

            reason = "SELL Signal"
            if sl_triggered:
                reason = "Stop Loss"
            elif tp_triggered:
                reason = "Take Profit"

            entry_dt_str = str(dates[entry_idx])[:10] if entry_idx is not None else ""
            exit_dt_str = str(dt)[:10]

            holding_days = 0
            if entry_idx is not None:
                try:
                    holding_days = (pd.to_datetime(dt) - pd.to_datetime(dates[entry_idx])).days
                except Exception:
                    holding_days = i - entry_idx

            trades.append({
                "entry_date": entry_dt_str,
                "exit_date": exit_dt_str,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "return": trade_ret - (2 * transaction_cost / 100.0),
                "holding_days": holding_days,
                "reason": reason,
                "entry_idx": entry_idx,
                "exit_idx": i,
            })
        else:
            prev_price = close_prices[i - 1] if i > 0 else price
            daily_ret = (price - prev_price) / prev_price if prev_price > 0 else 0
            equity_curve.append(equity_curve[-1] * (1 + daily_ret))

equity_series = pd.Series(equity_curve[1:])
daily_returns = equity_series.pct_change().dropna()

trade_returns = [t["return"] for t in trades]

c1, c2, c3, c4, c5 = st.columns(5)
total_ret_pct = ((equity_series.iloc[-1] / initial_capital) - 1) * 100 if len(equity_series) > 0 else 0.0
c1.metric("Total Return", f"{total_ret_pct:.2f}%")
c2.metric("CAGR", f"{cagr(equity_series, initial_capital, len(df)) * 100:.2f}%" if len(df) > 0 else "N/A")
c3.metric("Win Rate", f"{win_rate_from_trades(trade_returns) * 100:.1f}%" if trades else "N/A")
c4.metric("Max Drawdown", f"{max_drawdown(equity_series) * 100:.2f}%" if len(equity_series) > 0 else "N/A")
c5.metric("Sharpe Ratio", f"{sharpe_ratio(daily_returns):.2f}" if len(daily_returns) > 0 else "N/A")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Equity Curve")
    fig = go.Figure()
    date_axis = df["Date"].values if "Date" in df.columns else list(range(len(equity_series)))
    fig.add_trace(go.Scatter(x=date_axis, y=equity_series.values, name="Strategy Equity", line=dict(color="#00CC96", width=2)))
    buy_hold_equity = initial_capital * (df["Close"].values / df["Close"].iloc[0])
    fig.add_trace(go.Scatter(x=date_axis, y=buy_hold_equity, name="Buy & Hold", line=dict(color="#AB63FA", dash="dash")))
    fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Portfolio Value (₹)", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Trade Log")
    if trades:
        trade_df = pd.DataFrame(trades)
        display_df = trade_df[["entry_date", "exit_date", "entry_price", "exit_price", "return", "holding_days", "reason"]].copy()
        display_df.columns = ["Entry Date", "Exit Date", "Entry Price", "Exit Price", "Return", "Holding Days", "Reason"]
        display_df["Return"] = display_df["Return"].apply(lambda x: f"{x*100:.2f}%")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No trades executed with this strategy.")

st.divider()

st.subheader("Monthly & Yearly Returns")
try:
    df_returns = df.copy()
    df_returns["Date"] = pd.to_datetime(df_returns["Date"])
    df_returns.set_index("Date", inplace=True)
    monthly_returns = df_returns["Close"].resample("ME").last().pct_change().dropna()
    yearly_returns = df_returns["Close"].resample("YE").apply(lambda x: ((x.iloc[-1] / x.iloc[0]) - 1) * 100 if len(x) > 0 else 0)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Monthly Stock Returns (%)**")
        monthly_df = pd.DataFrame({"Return %": (monthly_returns * 100).round(2)})
        st.dataframe(monthly_df.tail(12), use_container_width=True)
    with c2:
        st.markdown("**Yearly Stock Returns (%)**")
        yearly_df = pd.DataFrame({"Return %": yearly_returns.round(2)})
        st.dataframe(yearly_df, use_container_width=True)
except Exception:
    st.caption("Unable to compute monthly/yearly returns.")

st.divider()

st.subheader("Additional Metrics")
if trades:
    pos_returns = [r for r in trade_returns if r > 0]
    neg_returns = [r for r in trade_returns if r < 0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Average Gain", f"{np.mean(pos_returns) * 100:.2f}%" if pos_returns else "0.00%")
    c2.metric("Average Loss", f"{np.mean(neg_returns) * 100:.2f}%" if neg_returns else "0.00%")
    prof_factor = abs(sum(pos_returns)) / abs(sum(neg_returns)) if neg_returns and sum(neg_returns) != 0 else "N/A"
    c3.metric("Profit Factor", f"{prof_factor:.2f}" if isinstance(prof_factor, float) else prof_factor)
    c4.metric("Sortino Ratio", f"{sortino_ratio(daily_returns):.2f}" if len(daily_returns) > 0 else "N/A")

    c5, c6, c7 = st.columns(3)
    avg_hold = np.mean([t["holding_days"] for t in trades]) if trades else 0
    c5.metric("Average Holding Period", f"{avg_hold:.0f} days")
    c6.metric("Maximum Gain", f"{max(trade_returns) * 100:.2f}%")
    c7.metric("Maximum Loss", f"{min(trade_returns) * 100:.2f}%")
else:
    st.caption("No trades to compute additional metrics.")