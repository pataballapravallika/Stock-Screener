import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go


st.title("Historical Backtesting")


symbol = st.text_input(
    "Stock Symbol",
    "RELIANCE.NS"
)


initial_capital = st.number_input(
    "Initial Capital",
    min_value=1000,
    value=100000
)


if st.button("Run Backtest"):

    with st.spinner(
        "Running historical backtest..."
    ):

        df = yf.download(
            symbol,
            period="max",
            auto_adjust=False,
            progress=False
        )


    if isinstance(
        df.columns,
        pd.MultiIndex
    ):
        df.columns = (
            df.columns
            .get_level_values(0)
        )


    if df.empty:

        st.error(
            "No historical data."
        )

        st.stop()


    # Indicators

    df["MA50"] = (
        df["Close"]
        .rolling(50)
        .mean()
    )

    df["MA200"] = (
        df["Close"]
        .rolling(200)
        .mean()
    )


    # Signal

    df["Signal"] = (
        df["MA50"] >
        df["MA200"]
    ).astype(int)


    # Shift to avoid look-ahead

    df["Position"] = (
        df["Signal"]
        .shift(1)
        .fillna(0)
    )


    # Returns

    df["Market_Return"] = (
        df["Close"]
        .pct_change()
    )

    df["Strategy_Return"] = (
        df["Market_Return"] *
        df["Position"]
    )


    # Equity

    df["Strategy_Equity"] = (
        initial_capital *
        (
            1 +
            df["Strategy_Return"]
            .fillna(0)
        ).cumprod()
    )


    df["BuyHold_Equity"] = (
        initial_capital *
        (
            1 +
            df["Market_Return"]
            .fillna(0)
        ).cumprod()
    )


    # ---------------------------
    # Metrics
    # ---------------------------

    total_return = (
        df["Strategy_Equity"].iloc[-1]
        /
        initial_capital
    ) - 1


    running_max = (
        df["Strategy_Equity"]
        .cummax()
    )


    drawdown = (
        df["Strategy_Equity"]
        /
        running_max
    ) - 1


    max_drawdown = (
        drawdown.min()
    )


    returns = (
        df["Strategy_Return"]
        .dropna()
    )


    if returns.std() != 0:

        sharpe = (
            np.sqrt(252) *
            returns.mean()
            /
            returns.std()
        )

    else:

        sharpe = 0


    active = returns[
        returns != 0
    ]


    win_rate = (
        (active > 0).mean()
        if len(active)
        else 0
    )


    # ---------------------------
    # Display
    # ---------------------------

    c1, c2, c3, c4 = (
        st.columns(4)
    )


    c1.metric(
        "Total Return",
        f"{total_return*100:.2f}%"
    )


    c2.metric(
        "Win Rate",
        f"{win_rate*100:.2f}%"
    )


    c3.metric(
        "Max Drawdown",
        f"{max_drawdown*100:.2f}%"
    )


    c4.metric(
        "Sharpe Ratio",
        f"{sharpe:.2f}"
    )


    # ---------------------------
    # Equity chart
    # ---------------------------

    fig = go.Figure()


    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[
                "Strategy_Equity"
            ],
            name="Strategy"
        )
    )


    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[
                "BuyHold_Equity"
            ],
            name="Buy & Hold"
        )
    )


    fig.update_layout(
        title=(
            "Strategy vs Buy & Hold"
        ),
        height=550
    )


    st.plotly_chart(
        fig,
        use_container_width=True
    )