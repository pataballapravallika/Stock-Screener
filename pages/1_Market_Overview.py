import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px


# ============================================================
# STOCK UNIVERSE
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
# FETCH MARKET DATA
# ============================================================

@st.cache_data(ttl=1800)
def get_market_data():

    rows = []

    for company, symbol in COMPANIES.items():

        try:

            df = yf.download(
                symbol,
                period="10d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False
            )

            # Skip failed downloads
            if df is None or df.empty:
                print(f"No data: {symbol}")
                continue

            # --------------------------------------------
            # Fix yfinance MultiIndex
            # --------------------------------------------

            if isinstance(df.columns, pd.MultiIndex):

                # Example:
                # ('Close', 'RELIANCE.NS')
                df.columns = df.columns.get_level_values(0)

            # --------------------------------------------
            # Ensure required columns exist
            # --------------------------------------------

            required = [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]

            if not all(
                column in df.columns
                for column in required
            ):
                print(
                    f"Missing columns: {symbol}"
                )
                continue

            # --------------------------------------------
            # Remove rows where Close is missing
            # --------------------------------------------

            df = df.dropna(
                subset=["Close"]
            )

            if len(df) < 2:
                print(
                    f"Not enough data: {symbol}"
                )
                continue

            # --------------------------------------------
            # Latest and previous trading sessions
            # --------------------------------------------

            latest = df.iloc[-1]
            previous = df.iloc[-2]

            current_close = float(
                latest["Close"]
            )

            previous_close = float(
                previous["Close"]
            )

            # Prevent division by zero
            if previous_close == 0:
                change_percent = 0
            else:
                change_percent = (
                    (
                        current_close -
                        previous_close
                    )
                    /
                    previous_close
                ) * 100

            # --------------------------------------------
            # Add result
            # --------------------------------------------

            rows.append({

                "Company":
                    company,

                "Symbol":
                    symbol,

                "Date":
                    df.index[-1].date(),

                "Open":
                    float(
                        latest["Open"]
                    ),

                "High":
                    float(
                        latest["High"]
                    ),

                "Low":
                    float(
                        latest["Low"]
                    ),

                "Close":
                    current_close,

                "Volume":
                    int(
                        latest["Volume"]
                    ),

                "Change %":
                    change_percent
            })

        except Exception as e:

            print(
                f"Error fetching {symbol}: {e}"
            )

    return pd.DataFrame(rows)


# ============================================================
# PAGE
# ============================================================

st.title("Market Overview")

st.caption(
    "Latest OHLCV data and daily performance "
    "for selected NSE stocks."
)


# ============================================================
# LOAD DATA
# ============================================================

with st.spinner(
    "Fetching latest market data..."
):

    market = get_market_data()


# ============================================================
# VALIDATION
# ============================================================

if market.empty:

    st.error(
        "No market data could be retrieved."
    )

    st.info(
        "Check your internet connection and "
        "whether Yahoo Finance is responding."
    )

    st.stop()


# Convert numeric columns explicitly

numeric_columns = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Change %"
]

for column in numeric_columns:

    market[column] = pd.to_numeric(
        market[column],
        errors="coerce"
    )


# Remove invalid Change values

valid_changes = market.dropna(
    subset=["Change %"]
)


# ============================================================
# MARKET METRICS
# ============================================================

c1, c2, c3, c4 = st.columns(4)


# Total stocks

c1.metric(
    "Stocks Loaded",
    len(market)
)


# --------------------------------------------
# Top Gainer
# --------------------------------------------

if not valid_changes.empty:

    gainer_index = (
        valid_changes["Change %"]
        .idxmax()
    )

    gainer = (
        valid_changes.loc[
            gainer_index
        ]
    )

    c2.metric(
        "Top Gainer",
        gainer["Company"],
        f"{gainer['Change %']:.2f}%"
    )

else:

    c2.metric(
        "Top Gainer",
        "N/A"
    )


# --------------------------------------------
# Top Loser
# --------------------------------------------

