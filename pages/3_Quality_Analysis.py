import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_utils import get_quarterly_df
from fundamentals.growth import calculate_growth_metrics, calculate_balance_sheet_ratios, calculate_cashflow_ratios
from fundamentals.ratios import safe_float, compute_roe, compute_roa, compute_roce, compute_debt_equity, compute_opm, compute_npm
from fundamentals.altman import compute_altman_z
from fundamentals.piotroski import compute_piotroski_f_score
from fundamentals.banking import compute_banking_metrics

st.set_page_config(page_title="Quality Analysis", layout="wide")

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

st.title("Quality Analysis")
st.caption("ROE, ROCE, ROA, Debt/Equity, Free Cashflow, Piotroski F Score, Altman Z Score, and banking metrics")

from data.ui_helpers import render_official_data_header

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=3600)
def load_quality_data(symbol):
    fund = fetch_fundamentals(symbol) or {}
    q_fund = get_quarterly_df(fund)
    return fund, q_fund

fund, q_fund = load_quality_data(symbol)

render_official_data_header(fund)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

sector = fund.get("Sector") or "Unknown"
is_bank = any(b.lower() in sector.lower() for b in {"Financial Services", "Banking", "Finance", "Insurance"})

st.subheader(f"{fund.get('Company') or symbol} — Quality Analysis")
st.caption(f"Sector: {sector}")

st.divider()

if is_bank:
    st.markdown("### Banking Quality Metrics")
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
    bmet = compute_banking_metrics(bank_data, {})
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("CASA Ratio", f"{bmet.get('CASA_Ratio', 0)*100:.1f}%" if bmet.get("CASA_Ratio") else "N/A")
    c2.metric("NIM", f"{bmet.get('NIM', 0)*100:.2f}%" if bmet.get("NIM") else "N/A")
    c3.metric("GNPA", f"{bmet.get('GNPA', 0)*100:.1f}%" if bmet.get("GNPA") else "N/A")
    c4.metric("NNPA", f"{bmet.get('NNPA', 0)*100:.1f}%" if bmet.get("NNPA") else "N/A")
    c5.metric("CAR", f"{bmet.get('CAR', 0)*100:.1f}%" if bmet.get("CAR") else "N/A")

    c6, c7, c8 = st.columns(3)
    c6.metric("NIIM", f"{bmet.get('NIIM', 0)*100:.2f}%" if bmet.get("NIIM") else "N/A")
    c7.metric("PCR", f"{bmet.get('PCR', 0):.2f}" if bmet.get("PCR") else "N/A")
    c8.metric("ROA", f"{bmet.get('ROA', 0)*100:.2f}%" if bmet.get("ROA") else "N/A")

    st.divider()

    st.markdown("### Piotroski F Score")
    fscore_result = compute_piotroski_f_score(
        current_income={"Net_Income": fund.get("NetIncome")},
        previous_income={},
        current_balance={
            "Total_Assets": fund.get("TotalAssets"),
            "Stockholders_Equity": fund.get("TotalStockholderEquity"),
            "Current_Assets": fund.get("CurrentAssets"),
            "Current_Liabilities": fund.get("CurrentLiabilities"),
            "Common_Shares_Outstanding": fund.get("SharesOutstanding"),
        },
        previous_balance={},
        current_cashflow={"Operating_Cash_Flow": fund.get("OperatingCashFlow")},
    )
    st.metric("Piotroski F Score", f"{fscore_result['score']}/9")
    st.progress(fscore_result['score'] / 9)

    st.markdown("### Altman Z Score")
    altman = compute_altman_z(
        working_capital=fund.get("WorkingCapital"),
        total_assets=fund.get("TotalAssets"),
        retained_earnings=fund.get("RetainedEarnings"),
        ebit=fund.get("EBIT"),
        market_value_equity=fund.get("MarketCap"),
        total_liabilities=fund.get("TotalLiabilities"),
        sales=fund.get("Revenue"),
    )
    st.metric("Altman Z Score", f"{altman['value']:.2f}" if altman and altman.get("value") else "N/A")
    if altman and altman.get("value"):
        if altman["value"] > 3.0:
            st.success("Safe Zone (Z > 3.0)")
        elif altman["value"] > 1.8:
            st.warning("Grey Zone (1.8 < Z < 3.0)")
        else:
            st.error("Distress Zone (Z < 1.8)")

else:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("ROE", f"{safe_float(fund.get('ROE'))*100:.2f}%" if fund.get("ROE") else "N/A")
    c2.metric("ROCE", f"{safe_float(fund.get('ROCE'))*100:.2f}%" if fund.get("ROCE") else "N/A")
    c3.metric("ROA", f"{safe_float(fund.get('ROA'))*100:.2f}%" if fund.get("ROA") else "N/A")
    c4.metric("Debt/Equity", f"{safe_float(fund.get('DebtEquity')):.2f}" if fund.get("DebtEquity") else "N/A")
    c5.metric("Operating Cash Flow", f"₹{fund.get('OperatingCashFlow', 0)/1e3:.1f}Cr" if fund.get("OperatingCashFlow") else "N/A")

    st.divider()

    c6, c7, c8 = st.columns(3)
    c6.metric("Free Cash Flow", f"₹{fund.get('FreeCashFlow', 0)/1e3:.1f}Cr" if fund.get("FreeCashFlow") else "N/A")
    c7.metric("FCF Margin", f"{safe_float(fund.get('FreeCashFlow'))/safe_float(fund.get('Revenue'))*100:.1f}%" if fund.get("FreeCashFlow") and fund.get("Revenue") and fund["Revenue"] != 0 else "N/A")
    c8.metric("Revenue", f"₹{fund.get('Revenue', 0)/1e3:.1f}Cr" if fund.get("Revenue") else "N/A")

    st.divider()

    st.markdown("### Piotroski F Score")
    fscore_result = compute_piotroski_f_score(
        current_income={"Net_Income": fund.get("NetIncome")},
        previous_income={},
        current_balance={
            "Total_Assets": fund.get("TotalAssets"),
            "Stockholders_Equity": fund.get("TotalStockholderEquity"),
            "Current_Assets": fund.get("CurrentAssets"),
            "Current_Liabilities": fund.get("CurrentLiabilities"),
            "Common_Shares_Outstanding": fund.get("SharesOutstanding"),
        },
        previous_balance={},
        current_cashflow={"Operating_Cash_Flow": fund.get("OperatingCashFlow")},
    )
    st.metric("Piotroski F Score", f"{fscore_result['score']}/9")
    st.progress(fscore_result['score'] / 9)
    for sig, val in fscore_result.get("signals", {}).items():
        st.write(f"- {sig}: {'Pass' if val else 'Fail'}")

    st.divider()

    st.markdown("### Altman Z Score")
    altman = compute_altman_z(
        working_capital=fund.get("WorkingCapital"),
        total_assets=fund.get("TotalAssets"),
        retained_earnings=fund.get("RetainedEarnings"),
        ebit=fund.get("EBIT"),
        market_value_equity=fund.get("MarketCap"),
        total_liabilities=fund.get("TotalLiabilities"),
        sales=fund.get("Revenue"),
    )
    st.metric("Altman Z Score", f"{altman['value']:.2f}" if altman and altman.get("value") else "N/A")
    if altman and altman.get("value"):
        if altman["value"] > 3.0:
            st.success("Safe Zone (Z > 3.0)")
        elif altman["value"] > 1.8:
            st.warning("Grey Zone (1.8 < Z < 3.0)")
        else:
            st.error("Distress Zone (Z < 1.8)")

st.divider()

st.markdown("### Key Metrics")
def fmt_metric(val, fmt):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return fmt(val)

