import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go


COMPANIES = {
    "Reliance": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "ITC": "ITC.NS"
}


@st.cache_data(ttl=3600)
def load_data(symbol):

    df = yf.download(
        symbol,
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.reset_index()


def indicators(df):

    df = df.copy()

    # Moving averages
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()

    # RSI
    delta = df["Close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    df["RSI"] = (
        100 -
        (100 / (1 + rs))
    )

    # MACD
    ema12 = df["Close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["Close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_Signal"] = (
        df["MACD"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    # Bollinger
    df["BB_Middle"] = (
        df["Close"]
        .rolling(20)
        .mean()
    )

    std = (
        df["Close"]
        .rolling(20)
        .std()
    )

    df["BB_Upper"] = (
        df["BB_Middle"] +
        2 * std
    )

    df["BB_Lower"] = (
        df["BB_Middle"] -
        2 * std
    )

    # 52W high
    df["52W_High"] = (
        df["High"]
        .rolling(252)
        .max()
    )

    df["Distance_52W_High"] = (
        (
            df["Close"] -
            df["52W_High"]
        )
        /
        df["52W_High"]
    ) * 100

    return df


st.title(" Stock Analysis")


company = st.selectbox(
    "Company",
    list(COMPANIES)
)

symbol = COMPANIES[company]


with st.spinner(
    "Loading historical data..."
):

    df = load_data(symbol)


if df.empty:
    st.error("No data.")
    st.stop()


df = indicators(df)

latest = df.iloc[-1]


# ---------------------------
# Information
# ---------------------------

start = df["Date"].min()
end = df["Date"].max()

years = (
    (end - start).days /
    365.25
)


st.write(
    f"**Available history:** "
    f"{start.date()} → {end.date()} "
    f"({years:.1f} years)"
)


# ---------------------------
# Metrics
# ---------------------------

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Close",
    f"₹{latest['Close']:,.2f}"
)

c2.metric(
    "RSI",
    f"{latest['RSI']:.2f}"
)

c3.metric(
    "52W High",
    f"₹{latest['52W_High']:,.2f}"
)

c4.metric(
    "From 52W High",
    f"{latest['Distance_52W_High']:.2f}%"
)


# ---------------------------
# Price chart
# ---------------------------

st.subheader("Historical Price")

fig = go.Figure()

fig.add_trace(
    go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Price"
    )
)

for column in [
    "MA20",
    "MA50",
    "MA200"
]:

    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df[column],
            name=column
        )
    )


fig.update_layout(
    height=650,
    xaxis_rangeslider_visible=False
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# ---------------------------
# RSI
# ---------------------------

st.subheader("RSI")

rsi_fig = go.Figure()

rsi_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["RSI"]
    )
)

rsi_fig.add_hline(y=70)
rsi_fig.add_hline(y=30)

st.plotly_chart(
    rsi_fig,
    use_container_width=True
)


# ---------------------------
# MACD
# ---------------------------

st.subheader("MACD")

macd_fig = go.Figure()

macd_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["MACD"],
        name="MACD"
    )
)

macd_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["MACD_Signal"],
        name="Signal"
    )
)

st.plotly_chart(
    macd_fig,
    use_container_width=True
)