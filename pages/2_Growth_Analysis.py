import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_utils import get_quarterly_df, quarterly_eps_series, is_quarterly_periods
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from scoring.config import DEFAULT_CONFIG, score_category, signal_badge
from fundamentals.growth import calculate_growth_metrics
from fundamentals.ratios import safe_float, qoq_growth, yoy_growth

st.set_page_config(page_title="Growth Analysis", layout="wide")

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

st.title("Growth Analysis")
st.caption("Quarterly & annual EPS, PAT, Sales, OPM, EBIT, NPM with YoY/QoQ comparison vs industry median")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=3600)
def load_growth_data(symbol):
    fund = fetch_fundamentals(symbol) or {}
    q_fund = get_quarterly_df(fund)
    return fund, q_fund

fund, q_fund = load_growth_data(symbol)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

sector = fund.get("Sector") or "Unknown"
industry = fund.get("Industry") or "Unknown"

st.subheader(f"{fund.get('Company') or symbol} — Growth Analysis")
st.caption(f"Sector: {sector} | Industry: {industry}")

st.divider()

df_prices = fetch_prices(symbol, period="1y")
if not df_prices.empty:
    df_prices = compute_technical_indicators(df_prices)
    latest = df_prices.iloc[-1]
    tech_result = score_technical(latest)
else:
    tech_result = {"percentage": 0, "signal": "N/A", "conditions": {}}

is_bank = any(b.lower() in sector.lower() for b in {"Financial Services", "Banking", "Finance", "Insurance"})
fund_for_scoring = {
    "EPS_Growth": fund.get("EarningsGrowth"),
    "Revenue_Growth": fund.get("RevenueGrowth"),
    "PAT_Growth": None,
    "ROE": fund.get("ROE"),
    "ROCE": fund.get("ROCE"),
    "ROA": fund.get("ROA"),
    "Debt_Equity": fund.get("DebtEquity"),
}
if is_bank:
    bank_data = {
        "NIM": fund.get("NIM"), "NII": fund.get("NII"), "CASA_Ratio": fund.get("CASA_Ratio"),
        "GNPA": fund.get("GNPA"), "NNPA": fund.get("NNPA"), "PCR": fund.get("PCR"),
        "Advances_Growth": fund.get("Advances_Growth"), "Deposits_Growth": fund.get("Deposits_Growth"),
        "CAR": fund.get("CAR"), "ROA": fund.get("ROA"), "ROE": fund.get("ROE"),
    }
    fund_score_result = {"percentage": score_banking(bank_data)["percentage"], "signal": score_banking(bank_data)["signal"]}
else:
    fund_score_result = score_fundamental(fund_for_scoring)

combined = combined_score(
    technical_result=tech_result,
    fundamental_result=fund_score_result,
    is_bank=is_bank,
)

price_strength = (latest["Close"] / latest["52W_High"] * 100) if pd.notna(latest.get("52W_High")) and latest.get("52W_High", 0) != 0 else None
price_strength_pct = f"{price_strength:.0f}%" if price_strength is not None else "N/A"
eps_growth = fund.get("EarningsGrowth")
eps_growth_str = f"{eps_growth*100:.1f}%" if eps_growth is not None else "N/A"
volume_ratio = (latest["Volume"] / latest["Volume_MA20"]) if pd.notna(latest.get("Volume_MA20")) and latest.get("Volume_MA20", 0) > 0 else None
volume_demand = ("A+" if volume_ratio and volume_ratio > 2 else "A" if volume_ratio and volume_ratio > 1.5 else "B+" if volume_ratio and volume_ratio > 1.2 else "B" if volume_ratio and volume_ratio > 1.0 else "C" if volume_ratio is not None else "N/A")

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
with c1:
    st.metric("Technical Score", f"{tech_result['percentage']:.0f}/100", score_category(tech_result["percentage"]))
with c2:
    st.metric("Fundamental Score", f"{fund_score_result['percentage']:.0f}/100", score_category(fund_score_result["percentage"]))
with c3:
    st.metric("Price Strength", price_strength_pct, score_category(price_strength) if price_strength is not None else "N/A")
with c4:
    st.metric("EPS Growth", eps_growth_str, "N/A" if eps_growth is None else ("Positive" if eps_growth > 0 else "Negative"))
