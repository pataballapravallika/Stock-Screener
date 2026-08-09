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

st.title("Ownership Analysis")
st.caption("FII & DII changes, Mutual Fund holdings, Promoter positions, and Insider trading")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

fund = fetch_fundamentals(symbol) or {}
ticker = yf.Ticker(symbol)

st.subheader(f"{fund.get('Company') or symbol} — Ownership Analysis")

sector = fund.get("Sector") or "Technology"
industry = fund.get("Industry") or "IT - Software"
mcap = fund.get("MarketCap")
if not mcap:
    try:
        fi = getattr(ticker, "fast_info", {})
        mc = fi.get("marketCap") or (ticker.info.get("marketCap") if hasattr(ticker, "info") else None)
        if mc:
            mcap = mc / 1e7
    except Exception:
        pass

emp = fund.get("Employees")
if not emp:
    try:
        emp = ticker.info.get("fullTimeEmployees") if hasattr(ticker, "info") else None
    except Exception:
        pass

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sector", sector)
c2.metric("Industry", industry)
c3.metric("Market Cap", f"₹{mcap:,.0f} Cr" if mcap else "N/A")
c4.metric("Employees", f"{emp:,}" if emp else "N/A")

st.divider()

st.markdown("### Official Shareholding Breakdown")

promoter_val = fund.get("Promoter_Pct")
fii_val = fund.get("FII_Pct")
dii_val = fund.get("DII_Pct")
govt_val = fund.get("Govt_Pct")
public_val = fund.get("Public_Pct")
inst_val = fund.get("Institutional_Pct")

if promoter_val is None and symbol == "HDFCBANK.NS":
    promoter_val = 0.00

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Promoter %", f"{promoter_val:.2f}%" if promoter_val is not None else "N/A")
c2.metric("FII %", f"{fii_val:.2f}%" if fii_val is not None else "N/A")
c3.metric("DII %", f"{dii_val:.2f}%" if dii_val is not None else "N/A")
c4.metric("Government %", f"{govt_val:.2f}%" if govt_val is not None else "N/A")
c5.metric("Public & Others %", f"{public_val:.2f}%" if public_val is not None else "N/A")

labels = []
values = []
if promoter_val is not None and promoter_val > 0:
    labels.append("Promoters")
    values.append(promoter_val)
if fii_val is not None and fii_val > 0:
    labels.append("FIIs")
    values.append(fii_val)
if dii_val is not None and dii_val > 0:
    labels.append("DIIs")
    values.append(dii_val)
if govt_val is not None and govt_val > 0:
    labels.append("Government")
    values.append(govt_val)
if public_val is not None and public_val > 0:
    labels.append("Public & Others")
    values.append(public_val)

if values:
    st.write("")
    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        fig = px.pie(
            names=labels,
            values=values,
            title="Shareholding Pattern",
            hole=0.4,
            color_discrete_sequence=["#636EFA", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3"],
            template="plotly_dark",
        )
        fig.update_layout(height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        sh_df = pd.DataFrame({
            "Category": labels,
            "Holding (%)": [f"{v:.2f}%" for v in values]
        })
        st.markdown("#### Shareholding Details")
        st.dataframe(sh_df, use_container_width=True, hide_index=True)

sh_table = fund.get("Shareholding_Table")
if sh_table is not None and isinstance(sh_table, pd.DataFrame) and not sh_table.empty:
    st.write("")
    st.markdown("#### Quarterly Shareholding Pattern Trend")
    st.dataframe(sh_table, use_container_width=True)

st.divider()

st.markdown("### Institutional & Mutual Fund Holders")
try:
    inst_holders = ticker.institutional_holders
    if inst_holders is not None and isinstance(inst_holders, pd.DataFrame) and not inst_holders.empty:
        st.dataframe(inst_holders, use_container_width=True, hide_index=True)
    else:
        st.caption("Institutional holder details unavailable from data provider.")
except Exception:
    st.caption("Institutional holder details unavailable.")

st.divider()

st.markdown("### Mutual Fund Holders")
try:
    mf_holders = ticker.mutualfund_holders
    if mf_holders is not None and isinstance(mf_holders, pd.DataFrame) and not mf_holders.empty:
        st.dataframe(mf_holders, use_container_width=True, hide_index=True)
    else:
        st.caption("Mutual fund holder details unavailable from data provider.")
except Exception:
    st.caption("Mutual fund holder details unavailable.")

st.divider()

st.markdown("### Insider Trading")
try:
    insider = ticker.insider_purchases if hasattr(ticker, "insider_purchases") else None
    if insider is not None and isinstance(insider, pd.DataFrame) and not insider.empty:
        st.dataframe(insider, use_container_width=True, hide_index=True)
    else:
        st.caption("Insider trading details unavailable from data provider.")
except Exception:
    st.caption("Insider trading details unavailable.")

st.divider()

st.markdown("### Ownership Summary")
ownership_summary = {
    "Institutional Conviction": f"Institutional investors hold {inst_val:.2f}%" if inst_val is not None else "Institutional holding data is derived directly from exchange filings and provider feeds.",
    "Promoter Alignment": f"Promoters/insiders hold {ins_val:.2f}%" if ins_val is not None else "Promoter conviction indicates long-term commitment.",
    "Market Liquidity": f"Public float represents {public_val:.2f}%" if public_val is not None else "Public float ensures active secondary market liquidity.",
}
for title, desc in ownership_summary.items():
    with st.expander(title, expanded=True):
        st.write(desc)