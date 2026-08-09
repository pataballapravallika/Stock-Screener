import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from data.sector_data import fetch_sector_performance, get_standard_sector, compute_sector_aggregated_metrics, STOCK_SECTOR_MAP

st.set_page_config(page_title="Sector Analysis & Rotation", layout="wide")

COMPANIES = {
    # Banking & Financials
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "State Bank of India": "SBIN.NS",
    "Kotak Mahindra Bank": "KOTAKBANK.NS",
    "Axis Bank": "AXISBANK.NS",
    "Bajaj Finance": "BAJFINANCE.NS",
    # IT & Technology
    "TCS": "TCS.NS",
    "Infosys": "INFY.NS",
    "HCL Technologies": "HCLTECH.NS",
    "Wipro": "WIPRO.NS",
    "LTIMindtree": "LTIM.NS",
    "Tech Mahindra": "TECHM.NS",
    # Automotive
    "Tata Motors": "TATAMOTORS.NS",
    "Mahindra & Mahindra": "M&M.NS",
    "Maruti Suzuki": "MARUTI.NS",
    "Bajaj Auto": "BAJAJ-AUTO.NS",
    "Hero MotoCorp": "HEROMOTOCO.NS",
    # FMCG
    "ITC": "ITC.NS",
    "Hindustan Unilever": "HINDUNILVR.NS",
    "Nestle India": "NESTLEIND.NS",
    "Britannia": "BRITANNIA.NS",
    "Varun Beverages": "VBL.NS",
    # Healthcare
    "Sun Pharma": "SUNPHARMA.NS",
    "Dr Reddy's": "DRREDDY.NS",
    "Cipla": "CIPLA.NS",
    "Apollo Hospitals": "APOLLOHOSP.NS",
    # Energy & Metals
    "Reliance Industries": "RELIANCE.NS",
    "NTPC": "NTPC.NS",
    "Power Grid": "POWERGRID.NS",
    "ONGC": "ONGC.NS",
    "Tata Steel": "TATASTEEL.NS",
    "Hindalco": "HINDALCO.NS",
    "DLF": "DLF.NS",
    "Larsen & Toubro": "LT.NS",
}

# Cached data loaders to eliminate indefinite page loading
@st.cache_data(ttl=1800)
def load_cached_sector_performance():
    return fetch_sector_performance()

@st.cache_data(ttl=1800)
def load_cached_sector_aggregated_metrics(std_sector: str):
    return compute_sector_aggregated_metrics(std_sector)

@st.cache_data(ttl=1800)
def load_cached_peer_metrics(std_sector: str, peer_tuples: list):
    peer_symbols = [sym for _, sym in peer_tuples]
    try:
        batch_prices = yf.download(peer_symbols, period="1y", interval="1d", progress=False, threads=True)["Close"]
    except Exception:
        batch_prices = pd.DataFrame()

    peer_metrics = []
    for p_name, p_sym in peer_tuples:
        pfund = fetch_fundamentals(p_sym) or {}

        p_close = None
        ret_1y = None
        if not batch_prices.empty:
            p_series = batch_prices[p_sym].dropna() if p_sym in batch_prices.columns else pd.Series()
            if not p_series.empty and len(p_series) > 1:
                p_close = float(p_series.iloc[-1])
                p_start = float(p_series.iloc[0])
                if p_start > 0:
                    ret_1y = ((p_close - p_start) / p_start) * 100

        roe = pfund.get("ROE")
        roce = pfund.get("ROCE")
        pe = pfund.get("PE")
        rev_g = pfund.get("Sales_YoY") or pfund.get("Sales_QoQ")
        eps_g = pfund.get("EPS_YoY") or pfund.get("PAT_YoY")
        promoter = pfund.get("Promoter_Pct")
        fii = pfund.get("FII_Pct")
        dii = pfund.get("DII_Pct")

        peer_metrics.append({
            "Company": p_name,
            "Ticker": p_sym,
            "LTP (₹)": round(p_close, 2) if p_close is not None else None,
            "1Y Return (%)": round(ret_1y, 2) if ret_1y is not None else None,
            "P/E": round(pe, 2) if pe is not None else None,
            "ROE (%)": round(roe, 2) if roe is not None else None,
            "ROCE (%)": round(roce, 2) if roce is not None else None,
            "Rev Growth (%)": round(rev_g, 2) if rev_g is not None else None,
            "EPS Growth (%)": round(eps_g, 2) if eps_g is not None else None,
            "Promoter (%)": round(promoter, 2) if promoter is not None else None,
            "FII (%)": round(fii, 2) if fii is not None else None,
            "DII (%)": round(dii, 2) if dii is not None else None,
        })
    return peer_metrics


st.title("Sector Analysis & Rotation Engine")
st.caption("NIFTY Sectoral Indices Performance, Sector Relative Strength (RS vs NIFTY 50), and Peer Fundamentals")

st.divider()

# ============================================================
# SECTION 1: NIFTY SECTOR INDICES & ROTATION LEADERBOARD
# ============================================================
st.markdown("### A. NIFTY Sectoral Indices & Rotation Quadrants")
st.caption("Live relative strength (RS) and momentum across benchmark sector indices")

