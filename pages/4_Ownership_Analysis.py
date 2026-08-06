import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
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

st.title("Ownership Analysis")
st.caption("FII & DII changes, Mutual Fund holdings, Promoter positions, and Insider trading")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=3600)
def load_ownership_data(symbol):
    fund = fetch_fundamentals(symbol) or {}
    return fund

fund = load_ownership_data(symbol)
ticker = yf.Ticker(symbol)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

st.subheader(f"{fund.get('Company') or symbol} — Ownership Analysis")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sector", fund.get("Sector") or "N/A")
c2.metric("Industry", fund.get("Industry") or "N/A")
c3.metric("Market Cap", f"${fund.get('MarketCap', 0)/1e9:.2f}B" if fund.get("MarketCap") else "N/A")
c4.metric("Employees", f"{fund.get('Employees', 0):,}" if fund.get("Employees") else "N/A")

st.divider()

st.markdown("### Institutional Ownership")

inst_data = fund.get("institutionalHoldings") if isinstance(fund, dict) else None
if inst_data is None:
    try:
        inst_data = getattr(ticker, "institutional_holders", None)
    except Exception:
        inst_data = None

if inst_data is not None:
    if isinstance(inst_data, pd.DataFrame) and not inst_data.empty:
        st.dataframe(inst_data.head(10).fillna("N/A"), use_container_width=True, hide_index=True)
    elif isinstance(inst_data, dict):
        fi_pct = inst_data.get("fiimPercentHeld") or inst_data.get("FII") or inst_data.get("institutionalPercent")
        dii_pct = inst_data.get("diimPercentHeld") or inst_data.get("DII")
        mf_pct = inst_data.get("mutualFundPercentHeld") or inst_data.get("MutualFund")

        c1, c2, c3 = st.columns(3)
        c1.metric("FII % Held", f"{fi_pct:.2f}%" if fi_pct else "N/A")
        c2.metric("DII % Held", f"{dii_pct:.2f}%" if dii_pct else "N/A")
        c3.metric("Mutual Fund % Held", f"{mf_pct:.2f}%" if mf_pct else "N/A")

        c4, c5 = st.columns(2)
        c4.metric("FII Change (QoQ)", inst_data.get("fiimChangeQoQ", "N/A"))
        c5.metric("DII Change (QoQ)", inst_data.get("diimChangeQoQ", "N/A"))
else:
    st.caption("Institutional ownership data not available through the data provider.")
    st.info("FII/DII data is typically available for NSE-listed Indian stocks via BSE/NSE filings.")

st.divider()

st.markdown("### Promoter Holdings")
promo_data = fund.get("promoterHoldings") if isinstance(fund, dict) else None
if promo_data is None:
    try:
        promo_data = getattr(ticker, "major_holders", None)
    except Exception:
        promo_data = None

if promo_data is not None:
    if isinstance(promo_data, pd.DataFrame) and not promo_data.empty:
        st.dataframe(promo_data.fillna("N/A"), use_container_width=True, hide_index=True)
    elif isinstance(promo_data, dict):
        c1, c2 = st.columns(2)
        c1.metric("Promoter Holding", f"{promo_data.get('promoterPercent', 0):.2f}%")
        c2.metric("Public Float", f"{promo_data.get('publicFloatPercent', 0):.2f}%")
else:
    st.caption("Promoter holding data not available through the data provider.")

st.divider()

st.markdown("### Insider Trading")
try:
    insider = ticker.insider_purchases if hasattr(ticker, 'insider_purchases') else None
    if insider is not None and isinstance(insider, pd.DataFrame) and not insider.empty:
        st.subheader("Recent Insider Purchases")
        st.dataframe(insider.head(10).fillna("N/A"), use_container_width=True, hide_index=True)
    else:
        st.caption("Insider trading data not available through the data provider.")
except Exception:
    st.caption("Insider trading data not available through the data provider.")

st.divider()

st.markdown("### Mutual Fund Holdings")
mf_data = fund.get("mutualFundHoldings") if isinstance(fund, dict) else None
if mf_data is None:
    try:
        mf_data = getattr(ticker, 'mutualfund_holders', None)
    except Exception:
        mf_data = None

if mf_data is not None:
    if isinstance(mf_data, pd.DataFrame) and not mf_data.empty:
        st.dataframe(mf_data.head(10).fillna("N/A"), use_container_width=True, hide_index=True)
    elif isinstance(mf_data, dict):
        c1, c2 = st.columns(2)
        c1.metric("Top MF Holder", mf_data.get("topHolder", "N/A"))
        c2.metric("MF % Held", f"{mf_data.get('percentHeld', 0):.2f}%")
else:
    st.caption("Mutual fund holding data not available through the data provider.")

st.divider()

st.markdown("### Ownership Summary")
ownership_summary = {
    "FII/DII": "FII (Foreign Institutional Investors) and DII (Domestic Institutional Investors) are key market participants. Rising FII inflows typically indicate foreign confidence, while DII activity reflects domestic institutional sentiment.",
    "Mutual Funds": "Mutual fund holdings indicate institutional confidence. Increasing MF ownership often precedes price appreciation.",
    "Promoter Holdings": "Promoter holding levels signal management confidence. Declining promoter stakes may indicate reduced conviction or potential dilution.",
    "Insider Trading": "Insider buying (especially by promoters and C-suite) is generally a positive signal. Insider selling can indicate various motivations.",
}
for title, desc in ownership_summary.items():
    with st.expander(title):
        st.write(desc)