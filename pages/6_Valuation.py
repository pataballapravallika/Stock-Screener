import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_fundamentals import fetch_fundamentals
from analysis.valuation import compute_peg, compute_ev_ebitda
from data.ui_helpers import render_official_data_header

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
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
    "Energy": ["RELIANCE.NS"],
    "Automotive": ["TATAMOTORS.NS"],
    "Consumer Goods": ["ITC.NS"],
}

DEFAULT_VALUATION_DATA = {
    "RELIANCE.NS": {"company": "Reliance Industries", "sector": "Energy", "mcap": 1806314.0, "pe": 19.47, "peg": 1.58, "ev_ebitda": 38.31, "roe": 0.106, "de": 0.77, "pat": 23196.0, "ebit": 47517.0},
    "TCS.NS": {"company": "Tata Consultancy Services", "sector": "Technology", "mcap": 887408.0, "pe": 16.53, "peg": 1.56, "ev_ebitda": 47.83, "roe": 0.265, "de": 0.01, "pat": 13420.0, "ebit": 18500.0},
    "INFY.NS": {"company": "Infosys Limited", "sector": "Technology", "mcap": 475930.0, "pe": 15.30, "peg": 1.88, "ev_ebitda": 41.72, "roe": 0.153, "de": 0.00, "pat": 7776.0, "ebit": 11400.0},
    "HDFCBANK.NS": {"company": "HDFC Bank Limited", "sector": "Financial Services", "mcap": 1126417.0, "pe": 13.82, "peg": 1.45, "ev_ebitda": 44.92, "roe": 0.035, "de": 6.85, "pat": 20400.0, "ebit": 25000.0},
    "ICICIBANK.NS": {"company": "ICICI Bank Limited", "sector": "Financial Services", "mcap": 1019322.0, "pe": 15.72, "peg": 1.57, "ev_ebitda": 51.51, "roe": 0.043, "de": 7.68, "pat": 16220.0, "ebit": 19800.0},
    "SBIN.NS": {"company": "State Bank of India", "sector": "Financial Services", "mcap": 1012783.0, "pe": 10.30, "peg": 0.79, "ev_ebitda": 34.97, "roe": 0.040, "de": 13.53, "pat": 24580.0, "ebit": 28900.0},
    "TATAMOTORS.NS": {"company": "Tata Motors Limited", "sector": "Automotive", "mcap": 345200.0, "pe": 12.50, "peg": 1.15, "ev_ebitda": 18.40, "roe": 0.185, "de": 1.42, "pat": 6900.0, "ebit": 18700.0},
    "ITC.NS": {"company": "ITC Limited", "sector": "Consumer Goods", "mcap": 358468.0, "pe": 19.88, "peg": 1.75, "ev_ebitda": 69.39, "roe": 0.062, "de": 0.29, "pat": 4508.0, "ebit": 5160.0},
    "WIPRO.NS": {"company": "Wipro Limited", "sector": "Technology", "mcap": 185513.0, "pe": 13.82, "peg": 1.38, "ev_ebitda": 42.79, "roe": 0.142, "de": 0.12, "pat": 3356.0, "ebit": 4330.0},
    "HCLTECH.NS": {"company": "HCL Technologies Limited", "sector": "Technology", "mcap": 367064.0, "pe": 19.84, "peg": 1.98, "ev_ebitda": 60.42, "roe": 0.062, "de": 0.55, "pat": 4625.0, "ebit": 6070.0},
}

st.title("Valuation")
st.caption("PE, PEG, EV/EBITDA, and valuation vs peers")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]


def pd_isna(val):
    return val is None or (isinstance(val, float) and np.isnan(val))


def extract_valuation_metrics(fund: dict, symbol: str = None) -> dict:
    if not isinstance(fund, dict):
        fund = {}

    sym = symbol or fund.get("Symbol") or fund.get("ticker")
    defaults = DEFAULT_VALUATION_DATA.get(sym, {})

    mcap = fund.get("MarketCap") or fund.get("marketCap") or defaults.get("mcap")
    pat = fund.get("PAT") or defaults.get("pat")
    ebit = fund.get("EBIT") or defaults.get("ebit")
    de = fund.get("DebtEquity") if fund.get("DebtEquity") is not None else defaults.get("de", 0.0)
    roe = fund.get("ROE") if fund.get("ROE") is not None else defaults.get("roe")

    pe = fund.get("PE")
    if (pe is None or pd_isna(pe)) and mcap and pat and pat > 0:
        pe = mcap / (pat * 4.0 if pat < 50000 else pat)
    if pe is None or pd_isna(pe):
        pe = defaults.get("pe")

    eps_g = fund.get("EPS_YoY") or fund.get("PAT_YoY") or fund.get("EarningsGrowth") or fund.get("EPS_QoQ") or 0.10
    peg = fund.get("PEG")
    if (peg is None or pd_isna(peg)) and pe and eps_g:
        g_val = eps_g / 100.0 if abs(eps_g) > 1.0 else eps_g
        peg = compute_peg(pe, g_val)
    if peg is None or pd_isna(peg):
        peg = defaults.get("peg")

    ev = mcap + (mcap * (de / 100.0) if de else 0.0) if mcap else None
    ev_ebitda = compute_ev_ebitda(ev, ebit) if ev and ebit else (ev / ebit if ev and ebit and ebit > 0 else None)
    if ev_ebitda is None or pd_isna(ev_ebitda):
        ev_ebitda = defaults.get("ev_ebitda")

    return {
        "PE": pe,
        "PEG": peg,
        "EV_EBITDA": ev_ebitda,
        "MarketCap": mcap,
        "ROE": roe,
        "DebtEquity": de,
        "Company": fund.get("Company") or defaults.get("company") or sym,
        "Sector": fund.get("Sector") or defaults.get("sector"),
    }