display_metrics = pd.DataFrame({
    "Metric": [
        "Market Cap", "Trailing P/E", "Forward P/E", "Price / Sales",
        "ROE", "ROCE", "ROA", "Debt / Equity", "Profit Margin",
        "Operating Cash Flow (TTM info)", "Operating Cash Flow (Annual statement)", "Free Cash Flow (Annual statement)",
        "Dividend Yield", "Revenue Growth", "Earnings Growth",
        "Shares Outstanding", "Float Shares", "Promoter %", "Institutional %"
    ],
    "Value": [
        fmt_metric(fund.get("MarketCap"), lambda v: f"${v/1e9:.2f}B" if v > 1e9 else f"${v/1e6:.2f}M"),
        fmt_metric(fund.get("PE"), lambda v: f"{v:.2f}"),
        fmt_metric(fund.get("ForwardPE"), lambda v: f"{v:.2f}"),
        fmt_metric(fund.get("PriceSales"), lambda v: f"{v:.2f}"),
        fmt_metric(fund.get("ROE"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("ROCE"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("ROA"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("DebtEquity"), lambda v: f"{v:.2f}"),
        fmt_metric(fund.get("ProfitMargin"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("OperatingCashFlowTTM"), lambda v: f"${v/1e3:.1f}Cr"),
        fmt_metric(fund.get("OperatingCashFlowAnnual"), lambda v: f"${v/1e3:.1f}Cr"),
        fmt_metric(fund.get("FreeCashFlowAnnual"), lambda v: f"${v/1e3:.1f}Cr"),
        fmt_metric(fund.get("DividendYield"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("RevenueGrowth"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("EarningsGrowth"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("SharesOutstanding"), lambda v: f"{int(v):,}"),
        (lambda fv, so, ins_pct, inst_pct: fmt_metric(
            fv if fv is not None else (
                int(so * (1 - (ins_pct or 0) - (inst_pct or 0))) if so is not None and (ins_pct is not None or inst_pct is not None) else None
            ), lambda v: f"{int(v):,}"))(fund.get("FloatShares"), fund.get("SharesOutstanding"), fund.get("InsidersPercentHeld"), fund.get("InstitutionsPercentHeld")),
        fmt_metric(fund.get("InsidersPercentHeld"), lambda v: f"{v*100:.2f}%"),
        fmt_metric(fund.get("InstitutionsPercentHeld"), lambda v: f"{v*100:.2f}%"),
    ]
})
display_metrics["Value"] = display_metrics["Value"].astype(str)
st.dataframe(display_metrics, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Annual Fundamentals")
income_stmt = fund.get("annual_financials") if isinstance(fund, dict) else None
balance_sheet = fund.get("balance_sheet") if isinstance(fund, dict) else None
cashflow = fund.get("cashflow") if isinstance(fund, dict) else None

annual_growth = {}
if income_stmt is not None and not income_stmt.empty:
    annual_growth = calculate_growth_metrics(income_stmt, quarterly=False)
if annual_growth:
    annual_rows = []
    for key in sorted(annual_growth.keys()):
        val = annual_growth[key]
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            annual_rows.append({"Metric": key, "Value": f"{val:.4f}" if isinstance(val, float) else str(val)})
    if annual_rows:
        st.dataframe(pd.DataFrame(annual_rows), use_container_width=True, hide_index=True)
else:
    st.info("Annual fundamentals unavailable from official filings.")

st.divider()
st.subheader("Quarterly Fundamentals")
q_df = get_quarterly_df(fund)
quarterly_growth = {}
if q_df is not None:
    quarterly_growth = calculate_growth_metrics(q_df, quarterly=True)
elif income_stmt is not None and not income_stmt.empty:
    quarterly_growth = calculate_growth_metrics(income_stmt, quarterly=True)
if quarterly_growth:
    q_rows = []
    for key in sorted(quarterly_growth.keys()):
        val = quarterly_growth[key]
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            display = f"{val*100:.2f}%" if isinstance(val, float) and abs(val) < 10 else f"{val:.4f}"
            q_rows.append({"Metric": key, "Value": display})
    if q_rows:
        st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Quarterly growth data unavailable.")
else:
    st.info("Quarterly fundamentals unavailable from official filings.")

st.subheader("Shareholding Pattern")
sh_tbl = fund.get("Shareholding_Table")
p_pct = fund.get("Promoter_Pct")
f_pct = fund.get("FII_Pct")
d_pct = fund.get("DII_Pct")
pub_pct = fund.get("Public_Pct")

if p_pct is not None or f_pct is not None or d_pct is not None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Promoters", f"{p_pct:.2f}%" if p_pct is not None else "N/A")
    c2.metric("FIIs", f"{f_pct:.2f}%" if f_pct is not None else "N/A")
    c3.metric("DIIs", f"{d_pct:.2f}%" if d_pct is not None else "N/A")
    c4.metric("Public & Others", f"{pub_pct:.2f}%" if pub_pct is not None else "N/A")

if sh_tbl is not None and isinstance(sh_tbl, pd.DataFrame) and not sh_tbl.empty:
    st.dataframe(sh_tbl, use_container_width=True)
elif p_pct is None:
    st.info("Shareholding data unavailable from current provider.")
q_roe = fund.get("quarterly_roe") or {}
q_roa = fund.get("quarterly_roa") or {}
q_de = fund.get("quarterly_debt_equity") or {}
if q_fund is not None and not q_fund.empty:
    periods = list(q_fund.columns)[:4]
    if len(periods) >= 2:
        roe_data = []
        roa_data = []
        de_data = []
        for p in periods:
            p_key = str(p)
            roe_val = q_roe.get(p_key)
            roa_val = q_roa.get(p_key)
            de_val = q_de.get(p_key)
            roe_data.append(roe_val * 100 if roe_val is not None else None)
            roa_data.append(roa_val * 100 if roa_val is not None else None)
            de_data.append(de_val)

        trend_df = pd.DataFrame({
            "Period": [str(p)[:7] for p in periods],
            "ROE": roe_data,
            "ROA": roa_data,
            "Debt/Equity": de_data,
        })

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=trend_df["Period"], y=trend_df["ROE"], mode="lines+markers", name="ROE"))
        fig.add_trace(go.Scatter(x=trend_df["Period"], y=trend_df["ROA"], mode="lines+markers", name="ROA"))
        fig.update_layout(height=350, yaxis_title="Ratio (%)", xaxis_title="Quarter")
        st.plotly_chart(fig, use_container_width=True)