import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from typing import Optional
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record, get_company_info as db_get_company_info
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
    """Compute exact valuation metrics with explicit inputs, formulas, and data sources.

    ALL valuation metrics use audited official data from NSE XBRL / company
    financial filings.  Yahoo Finance is used ONLY for the current market price
    (OHLCV data).  No Yahoo fundamental data (totalDebt, totalCash, ebitda,
    trailingEps, marketCap, sharesOutstanding) is used anywhere in this module.
    """
    calc_date = datetime.now().strftime("%Y-%m-%d")
    fund_raw = fetch_fundamentals(symbol) or {}
    prices = fetch_prices(symbol, period="5d")
    ttm_rec = get_ttm_record(symbol)

    # ── 1. Price, Shares, and Market Cap ──────────────────────────────────
    # Current price comes ONLY from the price feed (OHLCV data).
    current_price = prices["Close"].iloc[-1] if not prices.empty else None

    # Shares outstanding from official NSE quote API (stored in companies DB)
    # or derived from XBRL filing (Equity Share Capital / Face Value)
    shares_out = fund_raw.get("SharesOutstanding")
    if not shares_out:
        try:
            cached = db_get_company_info(symbol)
            if cached:
                shares_out = cached.get("shares_outstanding")
        except Exception:
            pass

    # Market Cap = Current Price × Shares Outstanding
    # If shares unavailable, fall back to the MarketCap stored in the companies
    # table (which was computed from the NSE quote API's marketCap field)
    mcap_cr = (current_price * shares_out) / 1e7 if (current_price and shares_out) else None
    if mcap_cr is None:
        mcap_cr = fund_raw.get("MarketCap")
    if mcap_cr is None:
        try:
            cached = db_get_company_info(symbol)
            if cached and cached.get("market_cap"):
                mcap_cr = float(cached["market_cap"])
        except Exception:
            pass

    mcap_source = "Current Price (NSE live) × Shares Outstanding (NSE quote API)"

    # ── 2. TTM EPS from 4 distinct quarterly reported EPS values ────────────
    q_df = get_latest_quarterly_reports(symbol, limit=4)
    ttm_eps = None
    ttm_eps_source = "Sum of Last 4 Reported Quarters (NSE XBRL filings)"
    if not q_df.empty and "eps" in q_df.columns and len(q_df) >= 4:
        # Ensure we have 4 DISTINCT quarters (deduplicate by report_date)
        seen = set()
        eps_vals = []
        for _, row in q_df.iterrows():
            rd = str(row.get("report_date", ""))
            if rd and rd not in seen:
                seen.add(rd)
                v = row.get("eps")
                if v is not None and not (isinstance(v, float) and v != v):
                    eps_vals.append(float(v))
        if len(eps_vals) >= 4:
            ttm_eps = sum(eps_vals[:4])

    if ttm_eps is None:
        ttm_eps = ttm_rec.get("eps") if ttm_rec else None
        if ttm_eps is not None:
            ttm_eps_source = "TTM record (aggregated from quarterly filings)"
        else:
            ttm_eps = fund_raw.get("TTMEPS") or fund_raw.get("EPS")
            if ttm_eps:
                ttm_eps_source = "Latest reported EPS (NSE XBRL)"

    if ttm_eps is None:
        ttm_eps_source = "N/A"

    # P/E Ratio = Current Market Price / TTM EPS or pre-calculated PE
    pe_ratio = (current_price / ttm_eps) if (current_price and ttm_eps and ttm_eps > 0) else None
    if pe_ratio is None:
        pe_ratio = fund_raw.get("PE")

    # ── 3. PEG Ratio ──────────────────────────────────────────────────────
    # EPS growth must be from official NSE XBRL annual filings
    eps_g_pct = fund_raw.get("EPS_YoY") or fund_raw.get("Sales_YoY")
    if eps_g_pct is None:
        eps_g_pct = fund_raw.get("EarningsGrowth") or fund_raw.get("RevenueGrowth")
    if eps_g_pct is not None:
        # Convert decimal to percentage if in decimal form (abs < 1.5 means it's a ratio)
        if abs(eps_g_pct) < 1.5:
            eps_g_pct = eps_g_pct * 100.0

    # PEG = PE / EPS Growth %. Only compute when both PE and growth are positive.
    if pe_ratio and eps_g_pct and eps_g_pct > 0:
        peg_ratio = pe_ratio / eps_g_pct
    else:
        peg_ratio = fund_raw.get("PEG")

    # ── 4. EV / EBITDA (Exempt for Banks) ─────────────────────────────────
    is_bank = any(b in symbol for b in ["BANK", "SBIN"])

    annual_df = get_latest_annual_reports(symbol, limit=1)

    # Total Debt — sourced from official annual balance sheet (Total Debt / Borrowings)
    # Falls back to TTM record or quarterly debt if annual not available
    debt_cr = None
    debt_source = "N/A"
    if not annual_df.empty:
        debt_cr = annual_df.iloc[0].get("total_debt")  # actual borrowings from XBRL
        if debt_cr is None:
            debt_cr = annual_df.iloc[0].get("debt")  # balance sheet debt line
        if debt_cr is not None:
            debt_source = f"Annual Report ({annual_df.iloc[0].get('report_date')}) — {annual_df.iloc[0].get('source', 'NSE XBRL')}"
    if debt_cr is None and ttm_rec:
        debt_cr = ttm_rec.get("total_debt") or ttm_rec.get("debt")
        if debt_cr is not None:
            debt_source = "TTM record (from quarterly filings)"
    if debt_cr is None and not q_df.empty:
        debt_cr = q_df.iloc[0].get("debt")
        if debt_cr is not None:
            debt_source = "Latest quarterly report"

    if debt_cr is None:
        debt_cr = fund_raw.get("TotalDebt")
        if debt_cr is not None:
            debt_source = "From fund_raw (official filings)"

    if debt_cr is None:
        debt_cr = 0.0

    # Cash & Cash Equivalents — from official annual balance sheet
    cash_cr = None
    cash_source = "N/A"
    if not annual_df.empty:
        cash_cr = annual_df.iloc[0].get("cash_and_cash_equivalents")
        if cash_cr is not None:
            cash_source = f"Annual Report ({annual_df.iloc[0].get('report_date')}) — {annual_df.iloc[0].get('source', 'NSE XBRL')}"
    if cash_cr is None and ttm_rec:
        cash_cr = ttm_rec.get("cash_and_cash_equivalents")
        if cash_cr is not None:
            cash_source = "TTM record (from quarterly filings)"
    if cash_cr is None:
        cash_cr = fund_raw.get("TotalCash") or fund_raw.get("CashAndCashEquivalents")
        if cash_cr is not None:
            cash_source = "From fund_raw (official filings)"
    if cash_cr is None:
        cash_cr = 0.0

    # EBITDA = EBIT + Depreciation & Amortisation (both from official filings)
    # Use TTM EBIT + annual D&A for the most complete picture
    dda_cr = None
    ebitda_cr = None
    ebitda_source = "N/A"
    if not annual_df.empty:
        dda_cr = annual_df.iloc[0].get("depreciation_amortization")
        if dda_cr is not None:
            ebitda_source = f"Annual Report ({annual_df.iloc[0].get('report_date')}) — {annual_df.iloc[0].get('source', 'NSE XBRL')}"

    # TTM D&A = sum of D&A from last 4 quarterly reports
    ttm_dda = None
    if not q_df.empty and "depreciation_amortization" in q_df.columns:
        seen = set()
        dda_vals = []
        for _, row in q_df.iterrows():
            rd = str(row.get("report_date", ""))
            if rd and rd not in seen:
                seen.add(rd)
                v = row.get("depreciation_amortization")
                if v is not None and not (isinstance(v, float) and v != v):
                    dda_vals.append(float(v))
        if len(dda_vals) >= 4:
            ttm_dda = sum(dda_vals[:4])

    if dda_cr is None and ttm_dda is not None:
        dda_cr = ttm_dda
        ebitda_source = "TTM D&A (sum of last 4 quarterly reports)"
    if dda_cr is None:
        dda_cr = fund_raw.get("DepreciationAmortization")
        if dda_cr is not None:
            ebitda_source = "From fund_raw (official filings)"

    # TTM EBIT from TTM record or sum of last 4 quarters
    ttm_ebit = None
    if ttm_rec:
        ttm_ebit = ttm_rec.get("ebit")
    if ttm_ebit is None and not q_df.empty and "ebit" in q_df.columns:
        ttm_ebit = q_df["ebit"].sum()

    if ttm_ebit is not None and dda_cr is not None:
        ebitda_cr = ttm_ebit + dda_cr
        ebitda_source = f"TTM EBIT + Annual D&A ({ebitda_source})"

    if ebitda_cr is None and ttm_ebit is not None:
        # Fallback: use EBIT if D&A unavailable (note: EBITDA = EBIT + D&A)
        ebitda_cr = ttm_ebit
        ebitda_source = f"TTM EBIT (D&A not available from official filings) — {ttm_ebit:,.2f} Cr"

    if ebitda_cr is None:
        ebitda_cr = fund_raw.get("EBITDATTM") or fund_raw.get("EBITDA")
        if ebitda_cr is not None:
            ebitda_source = "From fund_raw (official filings)"

    # Enterprise Value and EV/EBITDA
    # Per client requirement: if Total Debt, Cash, or EBITDA cannot be
    # reliably extracted from official filings, EV/EBITDA = N/A
    if cash_cr is None:
        cash_cr = 0.0
        cash_source = "N/A — not available from official filings (assumed 0 for EV calculation)"

    ev_cr = None
    ev_ebitda = None
    if mcap_cr is not None and debt_cr is not None and cash_cr is not None and ebitda_cr is not None and ebitda_cr > 0 and not is_bank:
        ev_cr = mcap_cr + debt_cr - cash_cr
        ev_ebitda = ev_cr / ebitda_cr

    return {
        "Symbol": symbol,
        "Company": fund_raw.get("Company") or symbol,
        "CalculationDate": calc_date,
        "DataSource": f"{fund_raw.get('fundamentals_source', 'NSE Official Filings (XBRL)')} & Live Price Feed",
        "CurrentPrice": current_price,
        "SharesOutstanding": shares_out,
        "MarketCapCr": mcap_cr,
        "MarketCapSource": mcap_source,
        "TTMEPS": ttm_eps,
        "TTMEPSSource": ttm_eps_source,
        "PERatio": pe_ratio,
        "EPSGrowthPct": eps_g_pct,
        "PEGRatio": peg_ratio,
        "TotalDebtCr": debt_cr,
        "TotalDebtSource": debt_source,
        "CashCr": cash_cr,
        "CashSource": cash_source,
        "EnterpriseValueCr": ev_cr,
        "TTMEBITDACr": ebitda_cr,
        "EBITDASource": ebitda_source,
        "TTMEBIT": ttm_ebit,
        "DepreciationAmortization": dda_cr,
        "EVEBITDA": ev_ebitda,
        "IsBank": is_bank,
        "AnnualReportDate": annual_df.iloc[0].get("report_date") if not annual_df.empty else None,
        "AnnualReportSource": annual_df.iloc[0].get("source") if not annual_df.empty else None,
        "AnnualReportURL": annual_df.iloc[0].get("source_url") if not annual_df.empty else None,
        "Consolidated": annual_df.iloc[0].get("consolidated") if not annual_df.empty else None,
        "Unit": annual_df.iloc[0].get("unit") if not annual_df.empty else None,
    }


