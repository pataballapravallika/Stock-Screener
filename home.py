# ============================================================
# STOCK SCREENER & BACKTESTING PLATFORM
# app.py
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Stock Screener",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# 2. STOCK UNIVERSE
# ============================================================

COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "State Bank of India": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Technologies": "HCLTECH.NS"
}


# ============================================================
# 3. DATA FETCHING
# ============================================================

@st.cache_data(ttl=3600)
def fetch_stock_data(symbol, period="max"):

    try:

        df = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df.empty:
            return pd.DataFrame()

        # yfinance may return MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()

        return df

    except Exception as e:

        st.error(f"Error downloading {symbol}: {e}")

        return pd.DataFrame()


# ============================================================
# 4. RSI
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# ============================================================
# 5. MACD
# ============================================================

def calculate_macd(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = macd - signal

    return macd, signal, histogram


# ============================================================
# 6. ATR
# ============================================================

def calculate_atr(df, period=14):

    previous_close = df["Close"].shift(1)

    ranges = pd.concat(
        [
            df["High"] - df["Low"],
            abs(df["High"] - previous_close),
            abs(df["Low"] - previous_close)
        ],
        axis=1
    )

    true_range = ranges.max(axis=1)

    return true_range.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


# ============================================================
# 7. ADD TECHNICAL INDICATORS
# ============================================================

def add_indicators(df):

    df = df.copy()

    # Moving averages
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()

    # RSI
    df["RSI"] = calculate_rsi(df["Close"])

    # MACD
    (
        df["MACD"],
        df["MACD_Signal"],
        df["MACD_Hist"]
    ) = calculate_macd(df["Close"])

    # ATR
    df["ATR"] = calculate_atr(df)

    # ADR
    daily_range = (
        (df["High"] - df["Low"]) /
        df["Low"]
    ) * 100

    df["ADR"] = daily_range.rolling(20).mean()

    # 52-week high
    df["52W_High"] = (
        df["High"]
        .rolling(252)
        .max()
    )

    # Distance from 52-week high
    df["Distance_52W_High"] = (
        (
            df["Close"] -
            df["52W_High"]
        )
        /
        df["52W_High"]
    ) * 100

    # Bollinger Bands
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
        (2 * std)
    )

    df["BB_Lower"] = (
        df["BB_Middle"] -
        (2 * std)
    )

    # Stochastic
    low14 = (
        df["Low"]
        .rolling(14)
        .min()
    )

    high14 = (
        df["High"]
        .rolling(14)
        .max()
    )

    denominator = high14 - low14

    df["Stochastic_K"] = np.where(
        denominator != 0,
        (
            (df["Close"] - low14)
            / denominator
        ) * 100,
        np.nan
    )

    df["Stochastic_D"] = (
        df["Stochastic_K"]
        .rolling(3)
        .mean()
    )

    # VWAP (Cumulative Volume Weighted Average Price)
    typical_price = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3
    vol = df["Volume"].replace(0, np.nan).fillna(0)
    cum_pv = (typical_price * vol).cumsum()
    cum_vol = vol.cumsum().replace(0, np.nan)
    df["VWAP"] = cum_pv / cum_vol

    # 20-day breakout
    previous_high = (
        df["High"]
        .rolling(20)
        .max()
        .shift(1)
    )

    df["Breakout"] = (
        df["Close"] >
        previous_high
    )

    # Volume average
    df["Volume_MA20"] = (
        df["Volume"]
        .rolling(20)
        .mean()
    )

    return df


# ============================================================
# 8. TECHNICAL SCORE
# ============================================================

def calculate_technical_score(row):

    score = 0

    # Price above MA200
    if (
        pd.notna(row["MA200"]) and
        row["Close"] > row["MA200"]
    ):
        score += 20

    # MA50 above MA200
    if (
        pd.notna(row["MA50"]) and
        pd.notna(row["MA200"]) and
        row["MA50"] > row["MA200"]
    ):
        score += 15

    # Healthy RSI
    if (
        pd.notna(row["RSI"]) and
        50 <= row["RSI"] <= 70
    ):
        score += 15

    # MACD bullish
    if (
        pd.notna(row["MACD"]) and
        pd.notna(row["MACD_Signal"]) and
        row["MACD"] > row["MACD_Signal"]
    ):
        score += 15

    # Near 52-week high
    if (
        pd.notna(row["Distance_52W_High"]) and
        row["Distance_52W_High"] >= -10
    ):
        score += 15

    # Breakout
    if row["Breakout"]:
        score += 10

    # Above MA20
    if (
        pd.notna(row["MA20"]) and
        row["Close"] > row["MA20"]
    ):
        score += 10

    return score


# ============================================================
# 9. SIDEBAR
# ============================================================

st.sidebar.title("Stock Screener")

st.sidebar.caption(
    "Technical Analysis & Backtesting Platform"
)

selected_company = st.sidebar.selectbox(
    "Select Company",
    list(COMPANIES.keys())
)

symbol = COMPANIES[selected_company]


