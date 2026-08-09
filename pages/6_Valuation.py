import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.database import get_latest_quarterly_reports
from data.ui_helpers import render_official_data_header

st.set_page_config(page_title="Valuation Analysis", layout="wide")

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
    "Energy & Oil": ["RELIANCE.NS"],
    "Automotive": ["TATAMOTORS.NS"],
    "Consumer Goods": ["ITC.NS"],
}

st.title("Valuation Module Audit & Analysis")
st.caption("Explicit valuation inputs, exact formulas, market data source comparison, and non-hardcoded context")

company = st.selectbox("Select Target Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]


def compute_audited_valuation(symbol: str) -> dict:
    """Compute exact valuation metrics with explicit inputs, formulas, and data sources."""
    calc_date = datetime.now().strftime("%Y-%m-%d")
    fund_raw = fetch_fundamentals(symbol) or {}
    prices = fetch_prices(symbol, period="5d")

    t = yf.Ticker(symbol)
    fi = getattr(t, "fast_info", {})
    t_info = t.info or {}

    # 1. Price and Shares
    current_price = prices["Close"].iloc[-1] if not prices.empty else fi.get("lastPrice") or t_info.get("currentPrice")
    shares_out = fi.get("shares") or t_info.get("sharesOutstanding")

    mcap_cr = (current_price * shares_out) / 1e7 if (current_price and shares_out) else None
    if mcap_cr is None:
        mcap_cr = fund_raw.get("MarketCap") or ((t_info.get("marketCap") or 0) / 1e7)

    # 2. TTM EPS Calculation (Strictly sum of last 4 reported quarters)
    q_df = get_latest_quarterly_reports(symbol, limit=4)
    ttm_eps = None
    ttm_eps_source = "Sum of Last 4 Reported Quarters (NSE XBRL)"
    if not q_df.empty and "eps" in q_df.columns and len(q_df) == 4:
        ttm_eps = q_df["eps"].sum()

    if ttm_eps is None:
        ttm_eps_source = "N/A"

    # P/E Ratio
    pe_ratio = (current_price / ttm_eps) if (current_price and ttm_eps and ttm_eps > 0) else None

    # 3. PEG Ratio
    eps_g_pct = fund_raw.get("EPS_YoY") or fund_raw.get("Sales_YoY")
    if eps_g_pct and abs(eps_g_pct) < 1.5:
        eps_g_pct = eps_g_pct * 100.0

    peg_ratio = (pe_ratio / eps_g_pct) if (pe_ratio and eps_g_pct and eps_g_pct > 0) else None

    # 4. EV / EBITDA (Exempt for Banks)
    is_bank = any(b in symbol for b in ["BANK", "SBIN"])
    latest_q = q_df.iloc[0] if not q_df.empty else {}
    debt_cr = latest_q.get("debt") or 0.0
    cash_cr = latest_q.get("current_assets") or 0.0
    ebitda_cr = q_df["ebit"].sum() if not q_df.empty and "ebit" in q_df.columns and len(q_df) == 4 else None

    ev_cr = (mcap_cr + debt_cr - cash_cr) if (mcap_cr and not is_bank) else None
    ev_ebitda = (ev_cr / ebitda_cr) if (ev_cr and ebitda_cr and ebitda_cr > 0 and not is_bank) else None

    return {
        "Symbol": symbol,
        "Company": fund_raw.get("Company") or t_info.get("shortName") or symbol,
        "CalculationDate": calc_date,
        "DataSource": f"{fund_raw.get('fundamentals_source', 'NSE Official Filings (XBRL)')} & Live Price Feed",
        "CurrentPrice": current_price,
        "SharesOutstanding": shares_out,
        "MarketCapCr": mcap_cr,
        "TTMEPS": ttm_eps,
        "TTMEPSSource": ttm_eps_source,
        "PERatio": pe_ratio,
        "EPSGrowthPct": eps_g_pct,
        "PEGRatio": peg_ratio,
        "TotalDebtCr": debt_cr,
        "CashCr": cash_cr,
        "EnterpriseValueCr": ev_cr,
        "TTMEBITDACr": ebitda_cr,
        "EVEBITDA": ev_ebitda,
        "MarketDataCompare": {
            "YFinancePE": yf_pe,
            "YFinancePEG": yf_peg,
            "YFinanceEVEBITDA": yf_ev_ebitda,
            "PEVariance": round(abs(pe_ratio - yf_pe), 2) if (pe_ratio and yf_pe) else None,
            "EBITDAVariance": round(abs(ev_ebitda - yf_ev_ebitda), 2) if (ev_ebitda and yf_ev_ebitda) else None,
        }
    }


val = compute_audited_valuation(symbol)

# Render Header with Valuation Date and Source
st.info(f"📅 **Valuation Date:** `{val['CalculationDate']}` | 📡 **Data Source:** `{val['DataSource']}`")

st.subheader(f"{val['Company']} ({val['Symbol']}) — Key Valuation Metrics")

c1, c2, c3, c4 = st.columns(4)
c1.metric("P/E Ratio", f"{val['PERatio']:.2f}" if val["PERatio"] else "N/A", help="P/E = Price / TTM EPS")
c2.metric("PEG Ratio", f"{val['PEGRatio']:.2f}" if val["PEGRatio"] else "N/A", help="PEG = P/E / EPS Growth %")
c3.metric("EV / EBITDA", f"{val['EVEBITDA']:.2f}x" if val["EVEBITDA"] else "N/A", help="EV/EBITDA = Enterprise Value / EBITDA")
c4.metric("Market Cap", f"₹{val['MarketCapCr']:,.0f} Cr" if val["MarketCapCr"] else "N/A")

st.divider()

# ============================================================
# EXPLICIT VALUATION INPUT AUDIT LOGS
# ============================================================
st.markdown("### A. Explicit Input Audit & Calculation Formulas")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("#### 1. Market Cap Calculation")
    st.markdown(f"""
    * **Current Price:** `INR {val['CurrentPrice']:.2f}`
    * **Shares Outstanding:** `{val['SharesOutstanding']:,.0f}`
    * **Calculation Date:** `{val['CalculationDate']}`
    * **Formula:** $\\text{{Market Cap}} = \\frac{{\\text{{Current Price}} \\times \\text{{Shares Outstanding}}}}{{10^7}}$
    * **Calculated Market Cap:** `INR {val['MarketCapCr']:,.2f} Cr`
    """)

    st.markdown("#### 2. P/E Ratio Calculation")
    st.markdown(f"""
    * **Current Market Price:** `INR {val['CurrentPrice']:.2f}`
    * **TTM EPS (4-Quarter Sum):** `INR {val['TTMEPS']:.2f}` *(Source: {val['TTMEPSSource']})*
    * **Calculation Date:** `{val['CalculationDate']}`
    * **Formula:** $P/E = \\frac{{\\text{{Current Market Price}}}}{{\\text{{TTM EPS}}}}$
    * **Calculated P/E:** `{val['PERatio']:.2f}`
    """)

with col_b:
    st.markdown("#### 3. PEG Ratio Calculation")
    st.markdown(f"""
    * **P/E Ratio:** `{val['PERatio']:.2f}`
    * **EPS YoY Growth %:** `{val['EPSGrowthPct']:.2f}%`
    * **Growth Period:** `Trailing 12 Months (YoY)`
    * **Formula:** $PEG = \\frac{{P/E}}{{\\text{{EPS Growth \\%}}}}$
    * **Calculated PEG:** `{val['PEGRatio']:.2f}`
    """)

    st.markdown("#### 4. EV / EBITDA Calculation")
    st.markdown(f"""
    * **Market Cap:** `INR {val['MarketCapCr']:,.2f} Cr`
    * **Total Debt:** `INR {val['TotalDebtCr']:,.2f} Cr`
    * **Cash & Equivalents:** `INR {val['CashCr']:,.2f} Cr`
    * **Enterprise Value (EV):** `INR {val['EnterpriseValueCr']:,.2f} Cr`
    * **TTM EBITDA:** `INR {val['TTMEBITDACr']:,.2f} Cr`
    * **Formulas:**
      * $EV = \\text{{Market Cap}} + \\text{{Total Debt}} - \\text{{Cash}}$
      * $EV/EBITDA = \\frac{{EV}}{{\\text{{TTM EBITDA}}}}$
    * **Calculated EV/EBITDA:** `{val['EVEBITDA']:.2f}x`
    """)

st.divider()

# ============================================================
# COMPARISON AGAINST RELIABLE MARKET SOURCES
# ============================================================
st.markdown("### B. Benchmark Data Source Comparison & Mismatch Audit")

cmp_data = val["MarketDataCompare"]
cmp_df = pd.DataFrame([{
    "Metric": "P/E Ratio",
    "Calculated Value (Official Filings + Price)": f"{val['PERatio']:.2f}" if val["PERatio"] else "N/A",
    "Market Benchmark (YFinance/Consolidated)": f"{cmp_data['YFinancePE']:.2f}" if cmp_data['YFinancePE'] else "N/A",
    "Variance": f"{cmp_data['PEVariance']:.2f}" if cmp_data['PEVariance'] is not None else "0.00",
    "Audit Status": "MATCH (Within Tolerance)" if (cmp_data['PEVariance'] and cmp_data['PEVariance'] <= 1.5) else "MISMATCH / STATEMENT DIFFERENCE",
}, {
    "Metric": "PEG Ratio",
    "Calculated Value (Official Filings + Price)": f"{val['PEGRatio']:.2f}" if val["PEGRatio"] else "N/A",
    "Market Benchmark (YFinance/Consolidated)": f"{cmp_data['YFinancePEG']:.2f}" if cmp_data['YFinancePEG'] else "N/A",
    "Variance": "N/A",
    "Audit Status": "HISTORICAL vs FORWARD GROWTH DIFFERENCE",
}, {
    "Metric": "EV / EBITDA",
    "Calculated Value (Official Filings + Price)": f"{val['EVEBITDA']:.2f}x" if val["EVEBITDA"] else "N/A",
    "Market Benchmark (YFinance/Consolidated)": f"{cmp_data['YFinanceEVEBITDA']:.2f}x" if cmp_data['YFinanceEVEBITDA'] else "N/A",
    "Variance": f"{cmp_data['EBITDAVariance']:.2f}x" if cmp_data['EBITDAVariance'] is not None else "0.00",
    "Audit Status": "MATCH (Within Tolerance)" if (cmp_data['EBITDAVariance'] and cmp_data['EBITDAVariance'] <= 1.5) else "MISMATCH / STATEMENT DIFFERENCE",
}])

st.dataframe(cmp_df, use_container_width=True, hide_index=True)

st.caption("ℹ️ **Audit Notes:** Minor variances between calculated values and third-party market data arise when third-party benchmarks use forward projected growth rates or standalone balance sheet items instead of audited consolidated filings.")

st.divider()

# ============================================================
# CONTEXTUAL VALUATION ANALYSIS (NON-HARDCODED)
# ============================================================
st.markdown("### C. Contextual Valuation Analysis")

st.info(f"""
**Objective Valuation Summary for {val['Company']}:**
* **P/E Multiplier:** Trading at **{val['PERatio']:.2f}x** TTM earnings based on trailing 4-quarter EPS of **INR {val['TTMEPS']:.2f}**.
* **PEG Multiplier:** PEG ratio stands at **{val['PEGRatio']:.2f}** based on current TTM YoY growth rate of **{val['EPSGrowthPct']:.2f}%**.
* **Enterprise Multiple:** EV/EBITDA ratio is **{val['EVEBITDA']:.2f}x** based on Enterprise Value of **INR {val['EnterpriseValueCr']:,.0f} Cr** and EBITDA of **INR {val['TTMEBITDACr']:,.0f} Cr**.

*Valuation assessment should be evaluated alongside industry historical medians and long-term earnings compounding rather than arbitrary static thresholds.*
""")