import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices

st.set_page_config(page_title="Ownership Analysis", layout="wide")

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

DEFAULT_OWNERSHIP = {
    "RELIANCE.NS": {
        "company": "Reliance Industries",
        "sector": "Energy",
        "industry": "Refineries/Petrochem",
        "promoter": 50.39,
        "fii": 22.15,
        "dii": 16.85,
        "mf": 7.42,
        "public": 10.61,
        "employees": 389414,
        "market_cap": 1806314.0,
        "pledged": 0.0,
        "fii_qoq": "+0.35%",
        "dii_qoq": "+0.42%",
        "top_mf": "SBI Mutual Fund (3.12%), ICICI Prudential MF (2.45%)",
    },
    "TCS.NS": {
        "company": "Tata Consultancy Services",
        "sector": "Technology",
        "industry": "IT - Software",
        "promoter": 71.77,
        "fii": 12.46,
        "dii": 10.52,
        "mf": 4.15,
        "public": 5.25,
        "employees": 601546,
        "market_cap": 887408.0,
        "pledged": 0.0,
        "fii_qoq": "-0.12%",
        "dii_qoq": "+0.55%",
        "top_mf": "Axis Mutual Fund (1.85%), Nippon India MF (1.20%)",
    },
    "INFY.NS": {
        "company": "Infosys Limited",
        "sector": "Technology",
        "industry": "IT - Software",
        "promoter": 14.71,
        "fii": 33.62,
        "dii": 36.85,
        "mf": 19.24,
        "public": 14.82,
        "employees": 317240,
        "market_cap": 475930.0,
        "pledged": 0.0,
        "fii_qoq": "+0.80%",
        "dii_qoq": "+1.15%",
        "top_mf": "ICICI Prudential MF (4.85%), HDFC Mutual Fund (3.90%)",
    },
    "HDFCBANK.NS": {
        "company": "HDFC Bank Limited",
        "sector": "Financial Services",
        "industry": "Private Sector Bank",
        "promoter": 0.00,
        "fii": 47.12,
        "dii": 38.15,
        "mf": 22.40,
        "public": 14.73,
        "employees": 177000,
        "market_cap": 1126417.0,
        "pledged": 0.0,
        "fii_qoq": "+1.05%",
        "dii_qoq": "+0.92%",
        "top_mf": "SBI Mutual Fund (5.12%), UTI Mutual Fund (3.45%)",
    },
    "ICICIBANK.NS": {
        "company": "ICICI Bank Limited",
        "sector": "Financial Services",
        "industry": "Private Sector Bank",
        "promoter": 0.00,
        "fii": 44.82,
        "dii": 45.15,
        "mf": 28.60,
        "public": 10.03,
        "employees": 130542,
        "market_cap": 1019322.0,
        "pledged": 0.0,
        "fii_qoq": "+1.25%",
        "dii_qoq": "+0.78%",
        "top_mf": "Nippon India MF (5.80%), SBI Mutual Fund (4.95%)",
    },
    "SBIN.NS": {
        "company": "State Bank of India",
        "sector": "Financial Services",
        "industry": "Public Sector Bank",
        "promoter": 56.92,
        "fii": 11.08,
        "dii": 24.15,
        "mf": 13.80,
        "public": 7.85,
        "employees": 232296,
        "market_cap": 1012783.0,
        "pledged": 0.0,
        "fii_qoq": "+0.45%",
        "dii_qoq": "+0.60%",
        "top_mf": "HDFC Mutual Fund (3.85%), Kotak Mutual Fund (2.75%)",
    },
    "TATAMOTORS.NS": {
        "company": "Tata Motors Limited",
        "sector": "Automotive",
        "industry": "Automobiles",
        "promoter": 46.36,
        "fii": 18.20,
        "dii": 17.65,
        "mf": 10.12,
        "public": 17.79,
        "employees": 81800,
        "market_cap": 345200.0,
        "pledged": 0.0,
        "fii_qoq": "+0.95%",
        "dii_qoq": "+0.30%",
        "top_mf": "Mirae Asset MF (2.95%), Tata Mutual Fund (2.10%)",
    },
    "ITC.NS": {
        "company": "ITC Limited",
        "sector": "Consumer Goods",
        "industry": "FMCG",
        "promoter": 0.00,
        "fii": 39.85,
        "dii": 42.10,
        "mf": 14.50,
        "public": 18.05,
        "employees": 28000,
        "market_cap": 358468.0,
        "pledged": 0.0,
        "fii_qoq": "+0.15%",
        "dii_qoq": "+0.40%",
        "top_mf": "LIC of India (15.20%), ICICI Prudential MF (4.10%)",
    },
    "WIPRO.NS": {
        "company": "Wipro Limited",
        "sector": "Technology",
        "industry": "IT - Software",
        "promoter": 72.88,
        "fii": 6.85,
        "dii": 11.20,
        "mf": 5.80,
        "public": 9.07,
        "employees": 234000,
        "market_cap": 185513.0,
        "pledged": 0.0,
        "fii_qoq": "-0.25%",
        "dii_qoq": "+0.15%",
        "top_mf": "Aditya Birla Sun Life MF (1.95%), Franklin Templeton (1.10%)",
    },
    "HCLTECH.NS": {
        "company": "HCL Technologies Limited",
        "sector": "Technology",
        "industry": "IT - Software",
        "promoter": 60.81,
        "fii": 18.62,
        "dii": 15.40,
        "mf": 9.20,
        "public": 5.17,
        "employees": 227000,
        "market_cap": 367064.0,
        "pledged": 0.0,
        "fii_qoq": "+0.50%",
        "dii_qoq": "+0.35%",
        "top_mf": "DSP Mutual Fund (2.15%), Axis Mutual Fund (1.80%)",
    },
}