period_option = st.sidebar.selectbox(
    "Historical Data",
    [
        "1 Year",
        "5 Years",
        "10 Years",
        "20 Years",
        "Maximum Available"
    ],
    index=4
)


PERIOD_MAP = {
    "1 Year": "1y",
    "5 Years": "5y",
    "10 Years": "10y",
    "20 Years": "20y",
    "Maximum Available": "max"
}

period = PERIOD_MAP[period_option]



# ============================================================
# 10. HEADER
# ============================================================

st.title("Stock Screener & Backtesting Platform")

st.caption(
    "Technical analysis, stock ranking and historical "
    "strategy research."
)

st.divider()


# ============================================================
# 11. FETCH DATA
# ============================================================

with st.spinner(
    f"Loading {period_option} of data for {selected_company}..."
):

    df = fetch_stock_data(
        symbol,
        period
    )


if df.empty:

    st.error(
        "No market data was returned. "
        "Check the ticker or internet connection."
    )

    st.stop()


# ============================================================
# 12. INDICATORS
# ============================================================

df = add_indicators(df)

latest = df.iloc[-1]

previous = (
    df.iloc[-2]
    if len(df) > 1
    else latest
)


# ============================================================
# 13. PRICE CHANGE
# ============================================================

price_change = (
    latest["Close"] -
    previous["Close"]
)

if previous["Close"] != 0:

    price_change_percent = (
        price_change /
        previous["Close"]
    ) * 100

else:

    price_change_percent = 0


# ============================================================
# 14. SCORE
# ============================================================

technical_score = calculate_technical_score(
    latest
)


# ============================================================
# 15. COMPANY INFORMATION
# ============================================================

st.subheader(
    f"{selected_company} ({symbol})"
)

start_date = pd.to_datetime(
    df["Date"].min()
)

end_date = pd.to_datetime(
    df["Date"].max()
)

years_available = (
    (end_date - start_date).days /
    365.25
)


st.caption(
    f"Available history: "
    f"{start_date.date()} → {end_date.date()} "
    f"({years_available:.1f} years)"
)


# ============================================================
# 16. MAIN METRICS
# ============================================================

c1, c2, c3, c4, c5, c6 = st.columns(6)


c1.metric(
    "Close",
    f"₹{latest['Close']:,.2f}",
    f"{price_change_percent:.2f}%"
)


c2.metric(
    "Open",
    f"₹{latest['Open']:,.2f}"
)


c3.metric(
    "Day High",
    f"₹{latest['High']:,.2f}"
)


c4.metric(
    "Day Low",
    f"₹{latest['Low']:,.2f}"
)


c5.metric(
    "Volume",
    f"{latest['Volume']:,.0f}"
)


c6.metric(
    "Technical Score",
    f"{technical_score}/100"
)


# ============================================================
# 17. SECOND METRIC ROW
# ============================================================

c1, c2, c3, c4, c5 = st.columns(5)


c1.metric(
    "RSI",
    (
        f"{latest['RSI']:.2f}"
        if pd.notna(latest["RSI"])
        else "N/A"
    )
)


c2.metric(
    "ATR",
    (
        f"{latest['ATR']:.2f}"
        if pd.notna(latest["ATR"])
        else "N/A"
    )
)


c3.metric(
    "ADR",
    (
        f"{latest['ADR']:.2f}%"
        if pd.notna(latest["ADR"])
        else "N/A"
    )
)


c4.metric(
    "52W High",
    (
        f"₹{latest['52W_High']:,.2f}"
        if pd.notna(latest["52W_High"])
        else "N/A"
    )
)


c5.metric(
    "Distance From 52W High",
    (
        f"{latest['Distance_52W_High']:.2f}%"
        if pd.notna(
            latest["Distance_52W_High"]
        )
        else "N/A"
    )
)


st.divider()


# ============================================================
# 18. PRICE CHART
# ============================================================

st.subheader(
    f"{selected_company} Price History"
)


price_fig = go.Figure()


price_fig.add_trace(
    go.Candlestick(
        x=df["Date"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="OHLC"
    )
)


price_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["MA20"],
        mode="lines",
        name="MA20"
    )
)


price_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["MA50"],
        mode="lines",
        name="MA50"
    )
)


price_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["MA200"],
        mode="lines",
        name="MA200"
    )
)


price_fig.update_layout(
    height=650,
    xaxis_rangeslider_visible=False,
    xaxis_title="Date",
    yaxis_title="Price",
    hovermode="x unified"
)


st.plotly_chart(
    price_fig,
    use_container_width=True
)


# ============================================================
# 19. RSI + MACD
# ============================================================

left, right = st.columns(2)


# ---------------- RSI ----------------

with left:

    st.subheader("RSI")

    rsi_fig = go.Figure()

    rsi_fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["RSI"],
            mode="lines",
            name="RSI"
        )
    )

    rsi_fig.add_hline(
        y=70,
        line_dash="dash"
    )

    rsi_fig.add_hline(
        y=30,
        line_dash="dash"
    )

    rsi_fig.update_layout(
        height=400,
        yaxis_range=[0, 100]
    )

    st.plotly_chart(
        rsi_fig,
        use_container_width=True
    )


# ---------------- MACD ----------------