fund_raw = fetch_fundamentals(symbol) or {}

render_official_data_header(fund_raw)

v_metrics = extract_valuation_metrics(fund_raw, symbol=symbol)

st.subheader(f"{v_metrics.get('Company') or symbol} — Valuation Metrics")

pe_val = v_metrics.get("PE")
peg_val = v_metrics.get("PEG")
ev_val = v_metrics.get("EV_EBITDA")
mcap_val = v_metrics.get("MarketCap")

c1, c2, c3, c4 = st.columns(4)
c1.metric("P/E Ratio", f"{pe_val:.2f}" if pe_val and not pd_isna(pe_val) else "N/A")
c2.metric("PEG Ratio", f"{peg_val:.2f}" if peg_val and not pd_isna(peg_val) else "N/A")
c3.metric("EV/EBITDA", f"{ev_val:.2f}x" if ev_val and not pd_isna(ev_val) else "N/A")
c4.metric("Market Cap", f"₹{mcap_val:,.0f} Cr" if mcap_val and not pd_isna(mcap_val) else "N/A")

st.divider()

st.markdown("### Valuation vs Peers")

sector = v_metrics.get("Sector") or "Unknown"
peer_symbols = []
for sec, syms in PEER_GROUPS.items():
    if sector.lower() in sec.lower() or sec.lower() in sector.lower():
        peer_symbols = syms
        break

if not peer_symbols:
    peer_symbols = list(COMPANIES.values())

peer_data = []
for ps in peer_symbols:
    try:
        pfund = fetch_fundamentals(ps)
        pm = extract_valuation_metrics(pfund, symbol=ps)
        peer_data.append({
            "Symbol": ps,
            "Company": pm.get("Company", ps),
            "PE": pm.get("PE"),
            "PEG": pm.get("PEG"),
            "EV/EBITDA": pm.get("EV_EBITDA"),
            "ROE": pm.get("ROE"),
            "Debt/Equity": pm.get("DebtEquity"),
            "Market Cap (Cr)": pm.get("MarketCap"),
        })
    except Exception:
        pass

peer_df = pd.DataFrame(peer_data)
if not peer_df.empty:
    display_df = peer_df.copy()
    for col in ["PE", "PEG", "EV/EBITDA", "ROE", "Debt/Equity"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda v: f"{v:.2f}" if v is not None and not pd_isna(v) else "N/A"
            )
    if "Market Cap (Cr)" in display_df.columns:
        display_df["Market Cap (Cr)"] = display_df["Market Cap (Cr)"].apply(
            lambda v: f"₹{v:,.0f} Cr" if v is not None and not pd_isna(v) else "N/A"
        )
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    clean_scatter = peer_df.dropna(subset=["PE", "ROE"]).copy()
    if not clean_scatter.empty:
        fig = px.scatter(
            clean_scatter,
            x="PE",
            y="ROE",
            size="Market Cap (Cr)" if "Market Cap (Cr)" in clean_scatter.columns else None,
            hover_name="Company",
            title="PE vs ROE (Peer Comparison)",
            template="plotly_dark",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Peer comparison data not available.")

st.divider()

st.markdown("### Valuation Summary")

valuation_notes = []
if pe_val is not None and not pd_isna(pe_val):
    if pe_val < 15:
        valuation_notes.append(f"P/E is {pe_val:.2f} (below 15) — potentially undervalued relative to market averages.")
    elif pe_val < 30:
        valuation_notes.append(f"P/E is {pe_val:.2f} (between 15–30) — fairly valued by market standards.")
    else:
        valuation_notes.append(f"P/E is {pe_val:.2f} (above 30) — trading at a premium; growth expectations are high.")

if peg_val is not None and not pd_isna(peg_val):
    if peg_val < 1.0:
        valuation_notes.append(f"PEG is {peg_val:.2f} (below 1.0) — attractive valuation relative to growth rate.")
    elif peg_val < 2.0:
        valuation_notes.append(f"PEG is {peg_val:.2f} (between 1.0–2.0) — reasonably valued for current growth rate.")
    else:
        valuation_notes.append(f"PEG is {peg_val:.2f} (above 2.0) — trading at a premium relative to growth rate.")

if ev_val is not None and not pd_isna(ev_val):
    if ev_val < 15:
        valuation_notes.append(f"EV/EBITDA is {ev_val:.2f}x — attractive enterprise multiple.")
    elif ev_val < 30:
        valuation_notes.append(f"EV/EBITDA is {ev_val:.2f}x — moderate enterprise multiple.")
    else:
        valuation_notes.append(f"EV/EBITDA is {ev_val:.2f}x — premium enterprise multiple.")

if valuation_notes:
    for note in valuation_notes:
        st.write(f"- {note}")
else:
    st.caption("Insufficient valuation data for analysis.")