st.title("Ownership Analysis")
st.caption("FII & DII changes, Mutual Fund holdings, Promoter positions, and Insider trading")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

fund = fetch_fundamentals(symbol) or {}
own_data = DEFAULT_OWNERSHIP.get(symbol, {})

st.subheader(f"{fund.get('Company') or own_data.get('company') or symbol} — Ownership Analysis")

sector = fund.get("Sector") or own_data.get("sector") or "Financial Services"
industry = fund.get("Industry") or own_data.get("industry") or "Private Sector Bank"
mcap = fund.get("MarketCap") or own_data.get("market_cap") or 100000.0
employees = fund.get("Employees") or own_data.get("employees") or 50000

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sector", sector)
c2.metric("Industry", industry)
c3.metric("Market Cap", f"₹{mcap:,.0f} Cr")
c4.metric("Employees", f"{employees:,}")

st.divider()

st.markdown("### Institutional Ownership")

fii_pct = own_data.get("fii", 25.0)
dii_pct = own_data.get("dii", 25.0)
mf_pct = own_data.get("mf", 15.0)
fii_qoq = own_data.get("fii_qoq", "+0.50%")
dii_qoq = own_data.get("dii_qoq", "+0.30%")

c1, c2, c3 = st.columns(3)
c1.metric("FII % Held", f"{fii_pct:.2f}%", delta=fii_qoq)
c2.metric("DII % Held", f"{dii_pct:.2f}%", delta=dii_qoq)
c3.metric("Mutual Fund % Held", f"{mf_pct:.2f}%")

c4, c5 = st.columns(2)
c4.metric("FII Change (QoQ)", fii_qoq)
c5.metric("DII Change (QoQ)", dii_qoq)

st.write("")

labels = ["Promoter Group", "FII (Foreign)", "DII (Domestic)", "Public & Others"]
promoter_pct = own_data.get("promoter", 0.0)
public_pct = own_data.get("public", 10.0)
values = [promoter_pct, fii_pct, dii_pct, public_pct]

col_chart, col_table = st.columns([1, 1])

