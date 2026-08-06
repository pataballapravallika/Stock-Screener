import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_fundamentals import fetch_fundamentals
from analysis.valuation import compute_peg, compute_ev_ebitda

st.set_page_config(page_title="Valuation", layout="wide")

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

PEER_GROUPS = {
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "LT.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "Energy": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS", "GAIL.NS"],
    "Automotive": ["TATAMOTORS.NS", "MAHINDRA.NS", "MARUTI.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS"],
    "Consumer Goods": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "DABUR.NS"],
}

st.title("Valuation")
st.caption("PE, PEG, EV/EBITDA, and valuation vs peers")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=3600)
def load_valuation_data(symbol):
    fund = fetch_fundamentals(symbol) or {}
    return fund

fund = load_valuation_data(symbol)
ticker = yf.Ticker(symbol)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

st.subheader(f"{fund.get('Company') or symbol} — Valuation Metrics")

c1, c2, c3, c4 = st.columns(4)
c1.metric("P/E Ratio", f"{fund.get('PE', 0):.2f}" if fund.get("PE") else "N/A")
c2.metric("PEG Ratio", f"{compute_peg(fund.get('PE'), fund.get('EarningsGrowth')):.2f}" if fund.get("PE") and fund.get("EarningsGrowth") and fund["EarningsGrowth"] > 0 else "N/A")
c3.metric("EV/EBITDA", f"{compute_ev_ebitda(fund.get('EnterpriseValue'), fund.get('EBITDA')):.2f}" if fund.get("EnterpriseValue") and fund.get("EBITDA") and fund["EBITDA"] != 0 else "N/A")
c4.metric("Market Cap", f"${fund.get('MarketCap', 0)/1e9:.2f}B" if fund.get("MarketCap") else "N/A")

st.divider()

st.markdown("### Valuation vs Peers")

sector = fund.get("Sector") or "Unknown"
peer_symbols = []
for sec, syms in PEER_GROUPS.items():
    if sector.lower() in sec.lower() or sec.lower() in sector.lower():
        peer_symbols = syms
        break

if not peer_symbols:
    peer_symbols = [s for s in COMPANIES.values() if s != symbol]

peer_data = []
for ps in peer_symbols[:5]:
    try:
        pfund = fetch_fundamentals(ps)
        if pfund and isinstance(pfund, dict):
            peer_data.append({
                "Symbol": ps,
                "Company": pfund.get("Company", ps),
                "PE": pfund.get("PE", np.nan),
                "PEG": compute_peg(pfund.get("PE"), pfund.get("EarningsGrowth")) if pfund.get("PE") and pfund.get("EarningsGrowth") else np.nan,
                "EV/EBITDA": compute_ev_ebitda(pfund.get("EnterpriseValue"), pfund.get("EBITDA")) if pfund.get("EnterpriseValue") and pfund.get("EBITDA") else np.nan,
                "ROE": pfund.get("ROE", np.nan),
                "Debt/Equity": pfund.get("DebtEquity", np.nan),
            })
    except Exception:
        pass

peer_df = pd.DataFrame(peer_data)
if not peer_df.empty:
    display_df = peer_df.copy()
    for col in ["PE", "PEG", "EV/EBITDA", "ROE", "Debt/Equity"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and not pd.isna(v) else "N/A")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    fig = px.scatter(
        peer_df, x="PE", y="ROE",
        size="Market Cap" if "Market Cap" in peer_df.columns else None,
        hover_name="Company",
        title="PE vs ROE (Peer Comparison)",
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Peer comparison data not available.")

st.divider()

st.markdown("### Valuation Summary")
pe = fund.get("PE")
peg = compute_peg(fund.get("PE"), fund.get("EarningsGrowth")) if fund.get("PE") and fund.get("EarningsGrowth") else None
ev_ebitda = compute_ev_ebitda(fund.get("EnterpriseValue"), fund.get("EBITDA")) if fund.get("EnterpriseValue") and fund.get("EBITDA") else None

valuation_notes = []
if pe is not None:
    if pe < 15:
        valuation_notes.append("P/E is below 15 — potentially undervalued relative to market averages.")
    elif pe < 30:
        valuation_notes.append("P/E is in the moderate range — fairly valued by market standards.")
    else:
        valuation_notes.append("P/E is above 30 — trading at a premium; growth expectations are high.")

if peg is not None:
    if peg < 1.0:
        valuation_notes.append("PEG below 1.0 — may be undervalued relative to growth rate.")
    elif peg < 2.0:
        valuation_notes.append("PEG between 1.0–2.0 — reasonably valued for the growth rate.")
    else:
        valuation_notes.append("PEG above 2.0 — may be overvalued relative to growth rate.")

if ev_ebitda is not None:
    if ev_ebitda < 10:
        valuation_notes.append("EV/EBITDA below 10x — potentially attractive on an enterprise value basis.")
    elif ev_ebitda < 20:
        valuation_notes.append("EV/EBITDA between 10–20x — in line with typical market multiples.")
    else:
        valuation_notes.append("EV/EBITDA above 20x — trading at a premium on enterprise value.")

if valuation_notes:
    for note in valuation_notes:
        st.write(f"- {note}")
else:
    st.caption("Insufficient valuation data for analysis.")