with right:

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

    macd_fig.add_trace(
        go.Bar(
            x=df["Date"],
            y=df["MACD_Hist"],
            name="Histogram"
        )
    )

    macd_fig.update_layout(
        height=400
    )

    st.plotly_chart(
        macd_fig,
        use_container_width=True
    )


# ============================================================
# 20. BOLLINGER BANDS
# ============================================================

st.subheader("Bollinger Bands")


bb_fig = go.Figure()


bb_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["Close"],
        name="Close"
    )
)


bb_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["BB_Upper"],
        name="Upper Band"
    )
)


bb_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["BB_Middle"],
        name="Middle Band"
    )
)


bb_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["BB_Lower"],
        name="Lower Band"
    )
)


bb_fig.update_layout(
    height=450,
    hovermode="x unified"
)


st.plotly_chart(
    bb_fig,
    use_container_width=True
)


# ============================================================
# 21. VOLUME
# ============================================================

st.subheader("Trading Volume")


volume_fig = go.Figure()


volume_fig.add_trace(
    go.Bar(
        x=df["Date"],
        y=df["Volume"],
        name="Volume"
    )
)


volume_fig.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["Volume_MA20"],
        name="20-Day Average Volume"
    )
)


volume_fig.update_layout(
    height=400,
    xaxis_title="Date",
    yaxis_title="Volume"
)


st.plotly_chart(
    volume_fig,
    use_container_width=True
)


# ============================================================
# 22. TECHNICAL SUMMARY
# ============================================================

st.subheader("Technical Summary")


summary = pd.DataFrame({
    "Indicator": [
        "Close",
        "MA20",
        "MA50",
        "MA200",
        "RSI",
        "MACD",
        "MACD Signal",
        "ATR",
        "ADR",
        "VWAP",
        "Stochastic %K",
        "Stochastic %D",
        "52-Week High",
        "Distance From 52W High",
        "Breakout"
    ],

    "Value": [
        latest["Close"],
        latest["MA20"],
        latest["MA50"],
        latest["MA200"],
        latest["RSI"],
        latest["MACD"],
        latest["MACD_Signal"],
        latest["ATR"],
        latest["ADR"],
        latest["VWAP"],
        latest["Stochastic_K"],
        latest["Stochastic_D"],
        latest["52W_High"],
        latest["Distance_52W_High"],
        latest["Breakout"]
    ]
})


st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 23. SIGNAL SUMMARY
# ============================================================

st.subheader("Signal Summary")


signals = []


if (
    pd.notna(latest["MA200"]) and
    latest["Close"] > latest["MA200"]
):

    signals.append(
        ["Price vs MA200", "Bullish"]
    )

else:

    signals.append(
        ["Price vs MA200", "Bearish"]
    )


if (
    pd.notna(latest["RSI"]) and
    latest["RSI"] > 70
):

    signals.append(
        ["RSI", "Overbought"]
    )

elif (
    pd.notna(latest["RSI"]) and
    latest["RSI"] < 30
):

    signals.append(
        ["RSI", "Oversold"]
    )

else:

    signals.append(
        ["RSI", "Neutral"]
    )


if (
    pd.notna(latest["MACD"]) and
    latest["MACD"] >
    latest["MACD_Signal"]
):

    signals.append(
        ["MACD", "Bullish"]
    )

else:

    signals.append(
        ["MACD", "Bearish"]
    )


if latest["Breakout"]:

    signals.append(
        ["20-Day Breakout", "Yes"]
    )

else:

    signals.append(
        ["20-Day Breakout", "No"]
    )


signal_df = pd.DataFrame(
    signals,
    columns=[
        "Indicator",
        "Signal"
    ]
)


st.dataframe(
    signal_df,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 24. RECENT MARKET DATA
# ============================================================

st.subheader("Recent OHLCV Data")


display_columns = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume"
]


recent_data = (
    df[display_columns]
    .tail(20)
    .sort_values(
        "Date",
        ascending=False
    )
)


st.dataframe(
    recent_data,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 25. DOWNLOAD DATA
# ============================================================

st.subheader("Export Historical Data")


csv = df.to_csv(
    index=False
).encode("utf-8")


st.download_button(
    label="⬇ Download Historical CSV",
    data=csv,
    file_name=(
        f"{symbol}_historical_data.csv"
    ),
    mime="text/csv"
)


# ============================================================
# 26. DATA INFORMATION
# ============================================================

with st.expander(
    "Dataset Information"
):

    st.write(
        f"Company: {selected_company}"
    )

    st.write(
        f"Ticker: {symbol}"
    )

    st.write(
        f"First available date: "
        f"{start_date.date()}"
    )

    st.write(
        f"Latest available date: "
        f"{end_date.date()}"
    )

    st.write(
        f"Historical coverage: "
        f"{years_available:.2f} years"
    )

    st.write(
        f"Trading records: "
        f"{len(df):,}"
    )


# ============================================================
# 27. FOOTER
# ============================================================

st.divider()

st.caption(
    "Stock Screener & Backtesting Platform | "
    "Market data is provided for research and analysis purposes."
)