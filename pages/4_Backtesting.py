import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from data.fetch_prices import fetch_prices
from backtest.engine import run_backtest, calculate_metrics
from backtest.metrics import (
    total_return,
    cagr,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
)
from scoring.config import (
    ScoringConfig,
    BacktestConfig,
    DEFAULT_CONFIG,
    DEFAULT_BACKTEST_CONFIG,
)
from scoring.technical_score import compute_technical_indicators

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

st.title("Historical Backtesting")
st.caption("Test technical scoring strategy against Buy & Hold benchmark")

with st.sidebar.expander("Backtest Settings", expanded=True):
    company = st.selectbox("Company", list(COMPANIES.keys()))
    symbol = COMPANIES[company]

    initial_capital = st.number_input(
        "Initial Capital",
        min_value=1000,
        value=100000,
        step=1000
    )

    start_date = st.text_input(
        "Start Date (YYYY-MM-DD)",
        "",
        help="Leave empty to use maximum available data"
    )

    transaction_cost = st.number_input(
        "Transaction Cost (%)",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.1
    )

    stop_loss = st.number_input(
        "Stop Loss (%)",
        min_value=0.0,
        max_value=50.0,
        value=0.0,
        step=0.5,
        help="0 = no stop loss"
    )

    take_profit = st.number_input(
        "Take Profit (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
        help="0 = no take profit"
    )
with st.sidebar.expander("Technical Score Settings", expanded=True):
    buy_threshold = st.slider(
        "Buy Threshold",
        min_value=1,
        max_value=100,
        value=DEFAULT_CONFIG.buy_threshold,
        help="Score >= this triggers BUY"
    )

    sell_threshold = st.slider(
        "Sell Threshold",
        min_value=1,
        max_value=100,
        value=DEFAULT_CONFIG.sell_threshold,
        help="Score <= this triggers SELL"
    )

    rsi_min = st.slider("RSI Min", 0, 100, DEFAULT_CONFIG.rsi_min)
    rsi_max = st.slider("RSI Max", 0, 100, DEFAULT_CONFIG.rsi_max)

    max_52w = st.slider(
        "Max distance from 52W High (%)",
        min_value=-50,
        max_value=50,
        value=int(DEFAULT_CONFIG.max_52w_distance)
    )

    use_ma_trend = st.checkbox("Use MA Trend", value=DEFAULT_CONFIG.use_ma_trend)
    use_macd = st.checkbox("Use MACD", value=DEFAULT_CONFIG.use_macd)
    use_volume = st.checkbox("Use Volume", value=DEFAULT_CONFIG.use_volume)
    use_breakout = st.checkbox("Use Breakout", value=DEFAULT_CONFIG.use_breakout)
    use_supertrend = st.checkbox("Use SuperTrend", value=DEFAULT_CONFIG.use_supertrend)

run_btn = st.button("Run Backtest", type="primary")

