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

st.markdown("### Institutional Ownership")

mh = getattr(ticker, "major_holders", None)
ins_pct = None
inst_pct = None

if mh is not None and isinstance(mh, pd.DataFrame) and not mh.empty:
    try:
        if "Breakdown" in mh.columns and "Value" in mh.columns:
            m_dict = dict(zip(mh["Breakdown"], mh["Value"]))
            ins_pct = m_dict.get("insidersPercentHeld")
            inst_pct = m_dict.get("institutionsPercentHeld")
    except Exception:
        pass

if ins_pct is None and hasattr(ticker, "info") and isinstance(ticker.info, dict):
    ins_pct = ticker.info.get("heldPercentInsiders")
    inst_pct = ticker.info.get("heldPercentInstitutions")

ins_val = (ins_pct * 100) if (ins_pct is not None and not np.isnan(ins_pct)) else None
inst_val = (inst_pct * 100) if (inst_pct is not None and not np.isnan(inst_pct)) else None
public_val = (100.0 - (ins_val or 0.0) - (inst_val or 0.0)) if (ins_val is not None or inst_val is not None) else None

c1, c2, c3 = st.columns(3)
c1.metric("Promoter / Insider %", f"{ins_val:.2f}%" if ins_val is not None else "N/A")
c2.metric("Institutional % Held", f"{inst_val:.2f}%" if inst_val is not None else "N/A")
c3.metric("Public Float %", f"{public_val:.2f}%" if public_val is not None else "N/A")

if ins_val is not None or inst_val is not None:
    st.write("")
    col_chart, col_table = st.columns([1, 1])

    labels = ["Promoters / Insiders", "Institutional Investors", "Public Float & Others"]
    values = [ins_val or 0.0, inst_val or 0.0, max(0.0, public_val or 0.0)]

    with col_chart:
        fig = px.pie(
            names=labels,
            values=values,
            title="Shareholding Breakdown",
            hole=0.4,
            color_discrete_sequence=["#636EFA", "#00CC96", "#FFA15A"],
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