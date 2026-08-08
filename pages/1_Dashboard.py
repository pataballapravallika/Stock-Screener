import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental, safe_float
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from scoring.config import DEFAULT_CONFIG, score_category, signal_badge
from fundamentals.growth import calculate_growth_metrics
from fundamentals.ratios import compute_roe, compute_roa, compute_roce, compute_debt_equity, compute_opm, compute_npm
from fundamentals.altman import compute_altman_z
from fundamentals.piotroski import compute_piotroski_f_score

from data.ui_helpers import render_official_data_header

st.set_page_config(page_title="Dashboard", layout="wide")

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

BENCHMARK_SYMBOL = "^CRSLDX"

st.title("Dashboard")
st.caption("Overall score, signal, and ranking overview")

company = st.sidebar.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=1800)
def load_dashboard_data(symbol):
    df = fetch_prices(symbol, period="1y")
    fund = fetch_fundamentals(symbol) or {}
    return df, fund

df, fund = load_dashboard_data(symbol)

render_official_data_header(fund)

if df.empty:
    st.error("No data available for this ticker.")
    st.stop()

df = compute_technical_indicators(df)
latest = df.iloc[-1]
tech_result = score_technical(latest)

sector = fund.get("Sector") or "Unknown"
industry = fund.get("Industry") or "Unknown"
is_bank = any(b.lower() in sector.lower() for b in {"Financial Services", "Banking", "Finance", "Insurance"})

fund_for_scoring = {
    "EPS_Growth": fund.get("EarningsGrowth"),
    "Revenue_Growth": fund.get("RevenueGrowth"),
    "PAT_Growth": None,
    "ROE": fund.get("ROE"),
    "ROCE": fund.get("ROCE"),
    "ROA": fund.get("ROA"),
    "Debt_Equity": fund.get("DebtEquity"),
}

if is_bank:
    bank_data = {
        "NIM": fund.get("NIM"),
        "NII": fund.get("NII"),
        "CASA_Ratio": fund.get("CASA_Ratio"),
        "GNPA": fund.get("GNPA"),
        "NNPA": fund.get("NNPA"),
        "PCR": fund.get("PCR"),
        "Advances_Growth": fund.get("Advances_Growth"),
        "Deposits_Growth": fund.get("Deposits_Growth"),
        "CAR": fund.get("CAR"),
        "ROA": fund.get("ROA"),
        "ROE": fund.get("ROE"),
    }
    fund_score_result = {"percentage": score_banking(bank_data)["percentage"], "signal": score_banking(bank_data)["signal"]}
else:
    fund_score_result = score_fundamental(fund_for_scoring)

combined = combined_score(
    technical_result=tech_result,
    fundamental_result=fund_score_result,
    is_bank=is_bank,
)

overall_score = combined["combined_percentage"]
signal = combined["combined_signal"]
tech_pct = tech_result["percentage"]
fund_pct = fund_score_result["percentage"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Overall Score", f"{overall_score:.0f}/100")
c2.metric("Signal", signal, delta=f"Tech: {tech_pct:.0f}% | Fund: {fund_pct:.0f}%")
c3.metric("Sector", sector)
c4.metric("Industry", industry)
c5.metric("Market Cap", f"${fund.get('MarketCap', 0)/1e9:.2f}B" if fund.get("MarketCap") else "N/A")

st.divider()

st.subheader("Score Breakdown")
col1, col2 = st.columns(2)
with col1:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=overall_score,
        title={"text": "Combined Score"},
        gauge={"axis": {"range": [0, 100]},
               "bar": {"color": "green" if overall_score >= 70 else "orange" if overall_score >= 40 else "red"},
               "steps": [{"range": [0, 40], "color": "lightcoral"},
                         {"range": [40, 70], "color": "lightyellow"},
                         {"range": [70, 100], "color": "lightgreen"}]}))
st.plotly_chart(fig, use_container_width=True)


# ============================================================
# MARKET OVERVIEW
# ============================================================

MARKET_COMPANIES = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "State Bank of India": "SBIN.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "Wipro": "WIPRO.NS",
    "HCL Technologies": "HCLTECH.NS",
}