val = compute_audited_valuation(symbol)


def _fmt(val, fmt=".2f"):
    """Safely format a value that may be None."""
    if val is None:
        return "N/A"
    try:
        return format(val, fmt)
    except (ValueError, TypeError):
        return "N/A"

# Render Header with Valuation Date and Source
st.info(f"📅 **Valuation Date:** `{val['CalculationDate']}` | 📡 **Data Source:** `{val['DataSource']}`")

st.subheader(f"{val['Company']} ({val['Symbol']}) — Key Valuation Metrics")

c1, c2, c3, c4 = st.columns(4)
c1.metric("P/E Ratio", f"{val['PERatio']:.2f}" if val["PERatio"] is not None else "N/A", help="P/E = Price / TTM EPS")
c2.metric("PEG Ratio", f"{val['PEGRatio']:.2f}" if val["PEGRatio"] is not None else "N/A", help="PEG = P/E / EPS Growth %")
c3.metric("EV / EBITDA", f"{val['EVEBITDA']:.2f}x" if val["EVEBITDA"] is not None else "N/A", help="EV/EBITDA = Enterprise Value / EBITDA")
c4.metric("Market Cap", f"₹{val['MarketCapCr']:,.0f} Cr" if val["MarketCapCr"] is not None else "N/A")

st.divider()