with c5:
    st.metric("Volume Demand", volume_demand, f"{volume_ratio:.1f}x" if volume_ratio is not None else "N/A")
with c6:
    st.metric("Combined Score", f"{combined['combined_percentage']:.0f}/100", score_category(combined["combined_percentage"]))
with c7:
    st.metric("Signal", combined["combined_signal"], signal_badge(combined["combined_signal"]))

st.divider()

st.markdown("### Fundamental Strength Matrix")
matrix_data = []
def add_matrix_row(name, current, score_val=None, status=""):
    matrix_data.append({"Metric": name, "Current": f"{current:.2f}" if current is not None else "N/A", "Score": score_val if score_val is not None else "N/A", "Status": status})
def safe_score(fund, key, threshold, comparator=">"):
    val = safe_float(fund.get(key))
    if val is None:
        return "N/A"
    if comparator == ">" and val > threshold:
        return "Pass"
    elif comparator == "<" and val < threshold:
        return "Pass"
    return "Fail"
add_matrix_row("EPS Growth", fund.get("EarningsGrowth"), score_val=safe_score(fund, "EarningsGrowth", 0.10, ">"))
add_matrix_row("Revenue Growth", fund.get("RevenueGrowth"), score_val=safe_score(fund, "RevenueGrowth", 0.10, ">"))
add_matrix_row("PAT Growth", None, score_val="N/A")
add_matrix_row("ROE", fund.get("ROE"), score_val=safe_score(fund, "ROE", 0.15, ">"))
add_matrix_row("ROCE", fund.get("ROCE"), score_val=safe_score(fund, "ROCE", 0.15, ">"))
add_matrix_row("ROA", fund.get("ROA"), score_val=safe_score(fund, "ROA", 0.05, ">"))
add_matrix_row("Debt/Equity", fund.get("DebtEquity"), score_val=safe_score(fund, "DebtEquity", 100, "<"))
add_matrix_row("Operating Cash Flow", fund.get("OperatingCashFlow"), score_val="Pass" if fund.get("OperatingCashFlow") is not None else "N/A")
add_matrix_row("Piotroski F-Score", None, score_val="N/A")
add_matrix_row("Altman Z-Score", None, score_val="N/A")
if matrix_data:
    matrix_df = pd.DataFrame(matrix_data)
    def color_status(val):
        if val == "Pass":
            return "background-color: #d4edda; color: #155724;"
        elif val == "Fail":
            return "background-color: #f8d7da; color: #721c24;"
        return ""
    styled_matrix = matrix_df.style.map(color_status, subset=["Score", "Status"])
    st.dataframe(styled_matrix, use_container_width=True, hide_index=True)

st.divider()