@st.cache_data(ttl=1800)
def get_market_data():
    rows = []
    for company, symbol in MARKET_COMPANIES.items():
        try:
            df = yf.download(
                symbol,
                period="10d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            required = ["Open", "High", "Low", "Close", "Volume"]
            if not all(column in df.columns for column in required):
                continue
            df = df.dropna(subset=["Close"])
            if len(df) < 2:
                continue
            latest = df.iloc[-1]
            previous = df.iloc[-2]
            current_close = float(latest["Close"])
            previous_close = float(previous["Close"])
            if previous_close == 0:
                change_percent = 0
            else:
                change_percent = ((current_close - previous_close) / previous_close) * 100
            rows.append({
                "Company": company,
                "Symbol": symbol,
                "Date": df.index[-1].date(),
                "Open": float(latest["Open"]),
                "High": float(latest["High"]),
                "Low": float(latest["Low"]),
                "Close": current_close,
                "Volume": int(latest["Volume"]),
                "Change %": change_percent,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


st.divider()
st.title("Market Overview")
st.caption("Latest OHLCV data and daily performance for selected NSE stocks.")

with st.spinner("Fetching latest market data..."):
    market = get_market_data()

if market.empty:
    st.error("No market data could be retrieved.")
    st.info("Check your internet connection and whether Yahoo Finance is responding.")
    st.stop()

numeric_columns = ["Open", "High", "Low", "Close", "Volume", "Change %"]
for column in numeric_columns:
    market[column] = pd.to_numeric(market[column], errors="coerce")

valid_changes = market.dropna(subset=["Change %"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Stocks Loaded", len(market))

if not valid_changes.empty:
    gainer_index = valid_changes["Change %"].idxmax()
    gainer = valid_changes.loc[gainer_index]
    c2.metric("Top Gainer", gainer["Company"], f"{gainer['Change %']:.2f}%")
else:
    c2.metric("Top Gainer", "N/A")

if not valid_changes.empty:
    loser_index = valid_changes["Change %"].idxmin()
    loser = valid_changes.loc[loser_index]
    c3.metric("Top Loser", loser["Company"], f"{loser['Change %']:.2f}%")
else:
    c3.metric("Top Loser", "N/A")

valid_volume = market.dropna(subset=["Volume"])
if not valid_volume.empty:
    volume_index = valid_volume["Volume"].idxmax()
    most_active = valid_volume.loc[volume_index]
    c4.metric("Highest Volume", most_active["Company"], f"{most_active['Volume']:,.0f}")
else:
    c4.metric("Highest Volume", "N/A")

st.divider()

advancers = (market["Change %"] > 0).sum()
decliners = (market["Change %"] < 0).sum()
unchanged = (market["Change %"] == 0).sum()

c1, c2, c3 = st.columns(3)
c1.metric("Advancers", int(advancers))
c2.metric("Decliners", int(decliners))
c3.metric("Unchanged", int(unchanged))

st.subheader("Latest OHLCV")
display = market.copy()
price_columns = ["Open", "High", "Low", "Close", "Change %"]
display[price_columns] = display[price_columns].round(2)
display = display.sort_values("Change %", ascending=False, na_position="last")
st.dataframe(display, use_container_width=True, hide_index=True)

st.subheader("Daily Performance")
chart_data = market.dropna(subset=["Change %"])
if not chart_data.empty:
    chart_data = chart_data.sort_values("Change %", ascending=False)
    fig = px.bar(chart_data, x="Company", y="Change %", title="Previous Close → Latest Close (%)")
    fig.update_layout(height=450, xaxis_title="Company", yaxis_title="Change (%)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Daily change data is unavailable.")

st.subheader("Trading Volume")
volume_data = market.dropna(subset=["Volume"])
if not volume_data.empty:
    volume_data = volume_data.sort_values("Volume", ascending=False)
    volume_fig = px.bar(volume_data, x="Company", y="Volume", title="Latest Trading Volume")
    volume_fig.update_layout(height=450)
    st.plotly_chart(volume_fig, use_container_width=True)

st.subheader("Latest Closing Prices")
price_data = market.dropna(subset=["Close"])
if not price_data.empty:
    price_fig = px.bar(price_data.sort_values("Close", ascending=False), x="Company", y="Close", title="Latest Closing Price")
    price_fig.update_layout(height=450, yaxis_title="Price (₹)")
    st.plotly_chart(price_fig, use_container_width=True)

st.divider()
csv = market.to_csv(index=False).encode("utf-8")
st.download_button(label="Download Market Data", data=csv, file_name="market_overview.csv", mime="text/csv")

if st.button("Refresh Market Data"):
    st.cache_data.clear()
    st.rerun()

with col2:
    cat = score_category(overall_score)
    st.metric("Score Category", cat)
    st.metric("Technical Score", f"{tech_pct:.0f}%", delta=signal_badge(tech_result["signal"]))
    st.metric("Fundamental Score", f"{fund_pct:.0f}%", delta=signal_badge(fund_score_result["signal"]))

st.divider()

st.subheader("Sector & Industry Rank")
rank_cols = st.columns(3)
with rank_cols[0]:
    st.markdown("**Sector Rank**")
    st.info(f"#{sector} — Based on combined score within {sector} peers")
with rank_cols[1]:
    st.markdown("**Industry Rank**")
    st.info(f"#{industry} — Based on combined score within {industry} peers")
with rank_cols[2]:
    st.markdown("**Benchmark Comparison**")
    try:
        bench_df = fetch_prices("^CRSLDX", period="1y")
        if not bench_df.empty:
            bench_latest = bench_df.iloc[-1]["Close"]
            bench_start = bench_df.iloc[0]["Close"]
            bench_return = (bench_latest - bench_start) / bench_start * 100
            stock_return = (latest["Close"] / df.iloc[0]["Close"] - 1) * 100
            st.metric("NIFTY 500 Return (1Y)", f"{bench_return:.2f}%")
            st.metric("Stock Return (1Y)", f"{stock_return:.2f}%")
            st.metric("Outperformance", f"{stock_return - bench_return:.2f}%")
    except Exception:
        st.caption("Benchmark data unavailable")

st.divider()

st.subheader("Recent Price Trend")
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df["Date"], open=df["Open"], high=df["High"],
    low=df["Low"], close=df["Close"], name="OHLC"))
fig.add_trace(go.Scatter(x=df["Date"], y=df["MA50"], name="MA50", line=dict(color="orange", width=1)))
fig.add_trace(go.Scatter(x=df["Date"], y=df["MA200"], name="MA200", line=dict(color="blue", width=1)))
fig.update_layout(height=400, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)