if not valid_changes.empty:

    loser_index = (
        valid_changes["Change %"]
        .idxmin()
    )

    loser = (
        valid_changes.loc[
            loser_index
        ]
    )

    c3.metric(
        "Top Loser",
        loser["Company"],
        f"{loser['Change %']:.2f}%"
    )

else:

    c3.metric(
        "Top Loser",
        "N/A"
    )


# --------------------------------------------
# Highest Volume
# --------------------------------------------

valid_volume = market.dropna(
    subset=["Volume"]
)


if not valid_volume.empty:

    volume_index = (
        valid_volume["Volume"]
        .idxmax()
    )

    most_active = (
        valid_volume.loc[
            volume_index
        ]
    )

    c4.metric(
        "Highest Volume",
        most_active["Company"],
        f"{most_active['Volume']:,.0f}"
    )

else:

    c4.metric(
        "Highest Volume",
        "N/A"
    )


# ============================================================
# ADVANCE / DECLINE
# ============================================================

st.divider()

advancers = (
    market["Change %"] > 0
).sum()

decliners = (
    market["Change %"] < 0
).sum()

unchanged = (
    market["Change %"] == 0
).sum()


c1, c2, c3 = st.columns(3)

c1.metric(
    "Advancers",
    int(advancers)
)

c2.metric(
    "Decliners",
    int(decliners)
)

c3.metric(
    "Unchanged",
    int(unchanged)
)


# ============================================================
# OHLCV TABLE
# ============================================================

st.subheader(
    "Latest OHLCV"
)


display = market.copy()


price_columns = [
    "Open",
    "High",
    "Low",
    "Close",
    "Change %"
]


display[price_columns] = (
    display[price_columns]
    .round(2)
)


display = display.sort_values(
    "Change %",
    ascending=False,
    na_position="last"
)


st.dataframe(
    display,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# DAILY PERFORMANCE
# ============================================================

st.subheader(
    "Daily Performance"
)


chart_data = market.dropna(
    subset=["Change %"]
)


if not chart_data.empty:

    chart_data = chart_data.sort_values(
        "Change %",
        ascending=False
    )

    fig = px.bar(
        chart_data,
        x="Company",
        y="Change %",
        title=(
            "Previous Close → Latest Close (%)"
        )
    )

    fig.update_layout(
        height=450,
        xaxis_title="Company",
        yaxis_title="Change (%)"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

else:

    st.warning(
        "Daily change data is unavailable."
    )


# ============================================================
# VOLUME
# ============================================================

st.subheader(
    "Trading Volume"
)


volume_data = market.dropna(
    subset=["Volume"]
)


if not volume_data.empty:

    volume_data = (
        volume_data.sort_values(
            "Volume",
            ascending=False
        )
    )

    volume_fig = px.bar(
        volume_data,
        x="Company",
        y="Volume",
        title="Latest Trading Volume"
    )

    volume_fig.update_layout(
        height=450
    )

    st.plotly_chart(
        volume_fig,
        use_container_width=True
    )


# ============================================================
# PRICE COMPARISON
# ============================================================

st.subheader(
    "Latest Closing Prices"
)


price_data = market.dropna(
    subset=["Close"]
)


if not price_data.empty:

    price_fig = px.bar(
        price_data.sort_values(
            "Close",
            ascending=False
        ),
        x="Company",
        y="Close",
        title="Latest Closing Price"
    )

    price_fig.update_layout(
        height=450,
        yaxis_title="Price (₹)"
    )

    st.plotly_chart(
        price_fig,
        use_container_width=True
    )


# ============================================================
# EXPORT
# ============================================================

st.divider()

csv = market.to_csv(
    index=False
).encode("utf-8")


st.download_button(
    label="⬇ Download Market Data",
    data=csv,
    file_name="market_overview.csv",
    mime="text/csv"
)


# ============================================================
# REFRESH
# ============================================================

if st.button(
    "Refresh Market Data"
):

    st.cache_data.clear()

    st.rerun()