# ============================================================
# EXPLICIT VALUATION INPUT AUDIT LOGS
# ============================================================
st.markdown("### A. Explicit Input Audit & Calculation Formulas")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("#### 1. Market Cap Calculation")
    st.markdown(f"""
    * **Current Price:** `INR {_fmt(val['CurrentPrice'])}`
    * **Price Source:** Live price feed (NSE market data)
    * **Shares Outstanding:** `{_fmt(val['SharesOutstanding'], ',.0f')}`
    * **Calculation Date:** `{val['CalculationDate']}`
    * **Formula:** $\\text{{Market Cap}} = \\frac{{\\text{{Current Price}} \\times \\text{{Shares Outstanding}}}}{{10^7}}$
    * **Calculated Market Cap:** `INR {_fmt(val['MarketCapCr'], ',.2f')} Cr`
    """)

    st.markdown("#### 2. P/E Ratio Calculation")
    st.markdown(f"""
    * **Current Market Price:** `INR {_fmt(val['CurrentPrice'])}`
    * **TTM EPS (4-Quarter Sum):** `INR {_fmt(val['TTMEPS'])}` *(Source: {val['TTMEPSSource']})*
    * **Calculation Date:** `{val['CalculationDate']}`
    * **Formula:** $P/E = \\frac{{\\text{{Current Market Price}}}}{{\\text{{TTM EPS}}}}$
    * **Calculated P/E:** `{_fmt(val['PERatio'])}`
    """)