if q_fund is not None and not q_fund.empty:
    periods = list(q_fund.columns)
    if len(periods) >= 2:
        latest_q = periods[0]
        prev_q = periods[1]

        eps_label = None
        for label in ["Diluted EPS", "Basic EPS", "EPS"]:
            if label in q_fund.index:
                eps_label = label
                break

        rev_label = None
        for label in ["Total Revenue", "Revenue", "Sales"]:
            if label in q_fund.index:
                rev_label = label
                break

        ni_label = None
        for label in ["Net Income", "Net Income Common Stockholders"]:
            if label in q_fund.index:
                ni_label = label
                break

        oi_label = None
        for label in ["Operating Income", "EBIT"]:
            if label in q_fund.index:
                oi_label = label
                break

        c1, c2, c3, c4, c5, c6 = st.columns(6)

        if eps_label:
            eps_latest = safe_float(q_fund.loc[eps_label, latest_q]) if latest_q in q_fund.columns else None
            eps_prev = safe_float(q_fund.loc[eps_label, prev_q]) if prev_q in q_fund.columns else None
            c1.metric("EPS (Latest Q)", f"{eps_latest:.2f}" if eps_latest else "N/A")
            if eps_latest and eps_prev and eps_prev != 0:
                c1.metric("EPS QoQ", f"{(eps_latest - eps_prev) / abs(eps_prev) * 100:.1f}%")

        if rev_label:
            rev_latest = safe_float(q_fund.loc[rev_label, latest_q]) if latest_q in q_fund.columns else None
            rev_prev = safe_float(q_fund.loc[rev_label, prev_q]) if prev_q in q_fund.columns else None
            c2.metric("Revenue (Latest Q)", f"₹{rev_latest/1e3:.1f}Cr" if rev_latest else "N/A")
            if rev_latest and rev_prev and rev_prev != 0:
                c2.metric("Revenue QoQ", f"{(rev_latest - rev_prev) / abs(rev_prev) * 100:.1f}%")

        if ni_label:
            ni_latest = safe_float(q_fund.loc[ni_label, latest_q]) if latest_q in q_fund.columns else None
            ni_prev = safe_float(q_fund.loc[ni_label, prev_q]) if prev_q in q_fund.columns else None
            c3.metric("PAT (Latest Q)", f"₹{ni_latest/1e3:.1f}Cr" if ni_latest else "N/A")
            if ni_latest and ni_prev and ni_prev != 0:
                c3.metric("PAT QoQ", f"{(ni_latest - ni_prev) / abs(ni_prev) * 100:.1f}%")

        if oi_label and rev_label:
            oi_latest = safe_float(q_fund.loc[oi_label, latest_q]) if latest_q in q_fund.columns else None
            oi_prev = safe_float(q_fund.loc[oi_label, prev_q]) if prev_q in q_fund.columns else None
            c4.metric("EBIT (Latest Q)", f"₹{oi_latest/1e3:.1f}Cr" if oi_latest else "N/A")
            if oi_latest and oi_prev and oi_prev != 0:
                c4.metric("EBIT QoQ", f"{(oi_latest - oi_prev) / abs(oi_prev) * 100:.1f}%")

        if oi_label and rev_label and oi_latest and rev_latest and rev_latest != 0:
            opm = oi_latest / rev_latest * 100
            opm_prev = (oi_prev / rev_prev * 100) if oi_prev and rev_prev and rev_prev != 0 else None
            c5.metric("OPM (Latest Q)", f"{opm:.1f}%")
            if opm_prev is not None:
                c5.metric("OPM QoQ", f"{opm - opm_prev:+.1f}pp")

        if ni_label and rev_label and ni_latest and rev_latest and rev_latest != 0:
            npm = ni_latest / rev_latest * 100
            npm_prev = (ni_prev / rev_prev * 100) if ni_prev and rev_prev and rev_prev != 0 else None
            c6.metric("NPM (Latest Q)", f"{npm:.1f}%")
            if npm_prev is not None:
                c6.metric("NPM QoQ", f"{npm - npm_prev:+.1f}pp")

    st.divider()

    st.markdown("#### Quarterly Trend (Last 4 Quarters)")
    quarterly_data = {}
    for i, period in enumerate(periods[:4]):
        row = {"Period": str(period)[:7]}
        if eps_label and eps_label in q_fund.index:
            row["EPS"] = safe_float(q_fund.loc[eps_label, period])
        if rev_label and rev_label in q_fund.index:
            row["Revenue"] = safe_float(q_fund.loc[rev_label, period])
        if ni_label and ni_label in q_fund.index:
            row["PAT"] = safe_float(q_fund.loc[ni_label, period])
        if oi_label and oi_label in q_fund.index:
            row["EBIT"] = safe_float(q_fund.loc[oi_label, period])
        quarterly_data[i] = row

    qdf = pd.DataFrame(quarterly_data).T
    if not qdf.empty:
        fig = go.Figure()
        for col in ["EPS", "Revenue", "PAT", "EBIT"]:
            if col in qdf.columns:
                fig.add_trace(go.Scatter(x=qdf["Period"], y=qdf[col], mode="lines+markers", name=col))
        fig.update_layout(height=400, xaxis_title="Quarter", yaxis_title="Value")
        st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### Annual Growth Metrics (Last 3 Years)")

annual_income = fund.get("annual_financials") if isinstance(fund, dict) else None
if annual_income is None:
    try:
        ticker_fallback = yf.Ticker(symbol)
        annual_income = getattr(ticker_fallback, "annual_financials", None)
    except Exception:
        annual_income = None