if run_btn:
    with st.spinner("Running historical backtest..."):
        scoring_config = ScoringConfig(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            max_52w_distance=float(max_52w),
            use_ma_trend=use_ma_trend,
            use_macd=use_macd,
            use_volume=use_volume,
            use_breakout=use_breakout,
            use_supertrend=use_supertrend,
        )

        backtest_config = BacktestConfig(
            initial_capital=initial_capital,
            start_date=start_date if start_date else None,
            transaction_cost=transaction_cost,
            stop_loss=stop_loss if stop_loss > 0 else None,
            take_profit=take_profit if take_profit > 0 else None,
        )

        df = fetch_prices(symbol, period="max")

        if df.empty:
            st.error(
                "No historical data returned for this ticker. "
                "Check the symbol or internet connection."
            )
            st.stop()

        result_df, metrics, trades = run_backtest(
            df,
            initial_capital=initial_capital,
            config=backtest_config,
            scoring_config=scoring_config,
        )

        if "error" in metrics:
            st.error(metrics["error"])
            st.stop()

    st.success(
        f"Backtest complete: {len(result_df)} trading days, {len(trades)} trades"
    )

    buy_hold_info = (
        "**Buy & Hold:** Invest entire initial capital on the first trading day of the "
        "backtest period and hold through the final day. No technical indicators are used."
    )
    strategy_info = (
        "**Strategy:** BUY when technical score >= Buy Threshold. "
        "HOLD while score is between thresholds. SELL when score <= Sell Threshold. "
        "Signals execute on the following session to avoid look-ahead bias."
    )
    st.info(buy_hold_info + " " + strategy_info)

    # ============================================================
    # SUMMARY CARDS
    # ============================================================

    st.subheader("Backtest Summary")
    card_cols = st.columns(5)
    with card_cols[0]:
        st.metric("Strategy Return", metrics.get("Strategy Total Return", "N/A"))
    with card_cols[1]:
        st.metric("Buy & Hold Return", metrics.get("Buy Hold Total Return", "N/A"))
    with card_cols[2]:
        st.metric("CAGR", metrics.get("Strategy CAGR", "N/A"))
    with card_cols[3]:
        st.metric("Sharpe Ratio", metrics.get("Sharpe Ratio", "N/A"))
    with card_cols[4]:
        st.metric("Max Drawdown", metrics.get("Max Drawdown", "N/A"))

    card_cols2 = st.columns(5)
    with card_cols2[0]:
        st.metric("Win Rate", metrics.get("Win Rate", "N/A"))
    with card_cols2[1]:
        st.metric("Number of Trades", metrics.get("Number of Trades", "N/A"))
    with card_cols2[2]:
        st.metric("Avg Trade", metrics.get("Avg Trade Return", "N/A"))
    with card_cols2[3]:
        st.metric("Best Trade", metrics.get("Best Trade", "N/A"))
    with card_cols2[4]:
        st.metric("Worst Trade", metrics.get("Worst Trade", "N/A"))

    st.caption("⚠ Historical performance does not predict future results.")

    # ============================================================
    # PRICE + SIGNAL CHART
    # ============================================================

    st.subheader("Price Chart with Signals")

    price_fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=("Price + MAs + Signals", "Volume")
    )

    price_fig.add_trace(
        go.Candlestick(
            x=result_df["Date"],
            open=result_df["Open"],
            high=result_df["High"],
            low=result_df["Low"],
            close=result_df["Close"],
            name="OHLC",
            increasing_line_color="green",
            decreasing_line_color="red",
        ),
        row=1, col=1
    )

    for ma, color in [("MA50", "blue"), ("MA200", "orange")]:
        if ma in result_df.columns:
            price_fig.add_trace(
                go.Scatter(x=result_df["Date"], y=result_df[ma], mode="lines", name=ma, line=dict(color=color, width=1)),
                row=1, col=1
            )

    buy_signals = result_df[result_df["Signal"] == 1]
    sell_signals = result_df[result_df["Signal"] == -1]

    price_fig.add_trace(
        go.Scatter(x=buy_signals["Date"], y=buy_signals["Low"] * 0.995, mode="markers", name="BUY", marker=dict(symbol="triangle-up", color="green", size=10)),
        row=1, col=1
    )
    price_fig.add_trace(
        go.Scatter(x=sell_signals["Date"], y=sell_signals["High"] * 1.005, mode="markers", name="SELL", marker=dict(symbol="triangle-down", color="red", size=10)),
        row=1, col=1
    )

    colors_vol = ["green" if result_df["Close"].iloc[i] >= result_df["Close"].iloc[i-1] else "red" for i in range(len(result_df))]
    price_fig.add_trace(
        go.Bar(x=result_df["Date"], y=result_df["Volume"], name="Volume", marker_color=colors_vol, opacity=0.7),
        row=2, col=1
    )

    price_fig.update_layout(height=700, xaxis_rangeslider_visible=False, hovermode="x unified", showlegend=True)
    st.plotly_chart(price_fig, use_container_width=True)

    # ============================================================
    # PORTFOLIO COMPARISON
    # ============================================================

    st.subheader("Portfolio Comparison")

    port_fig = go.Figure()
    port_fig.add_trace(go.Scatter(x=result_df["Date"], y=result_df["Strategy_Equity"], mode="lines", name="Strategy", line=dict(color="blue")))
    port_fig.add_trace(go.Scatter(x=result_df["Date"], y=result_df["BuyHold_Equity"], mode="lines", name="Buy & Hold", line=dict(color="orange", dash="dash")))
    port_fig.update_layout(
        title="Strategy vs Buy & Hold Equity Curve",
        height=500,
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified"
    )
    st.plotly_chart(port_fig, use_container_width=True)

    # ============================================================
    # DRAWDOWN CHART
    # ============================================================

    st.subheader("Drawdown Analysis")

    strategy_equity = result_df["Strategy_Equity"]
    bh_equity = result_df["BuyHold_Equity"]

    strategy_peak = strategy_equity.cummax()
    strategy_dd = (strategy_equity - strategy_peak) / strategy_peak

    bh_peak = bh_equity.cummax()
    bh_dd = (bh_equity - bh_peak) / bh_peak

    dd_fig = go.Figure()
    dd_fig.add_trace(go.Scatter(x=result_df["Date"], y=strategy_dd, mode="lines", name="Strategy Drawdown", line=dict(color="blue"), fill="tozeroy"))
    dd_fig.add_trace(go.Scatter(x=result_df["Date"], y=bh_dd, mode="lines", name="Buy & Hold Drawdown", line=dict(color="orange", dash="dash")))
    dd_fig.update_layout(
        title="Historical Drawdown",
        height=400,
        xaxis_title="Date",
        yaxis_title="Drawdown",
        hovermode="x unified"
    )
    st.plotly_chart(dd_fig, use_container_width=True)

    # ============================================================
    # TRADE RETURN DISTRIBUTION
    # ============================================================

    st.subheader("Trade Return Distribution")

    if trades:
        trade_returns = [t["return"] * 100 for t in trades]
        trade_fig = go.Figure()
        trade_fig.add_trace(go.Histogram(x=trade_returns, nbinsx=20, marker_color="steelblue", name="Trade Returns"))
        trade_fig.add_vline(x=0, line_dash="dash", line_color="red")
        trade_fig.update_layout(
            title="Distribution of Completed Trade Returns",
            height=400,
            xaxis_title="Return (%)",
            yaxis_title="Number of Trades"
        )
        st.plotly_chart(trade_fig, use_container_width=True)

    # ============================================================
    # YEARLY PERFORMANCE
    # ============================================================

    st.subheader("Yearly Performance")

    result_df["Year"] = pd.to_datetime(result_df["Date"]).dt.year
    yearly = result_df.groupby("Year").agg({
        "Strategy_Return": lambda x: (1 + x.fillna(0)).prod() - 1,
        "Market_Return": lambda x: (1 + x.fillna(0)).prod() - 1,
    }).reset_index()

    yearly["Strategy_Return_Pct"] = (yearly["Strategy_Return"] * 100).round(2)
    yearly["BuyHold_Return_Pct"] = (yearly["Market_Return"] * 100).round(2)
    yearly["Difference"] = (yearly["Strategy_Return_Pct"] - yearly["BuyHold_Return_Pct"]).round(2)

    yearly["Strategy Return"] = yearly["Strategy_Return_Pct"].astype(str) + "%"
    yearly["Buy & Hold Return"] = yearly["BuyHold_Return_Pct"].astype(str) + "%"
    yearly["Difference"] = yearly["Difference"].astype(str) + "%"

    st.dataframe(yearly[["Year", "Strategy Return", "Buy & Hold Return", "Difference"]], use_container_width=True, hide_index=True)

    yearly_fig = go.Figure()
    yearly_fig.add_trace(go.Bar(x=yearly["Year"], y=yearly["Strategy_Return_Pct"], name="Strategy", marker_color="blue"))
    yearly_fig.add_trace(go.Bar(x=yearly["Year"], y=yearly["BuyHold_Return_Pct"], name="Buy & Hold", marker_color="orange"))
    yearly_fig.update_layout(
        title="Yearly Returns Comparison",
        height=400,
        xaxis_title="Year",
        yaxis_title="Return (%)",
        barmode="group"
    )
    st.plotly_chart(yearly_fig, use_container_width=True)

    # ============================================================
    # PERFORMANCE COMPARISON TABLE
    # ============================================================

    st.subheader("Performance Comparison")
    comparison_data = []
    for key in [
        "Strategy Total Return",
        "Buy Hold Total Return",
        "Strategy CAGR",
        "Buy Hold CAGR",
        "Annualized Volatility",
        "Sharpe Ratio",
        "Max Drawdown",
        "Number of Trades",
        "Win Rate",
        "Avg Trade Return",
        "Best Trade",
        "Worst Trade",
        "Avg Holding Period (days)",
    ]:
        comparison_data.append({
            "Metric": key,
            "Strategy": metrics.get(key, "N/A"),
            "Buy & Hold": metrics.get(
                key.replace("Strategy", "Buy Hold").replace("Strategy ", "Buy Hold "),
                "N/A"
            ),
        })

    bh_keys = {
        "Strategy Total Return": "Buy Hold Total Return",
        "Strategy CAGR": "Buy Hold CAGR",
    }
    for row in comparison_data:
        if row["Metric"] in bh_keys:
            row["Buy & Hold"] = metrics.get(bh_keys[row["Metric"]], "N/A")

    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    # ============================================================
    # TRADE HISTORY
    # ============================================================

    if trades:
        st.subheader("Trade History")
        trade_df = pd.DataFrame([
            {
                "Entry Date": t["entry_date"],
                "Exit Date": t["exit_date"],
                "Return": f"{t['return']*100:.2f}%",
            }
            for t in trades
        ])
        st.dataframe(trade_df, use_container_width=True, hide_index=True)

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Backtest Results CSV",
        data=csv,
        file_name=f"{symbol}_backtest_results.csv",
        mime="text/csv",
    )