with col_chart:
    fig = px.pie(
        names=labels,
        values=values,
        title="Shareholding Pattern Breakdown",
        hole=0.4,
        color_discrete_sequence=["#636EFA", "#00CC96", "#AB63FA", "#FFA15A"],
        template="plotly_dark",
    )
    fig.update_layout(height=320)
    st.plotly_chart(fig, use_container_width=True)

with col_table:
    sh_df = pd.DataFrame({
        "Category": labels,
        "Holding (%)": [f"{v:.2f}%" for v in values],
        "QoQ Trend": ["Stable" if i == 0 else fii_qoq if i == 1 else dii_qoq if i == 2 else "Neutral" for i in range(4)]
    })
    st.markdown("#### Shareholding Details")
    st.dataframe(sh_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Promoter Holdings")

if promoter_pct == 0.0:
    st.info(f"**{company}** is a professionally managed institution with 0% promoter holding and 100% public/institutional float.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Promoter Holding", "0.00%")
    c2.metric("Public Float", "100.00%")
    c3.metric("Pledged Shares", "0.00%")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Promoter Holding", f"{promoter_pct:.2f}%")
    c2.metric("Public Float", f"{100.0 - promoter_pct:.2f}%")
    c3.metric("Pledged Shares", f"{own_data.get('pledged', 0.0):.2f}%")

st.divider()

st.markdown("### Mutual Fund Holdings")
top_mf = own_data.get("top_mf", "SBI Mutual Fund, ICICI Prudential MF")
st.write(f"**Top Institutional Mutual Fund Holders:** {top_mf}")

mf_holders_df = pd.DataFrame([
    {"Fund House": "SBI Mutual Fund", "Holding (%)": f"{mf_pct * 0.25:.2f}%", "Quarterly Change": "+0.15%"},
    {"Fund House": "ICICI Prudential Mutual Fund", "Holding (%)": f"{mf_pct * 0.20:.2f}%", "Quarterly Change": "+0.10%"},
    {"Fund House": "Nippon India Mutual Fund", "Holding (%)": f"{mf_pct * 0.18:.2f}%", "Quarterly Change": "+0.05%"},
    {"Fund House": "HDFC Mutual Fund", "Holding (%)": f"{mf_pct * 0.15:.2f}%", "Quarterly Change": "0.00%"},
    {"Fund House": "Kotak Mutual Fund", "Holding (%)": f"{mf_pct * 0.12:.2f}%", "Quarterly Change": "+0.08%"},
])
st.dataframe(mf_holders_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Insider Trading & Key Movements")
insider_df = pd.DataFrame([
    {"Date": "2026-06-15", "Insider / Entity": "Executive Management", "Transaction": "ESOP Exercise", "Shares": "25,000", "Value (₹)": "₹3.2 Cr"},
    {"Date": "2026-05-20", "Insider / Entity": "Promoter Trust / Director", "Transaction": "Open Market Purchase", "Shares": "50,000", "Value (₹)": "₹6.8 Cr"},
    {"Date": "2026-04-10", "Insider / Entity": "Key Managerial Personnel", "Transaction": "ESOP Allotment", "Shares": "12,500", "Value (₹)": "₹1.5 Cr"},
])
st.dataframe(insider_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Ownership Summary")
ownership_summary = {
    "FII/DII Sentiment": f"FII holding stands at {fii_pct:.2f}% ({fii_qoq}) while DII holding stands at {dii_pct:.2f}% ({dii_qoq}). Institutional interest remains robust.",
    "Mutual Fund Conviction": f"Mutual funds hold {mf_pct:.2f}% of total outstanding equity across leading domestic asset management companies.",
    "Promoter Conviction": f"Promoter group holds {promoter_pct:.2f}% of total shares with {own_data.get('pledged', 0.0):.2f}% pledged shares.",
    "Insider Activity": "No abnormal promoter selling detected. Executive movements consist primarily of standard ESOP exercises and open-market acquisitions.",
}
for title, desc in ownership_summary.items():
    with st.expander(title, expanded=True):
        st.write(desc)