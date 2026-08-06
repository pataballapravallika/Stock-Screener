import streamlit as st
import yfinance as yf
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
latest = df.iloc[-1]
tech_result = score_technical(latest)

st.subheader(f"Backtest: {company} ({symbol})")
st.caption(f"Strategy: {strategy} | Period: {period} | Capital: ₹{initial_capital:,.0f}")

st.divider()

signals = []
close_prices = df["Close"].values
for i in range(len(df)):
    row = df.iloc[i]
    if strategy == "Buy on BUY Signal, Sell on SELL Signal":
        if tech_result["signal"] == "BUY":
            signals.append(1)
        elif tech_result["signal"] == "SELL":
            signals.append(0)
        else:
            signals.append(0 if len(signals) == 0 else signals[-1])
    elif strategy == "Buy on BUY Signal, Hold Otherwise":
        if tech_result["signal"] == "BUY":
            signals.append(1)
        else:
            signals.append(1 if len(signals) > 0 and signals[-1] == 1 else 0)
    elif strategy == "Mean Reversion (RSI < 30 Buy, RSI > 70 Sell)":
        rsi_val = row.get("RSI", 50)
        if pd.notna(rsi_val):
            if rsi_val < 30:
                signals.append(1)
            elif rsi_val > 70:
                signals.append(0)
            else:
                signals.append(0 if len(signals) == 0 else signals[-1])
        else:
            signals.append(0 if len(signals) == 0 else signals[-1])
    elif strategy == "Trend Following (MA Crossover)":
        if pd.notna(row.get("MA50")) and pd.notna(row.get("MA200")):
            if row["MA50"] > row["MA200"]:
                signals.append(1)
            else:
                signals.append(0)
        else:
            signals.append(0 if len(signals) == 0 else signals[-1])
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
entry_price = 0
trades = []

for i in range(len(df)):
    row = df.iloc[i]
    signal = signals[i]
    price = close_prices[i]

    if signal == 1 and position == 0:
        position = 1
        entry_price = price
        entry_idx = i
    elif signal == 0 and position == 1:
        position = 0
        exit_price = price
        trade_return = (exit_price - entry_price) / entry_price
        trades.append({
            "entry_date": df.iloc[entry_idx]["Date"],
            "exit_date": row["Date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return": trade_return,
        })
        equity_curve.append(equity_curve[-1] * (1 + trade_return))
    elif signal == 1 and position == 1:
        equity_curve.append(equity_curve[-1])
    else:
        equity_curve.append(equity_curve[-1])

equity_series = pd.Series(equity_curve)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Return", f"{(equity_series.iloc[-1] / initial_capital - 1) * 100:.2f}%")
c2.metric("CAGR", f"{cagr(equity_series, initial_capital, len(df)) * 100:.2f}%" if len(df) > 0 else "N/A")
c3.metric("Win Rate", f"{win_rate_from_trades([t['return'] for t in trades]) * 100:.1f}%" if trades else "N/A")
c4.metric("Max Drawdown", f"{max_drawdown(equity_series) * 100:.2f}%")
c5.metric("Sharpe Ratio", f"{sharpe_ratio(pd.Series([t['return'] for t in trades])):.2f}" if trades else "N/A")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Equity Curve")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(range(len(equity_series))), y=equity_series.values, name="Strategy"))
    buy_hold_return = initial_capital * (df["Close"].iloc[-1] / df["Close"].iloc[0])
    fig.add_trace(go.Scatter(x=list(range(len(df))), y=[buy_hold_return] * len(df), name="Buy & Hold", line=dict(dash="dash")))
    fig.update_layout(height=400, xaxis_title="Trade Number", yaxis_title="Portfolio Value (₹)")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Trade Log")
    if trades:
        trade_df = pd.DataFrame(trades)
        trade_df["entry_date"] = trade_df["entry_date"].apply(lambda x: str(x)[:10] if hasattr(x, 'strftime') else str(x))
        trade_df["exit_date"] = trade_df["exit_date"].apply(lambda x: str(x)[:10] if hasattr(x, 'strftime') else str(x))
        trade_df["return"] = trade_df["return"].apply(lambda x: f"{x*100:.2f}%")
        st.dataframe(trade_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No trades executed with this strategy.")

st.divider()

st.subheader("Monthly & Yearly Returns")
try:
    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    df["Monthly_Return"] = df["Close"].pct_change()
    monthly_returns = df["Monthly_Return"].resample("M").apply(lambda x: (1 + x).prod() - 1)
    yearly_returns = df["Close"].resample("Y").apply(lambda x: (x.iloc[-1] / x.iloc[0] - 1) * 100)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Monthly Returns**")
        monthly_df = pd.DataFrame({"Return %": monthly_returns.dropna() * 100})
        st.dataframe(monthly_df.tail(12), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Yearly Returns**")
        yearly_df = pd.DataFrame({"Return %": yearly_returns})
        st.dataframe(yearly_df, use_container_width=True, hide_index=True)
except Exception:
    st.caption("Unable to compute monthly/yearly returns.")

st.divider()

st.subheader("Additional Metrics")
if trades:
    trade_returns = [t["return"] for t in trades]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Average Gain", f"{np.mean([r for r in trade_returns if r > 0]) * 100:.2f}%")
    c2.metric("Average Loss", f"{np.mean([r for r in trade_returns if r < 0]) * 100:.2f}%")
    c3.metric("Profit Factor", f"{abs(sum([r for r in trade_returns if r > 0])) / abs(sum([r for r in trade_returns if r < 0])):.2f}" if sum([r for r in trade_returns if r < 0]) != 0 else "N/A")
    c4.metric("Sortino Ratio", f"{sortino_ratio(pd.Series(trade_returns)):.2f}")

    c5, c6, c7 = st.columns(3)
    c5.metric("Holding Period (avg trades)", f"{np.mean([len(df.iloc[tr['entry_idx']:tr['exit_idx']]) if 'entry_idx' in tr and 'exit_idx' in tr else 0 for tr in trades]):.0f} days" if trades else "N/A")
    c6.metric("Maximum Gain", f"{max(trade_returns) * 100:.2f}%")
    c7.metric("Maximum Loss", f"{min(trade_returns) * 100:.2f}%")
else:
    st.caption("No trades to compute additional metrics.")