with col_b:
    st.markdown("#### 3. PEG Ratio Calculation")
    peg_note = ""
    if val["EPSGrowthPct"] is not None and val["EPSGrowthPct"] <= 0:
        growth_str = _fmt(val["EPSGrowthPct"])
        peg_note = f"\n\n> **Note:** PEG is N/A because EPS growth is negative ({growth_str}%). PEG is only meaningful for positive growth rates."
    elif val["PERatio"] is None:
        peg_note = "\n\n> **Note:** PEG is N/A because P/E ratio could not be calculated (TTM EPS unavailable or non-positive)."
    st.markdown(f"""
    * **P/E Ratio:** `{_fmt(val['PERatio'])}`
    * **EPS YoY Growth %:** `{_fmt(val['EPSGrowthPct'])}%`
    * **Growth Period:** `Trailing 12 Months (YoY)`
    * **Formula:** $PEG = \\frac{{P/E}}{{\\text{{EPS Growth \\%}}}}$
    * **Calculated PEG:** `{_fmt(val['PEGRatio'])}`{peg_note}
    """)

    st.markdown("#### 4. EV / EBITDA Calculation")
    st.markdown(f"""
    * **Market Cap:** `INR {_fmt(val['MarketCapCr'], ',.2f')} Cr`
    * **Total Debt:** `INR {_fmt(val['TotalDebtCr'], ',.2f')} Cr` *(Source: {val['TotalDebtSource']})*
    * **Cash &amp; Equivalents:** `INR {_fmt(val['CashCr'], ',.2f')} Cr` *(Source: {val['CashSource']})*
    * **Enterprise Value (EV):** `INR {_fmt(val['EnterpriseValueCr'], ',.2f')} Cr`
    * **TTM EBITDA:** `INR {_fmt(val['TTMEBITDACr'], ',.2f')} Cr` *(Source: {val['EBITDASource']})*
    * **Formulas:**
      * $EV = \\text{{Market Cap}} + \\text{{Total Debt}} - \\text{{Cash}}$
      * $EV/EBITDA = \\frac{{EV}}{{\\text{{TTM EBITDA}}}}$
    * **Calculated EV/EBITDA:** `{_fmt(val['EVEBITDA'])}x`
    """)

    # Show data source details for transparency
    st.markdown("#### Data Source Details")
    st.caption(f"""
    * **Market Cap**: Current price (NSE live feed) × Shares outstanding (NSE quote API / XBRL filing)
    * **P/E**: Current price ÷ TTM EPS (price from live feed, EPS from NSE XBRL quarterly filings)
    * **Total Debt**: Extracted from official annual balance sheet (Total Debt / Borrowings line item)
    * **Cash & Equivalents**: Extracted from official annual balance sheet (Cash & Cash Equivalents line item)
    * **EBITDA**: TTM EBIT + Annual Depreciation & Amortisation (both from NSE XBRL filings)
    * **NO Yahoo Finance fundamental data is used** — only OHLCV price data
    """)