with st.spinner("Fetching live NIFTY sector index data..."):
    sector_perf_df = load_cached_sector_performance()

if not sector_perf_df.empty:
    col1, col2 = st.columns([1.6, 1])

    with col1:
        st.markdown("##### NIFTY Sector Performance & Relative Strength (vs NIFTY 50)")
        styled_df = sector_perf_df.copy()

        def highlight_quadrant(val):
            if val == "Leading":
                return "background-color: #0e4429; color: #3fb950; font-weight: bold"
            elif val == "Improving":
                return "background-color: #1b4721; color: #7ee787; font-weight: bold"
            elif val == "Weakening":
                return "background-color: #4d2d00; color: #d29922; font-weight: bold"
            else:
                return "background-color: #4c1d1d; color: #f85149; font-weight: bold"

        styler = styled_df.style
        if hasattr(styler, "map"):
            styler = styler.map(highlight_quadrant, subset=["Rotation Quadrant"])
        else:
            styler = styler.applymap(highlight_quadrant, subset=["Rotation Quadrant"])

        st.dataframe(
            styler,
            use_container_width=True,
            hide_index=True,
        )


    with col2:
        st.markdown("##### Sector Rotation Bar Chart (3M RS vs NIFTY 50)")
        fig_rs = px.bar(
            sector_perf_df,
            x="RS vs NIFTY 50",
            y="Sector Index",
            orientation="h",
            color="RS vs NIFTY 50",
            color_continuous_scale="RdYlGn",
            template="plotly_dark",
        )
        fig_rs.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_rs, use_container_width=True)

st.divider()

# ============================================================
# SECTION 2: COMPANY & SECTOR PEER ANALYSIS
# ============================================================
st.markdown("### B. Company & Industry Sector Peer Analysis")

c1, c2 = st.columns([1, 2])
with c1:
    selected_company_name = st.selectbox("Select Sample Company", ["-- Custom Ticker --"] + list(COMPANIES.keys()))
    if selected_company_name == "-- Custom Ticker --":
        custom_input = st.text_input("Enter Any Ticker Symbol (e.g. RELIANCE.NS, TATAPOWER.NS)", value="RELIANCE.NS").strip().upper()
        target_symbol = custom_input if custom_input.endswith(".NS") else f"{custom_input}.NS"
    else:
        target_symbol = COMPANIES[selected_company_name]

target_fund = fetch_fundamentals(target_symbol) or {}
raw_sec = target_fund.get("Sector")
std_sector = get_standard_sector(target_symbol, raw_sec)

with c2:
    st.info(f"**Target Symbol:** `{target_symbol}` | **Standardized Sector:** `{std_sector}` | **Data Source:** `{target_fund.get('fundamentals_source', 'Official Filings')}`")

# Gather peers in this sector from STOCK_SECTOR_MAP
peer_list = []
for sym, sec in STOCK_SECTOR_MAP.items():
    if sec == std_sector:
        name = sym.replace(".NS", "")
        peer_list.append((name, sym))

if target_symbol not in [s for _, s in peer_list]:
    peer_list.insert(0, (target_symbol.replace(".NS", ""), target_symbol))


sec_agg_info = load_cached_sector_aggregated_metrics(std_sector)

st.markdown(f"#### Peer Comparison in Sector: **{std_sector}** ({len(peer_list)} Companies)")

if sec_agg_info:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Reporting Period", sec_agg_info.get("ReportingPeriod", "N/A"), help="Enforced common reporting quarter for all constituents")
    m2.metric("Median Sector P/E", f"{sec_agg_info['MedianPE']:.2f}" if sec_agg_info.get("MedianPE") else "N/A", help="Median P/E ratio across constituent stocks")
    m3.metric("Median Sector ROE", f"{sec_agg_info['MedianROE']:.2f}%" if sec_agg_info.get("MedianROE") else "N/A", help="Median Return on Equity across constituent stocks")
    m4.metric("Sector Breadth (> 200 EMA)", f"{sec_agg_info['BreadthAbove200EMA']:.1f}%", help="Percentage of sector constituents trading above 200 EMA")

st.divider()

peer_metrics = load_cached_peer_metrics(std_sector, peer_list)

if peer_metrics:
    peer_df = pd.DataFrame(peer_metrics)
    st.dataframe(peer_df, use_container_width=True, hide_index=True)

    # Comparative Visualizations
    st.markdown("##### Sector Financial Comparison Visualizer")
    metric_choice = st.selectbox(
        "Select Metric to Compare Across Peers",
        ["1Y Return (%)", "ROE (%)", "ROCE (%)", "Rev Growth (%)", "EPS Growth (%)", "P/E", "Promoter (%)"]
    )

    fig_comp = px.bar(
        peer_df.dropna(subset=[metric_choice]),
        x="Company",
        y=metric_choice,
        text=metric_choice,
        color=metric_choice,
        color_continuous_scale="Blues",
        title=f"{std_sector} — {metric_choice} Peer Ranking",
        template="plotly_dark"
    )
    fig_comp.update_traces(texttemplate='%{text:.2f}', textposition='outside')
    fig_comp.update_layout(height=400)
    st.plotly_chart(fig_comp, use_container_width=True)