if annual_income is not None and not annual_income.empty:
    periods_ann = list(annual_income.columns)[:3]
    if len(periods_ann) >= 2:
        ann_metrics = []
        for i, period in enumerate(periods_ann):
            row = {"Year": str(period)[:4] if hasattr(period, 'year') else str(period)}
            if rev_label and rev_label in annual_income.index:
                row["Revenue"] = safe_float(annual_income.loc[rev_label, period])
            if ni_label and ni_label in annual_income.index:
                row["PAT"] = safe_float(annual_income.loc[ni_label, period])
            if oi_label and oi_label in annual_income.index:
                row["EBIT"] = safe_float(annual_income.loc[oi_label, period])
            if eps_label and eps_label in annual_income.index:
                row["EPS"] = safe_float(annual_income.loc[eps_label, period])
            ann_metrics.append(row)

        adf = pd.DataFrame(ann_metrics)
        if not adf.empty and len(adf) >= 2:
            for col in ["Revenue", "PAT", "EBIT", "EPS"]:
                if col in adf.columns:
                    for i in range(1, len(adf)):
                        curr = adf[col].iloc[i]
                        prev = adf[col].iloc[i - 1]
                        if curr is not None and prev is not None and prev != 0:
                            key = f"{col} Growth {adf['Year'].iloc[i]}"
                            adf.loc[i, key] = (curr - prev) / abs(prev) * 100

            adf_display = adf.copy()
            for col in adf_display.columns:
                if col == "Year":
                    continue
                adf_display[col] = adf_display[col].apply(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and not pd.isna(v) else "N/A")
            st.dataframe(adf_display, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Individual Growth vs Industry Median")

st.caption("Comparing individual company growth metrics against the industry median. Industry median is computed from the same sector/industry peers.")

industry_peers = {
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "LT.NS", "MINDTREE.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "Energy": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS", "GAIL.NS"],
    "Automotive": ["TATAMOTORS.NS", "MAHINDRA.NS", "MARUTI.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS"],
    "Consumer Goods": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "DABUR.NS"],
}

peer_symbols = []
for sec, syms in industry_peers.items():
    if sector.lower() in sec.lower() or sec.lower() in sector.lower():
        peer_symbols = syms
        break

if not peer_symbols:
    peer_symbols = list(COMPANIES.values())
    peer_symbols = [s for s in peer_symbols if s != symbol]

peer_growth = {}
for ps in peer_symbols[:5]:
    try:
        pfund = fetch_fundamentals(ps)
        if pfund and isinstance(pfund, dict):
            pq = get_quarterly_df(pfund)
            if pq is not None and not pq.empty:
                peps_label = None
                for lbl in ["Diluted EPS", "Basic EPS", "EPS"]:
                    if lbl in pq.index:
                        peps_label = lbl
                        break
                prev_q = list(pq.columns)[1] if len(pq.columns) > 1 else None
                curr_q = pq.columns[0]
                if peps_label and prev_q and curr_q in pq.columns:
                    curr_eps = safe_float(pq.loc[peps_label, curr_q])
                    prev_eps = safe_float(pq.loc[peps_label, prev_q])
                    if curr_eps and prev_eps and prev_eps != 0:
                        peer_growth[ps] = (curr_eps - prev_eps) / abs(prev_eps) * 100
    except Exception:
        pass

if peer_growth:
    median_growth = np.median(list(peer_growth.values()))
    company_growth = None
    if eps_label and prev_q and latest_q in q_fund.columns and prev_q in q_fund.columns:
        curr_eps = safe_float(q_fund.loc[eps_label, latest_q])
        prev_eps = safe_float(q_fund.loc[eps_label, prev_q])
        if curr_eps and prev_eps and prev_eps != 0:
            company_growth = (curr_eps - prev_eps) / abs(prev_eps) * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("Company EPS QoQ Growth", f"{company_growth:.1f}%" if company_growth else "N/A")
    c2.metric("Industry Median EPS QoQ Growth", f"{median_growth:.1f}%")
    if company_growth is not None:
        c3.metric("vs Industry Median", f"{company_growth - median_growth:+.1f}pp")

    fig = go.Figure()
    all_growths = {**{"Company": company_growth}, **peer_growth}
    labels = list(all_growths.keys())
    values = list(all_growths.values())
    colors = ["green" if v >= median_growth else "red" for v in values]
    fig.add_trace(go.Bar(x=labels, y=values, marker_color=colors))
    fig.add_hline(y=median_growth, line_dash="dash", line_color="blue", annotation_text="Industry Median")
    fig.update_layout(height=350, yaxis_title="EPS QoQ Growth %", xaxis_title="Company")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Peer comparison data not available for this sector.")