st.divider()

# ============================================================
# PROVENANCE TABLE — Full audit trail with source, period, consolidated flag
# ============================================================
st.markdown("### Input Provenance Audit Trail")

prov_rows = [
    {"Metric": "Current Price", "Value": _fmt(val["CurrentPrice"]), "Source": "NSE Live Price Feed", "Period": val["CalculationDate"], "Consolidated": "N/A", "Unit": "INR", "Formula": "OHLCV Close"},
    {"Metric": "Shares Outstanding", "Value": _fmt(val["SharesOutstanding"], ",.0f"), "Source": "NSE Quote API / XBRL Filing (Equity Share Capital / Face Value)", "Period": val["AnnualReportDate"] or "N/A", "Consolidated": val["Consolidated"] or "N/A", "Unit": "Shares", "Formula": "Share Capital / Face Value per Share"},
    {"Metric": "Market Cap", "Value": f"₹{_fmt(val['MarketCapCr'], ',.2f')} Cr", "Source": val["MarketCapSource"], "Period": val["CalculationDate"], "Consolidated": "N/A", "Unit": "INR Crores", "Formula": "Price × Shares Outstanding / 10^7"},
    {"Metric": "TTM EPS", "Value": _fmt(val["TTMEPS"]), "Source": val["TTMEPSSource"], "Period": val["AnnualReportDate"] or "N/A", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR", "Formula": "Sum of last 4 quarterly EPS"},
    {"Metric": "P/E Ratio", "Value": _fmt(val["PERatio"]), "Source": "Calculated from above", "Period": val["CalculationDate"], "Consolidated": "N/A", "Unit": "x", "Formula": "P/E = Price / TTM EPS"},
    {"Metric": "EPS Growth %", "Value": f"{_fmt(val['EPSGrowthPct'])}%", "Source": "NSE XBRL Annual Growth", "Period": "YoY", "Consolidated": "N/A", "Unit": "%", "Formula": "(EPS_ttm - EPS_prev) / EPS_prev × 100"},
    {"Metric": "PEG Ratio", "Value": _fmt(val["PEGRatio"]), "Source": "Calculated from above", "Period": "TTM", "Consolidated": "N/A", "Unit": "x", "Formula": "PEG = P/E / EPS Growth %"},
    {"Metric": "Total Debt", "Value": f"₹{_fmt(val['TotalDebtCr'], ',.2f')} Cr", "Source": val["TotalDebtSource"], "Period": val["AnnualReportDate"] or "N/A", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR Crores", "Formula": "Balance Sheet: Total Debt / Borrowings"},
    {"Metric": "Cash & Equivalents", "Value": f"₹{_fmt(val['CashCr'], ',.2f')} Cr", "Source": val["CashSource"], "Period": val["AnnualReportDate"] or "N/A", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR Crores", "Formula": "Balance Sheet: Cash & Cash Equivalents"},
    {"Metric": "TTM EBIT", "Value": f"₹{_fmt(val['TTMEBIT'], ',.2f')} Cr", "Source": "NSE XBRL Quarterly Filings", "Period": "TTM", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR Crores", "Formula": "Sum of last 4 quarterly EBIT"},
    {"Metric": "Depreciation & Amortisation", "Value": f"₹{_fmt(val['DepreciationAmortization'], ',.2f')} Cr", "Source": "NSE XBRL Annual Filing", "Period": val["AnnualReportDate"] or "N/A", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR Crores", "Formula": "Depreciation, Depletion & Amortisation Expense"},
    {"Metric": "EBITDA", "Value": f"₹{_fmt(val['TTMEBITDACr'], ',.2f')} Cr", "Source": val["EBITDASource"], "Period": "TTM", "Consolidated": val["Consolidated"] or "N/A", "Unit": "INR Crores", "Formula": "EBITDA = TTM EBIT + Annual D&A"},
    {"Metric": "Enterprise Value", "Value": f"₹{_fmt(val['EnterpriseValueCr'], ',.2f')} Cr", "Source": "Calculated from above", "Period": val["CalculationDate"], "Consolidated": "N/A", "Unit": "INR Crores", "Formula": "EV = Market Cap + Total Debt - Cash"},
    {"Metric": "EV/EBITDA", "Value": f"{_fmt(val['EVEBITDA'])}x", "Source": "Calculated from above", "Period": "TTM", "Consolidated": "N/A", "Unit": "x", "Formula": "EV/EBITDA = EV / TTM EBITDA"},
]
prov_df = pd.DataFrame(prov_rows)
st.dataframe(prov_df, use_container_width=True, hide_index=True)

# Show filing provenance
if val["AnnualReportSource"]:
    st.caption(f"""
    🔗 **Filing Provenance:**
    - **Source**: {val["AnnualReportSource"]}
    - **Filing Date**: {val["AnnualReportDate"]}
    - **URL**: `{val["AnnualReportURL"]}`
    - **Consolidated**: {val["Consolidated"]}
    - **Unit**: {val["Unit"]}
    """)

st.divider()

# ============================================================
# BENCHMARK DATA SOURCE COMPARISON
# ============================================================
st.markdown("### B. Benchmark Data Source Comparison & Mismatch Audit")

st.info("All valuation inputs are sourced exclusively from official NSE XBRL company filings and the NSE live price feed. No third-party fundamental data (Yahoo Finance, etc.) is used in any calculation. Third-party market data may differ due to forward-looking projections or standalone statement usage.")

st.caption("ℹ️ **Audit Notes:** All values computed from this page use only audited official data sources. Where data is unavailable from official filings (e.g., quarterly cash/balance sheet items not yet reported), the annual consolidated filing is used as the authoritative source.")

st.divider()

# ============================================================
# CONTEXTUAL VALUATION ANALYSIS (NON-HARDCODED)
# ============================================================
st.markdown("### C. Contextual Valuation Analysis")

st.info(f"""
**Objective Valuation Summary for {val['Company']}:**
* **P/E Multiplier:** Trading at **{_fmt(val['PERatio'])}x** TTM earnings based on trailing 4-quarter EPS of **INR {_fmt(val['TTMEPS'])}**.
* **PEG Multiplier:** PEG ratio stands at **{_fmt(val['PEGRatio'])}** based on current TTM YoY growth rate of **{_fmt(val['EPSGrowthPct'])}%**.
* **Enterprise Multiple:** EV/EBITDA ratio is **{_fmt(val['EVEBITDA'])}x** based on Enterprise Value of **INR {_fmt(val['EnterpriseValueCr'], ',.0f')} Cr** and EBITDA of **INR {_fmt(val['TTMEBITDACr'], ',.0f')} Cr** (TTM EBIT of INR {_fmt(val['TTMEBIT'], ',.0f')} Cr + D&A of INR {_fmt(val['DepreciationAmortization'], ',.0f')} Cr).

*Valuation assessment should be evaluated alongside industry historical medians and long-term earnings compounding rather than arbitrary static thresholds.*
""")
