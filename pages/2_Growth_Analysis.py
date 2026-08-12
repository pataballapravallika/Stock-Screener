import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_utils import get_quarterly_df
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental, safe_float
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from scoring.config import DEFAULT_CONFIG, score_category, signal_badge
from data.ui_helpers import render_official_data_header

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

fund = fetch_fundamentals(symbol) or {}
q_fund = get_quarterly_df(fund)

render_official_data_header(fund)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

sector = fund.get("Sector") or "N/A"
industry = fund.get("Industry") or "N/A"

st.subheader(f"{fund.get('Company') or symbol} — Growth Analysis")
st.caption(f"Sector: {sector} | Industry: {industry}")

st.divider()

df_prices = fetch_prices(symbol, period="1y")
latest = {}
if not df_prices.empty:
    df_prices = compute_technical_indicators(df_prices)
    latest = df_prices.iloc[-1]
    tech_result = score_technical(latest)
else:
    tech_result = {"percentage": 0, "signal": "NEUTRAL", "conditions": {}}
is_bank = any(b.lower() in sector.lower() for b in {"Financial Services", "Banking", "Finance", "Insurance"})

eps_g = fund.get("EPS_YoY") if fund.get("EPS_YoY") is not None else fund.get("EPS_QoQ")
rev_g = fund.get("Sales_YoY") if fund.get("Sales_YoY") is not None else fund.get("Sales_QoQ")
pat_g = fund.get("PAT_YoY") if fund.get("PAT_YoY") is not None else fund.get("PAT_QoQ")
roe = fund.get("ROE")
roce = fund.get("ROCE")
roa = fund.get("ROA")
de = fund.get("DebtEquity")

fund_for_scoring = {
    "EPS_Growth": eps_g,
    "Revenue_Growth": rev_g,
    "PAT_Growth": pat_g,
    "ROE": roe,
    "ROCE": roce,
    "ROA": roa,
    "Debt_Equity": de,
    "Piotroski_FScore": fund.get("Piotroski_FScore"),
    "Altman_ZScore": fund.get("Altman_ZScore"),
}

if is_bank:
    bank_data = {
        "NIM": fund.get("NIM"),
        "NII": fund.get("NII"),
        "CASA_Ratio": fund.get("CASA_Ratio"),
        "GNPA": fund.get("GNPA"),
        "NNPA": fund.get("NNPA"),
        "PCR": fund.get("PCR"),
        "Advances_Growth": rev_g,
        "Deposits_Growth": rev_g,
        "CAR": fund.get("CAR"),
        "ROA": roa,
        "ROE": roe,
    }
    bs_res = score_banking(bank_data)
    fund_score_result = {"percentage": bs_res["percentage"], "signal": bs_res["signal"]}
else:
    fund_score_result = score_fundamental(fund_for_scoring)

combined = combined_score(
    technical_result=tech_result,
    fundamental_result=fund_score_result,
    is_bank=is_bank,
)

high_52 = latest.get("52W_High") if not pd.isna(latest.get("52W_High")) else latest.get("High")
close_price = latest.get("Close")
close_price = close_price if close_price is not None and not pd.isna(close_price) else None
price_strength = ((close_price / high_52) * 100) if (close_price and high_52 and high_52 != 0) else 0.0
price_strength_pct = f"{price_strength:.0f}%" if price_strength > 0 else "N/A"

if eps_g is not None and not pd.isna(eps_g):
    eps_growth_str = f"{eps_g*100:.1f}%" if abs(eps_g) <= 1.0 else f"{eps_g:.1f}%"
else:
    eps_growth_str = "N/A"

vol = latest.get("Volume")
vol_ma = latest.get("Volume_MA20")
vol_v = safe_float(vol) if vol is not None else None
vol_ma_v = safe_float(vol_ma) if vol_ma is not None else None
volume_ratio = (vol_v / vol_ma_v) if (vol_v is not None and vol_v > 0 and vol_ma_v is not None and vol_ma_v > 0) else None
if volume_ratio is not None:
    volume_demand = ("A+" if volume_ratio > 2 else "A" if volume_ratio > 1.5 else "B+" if volume_ratio > 1.2 else "B" if volume_ratio > 1.0 else "C")
else:
    volume_demand = "N/A"

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
with c1:
    st.metric("Technical Score", f"{tech_result['percentage']:.0f}/100", score_category(tech_result["percentage"]))
with c2:
    st.metric("Fundamental Score", f"{fund_score_result['percentage']:.0f}/100", score_category(fund_score_result["percentage"]))
with c3:
    st.metric("Price Strength", price_strength_pct, score_category(price_strength))
with c4:
    st.metric("EPS Growth", eps_growth_str, "Positive" if (isinstance(eps_g, (int, float)) and eps_g > 0) else "Neutral")
with c5:
    st.metric("Volume Demand", volume_demand, f"{volume_ratio:.1f}x" if volume_ratio is not None else "")
with c6:
    st.metric("Combined Score", f"{combined['combined_percentage']:.0f}/100", score_category(combined["combined_percentage"]))
with c7:
    st.metric("Signal", combined["combined_signal"], signal_badge(combined["combined_signal"]))

st.divider()

st.markdown("### Fundamental Strength Matrix")
matrix_data = []

def fmt_pct(val):
    if val is None or pd.isna(val):
        return "N/A"
    if abs(val) <= 1.5:
        return f"{val * 100:.2f}%"
    return f"{val:.2f}%"

def add_row(metric, val, threshold, comp=">"):
    if val is None or pd.isna(val):
        score_str = "Pass" if metric in ["Operating Cash Flow", "Piotroski F-Score", "Altman Z-Score"] else "N/A"
        cur_str = "Pass" if metric in ["Piotroski F-Score", "Altman Z-Score"] else "N/A"
        matrix_data.append({"Metric": metric, "Current": cur_str, "Score": score_str, "Status": "Pass" if score_str == "Pass" else "N/A"})
        return

    is_pass = (val > threshold) if comp == ">" else (val < threshold)
    score_str = "Pass" if is_pass else "Fail"
    matrix_data.append({
        "Metric": metric,
        "Current": fmt_pct(val) if "Growth" in metric or metric in ["ROE", "ROCE", "ROA"] else (f"{val:.2f}" if isinstance(val, (int, float)) else str(val)),
        "Score": score_str,
        "Status": "Strong" if is_pass else "Weak"
    })

add_row("EPS Growth", eps_g, 0.05, ">")
add_row("Revenue Growth", rev_g, 0.05, ">")
add_row("PAT Growth", pat_g, 0.05, ">")
add_row("ROE", roe, 0.12, ">")
add_row("ROCE", roce, 0.12, ">")
add_row("ROA", roa, 0.03, ">")
add_row("Debt/Equity", de, 2.0, "<")

pat_val = fund.get("PAT")
matrix_data.append({"Metric": "Operating Cash Flow", "Current": f"₹{pat_val:,.0f} Cr" if pat_val else "N/A", "Score": "N/A", "Status": "N/A"})

pio = fund.get("Piotroski") or fund.get("piotroski_f_score")
pio_str = f"{pio}/9" if isinstance(pio, (int, float)) and 0 <= pio <= 9 else "N/A"
matrix_data.append({"Metric": "Piotroski F-Score", "Current": pio_str, "Score": "N/A", "Status": "N/A"})

alt = fund.get("Altman") or fund.get("altman_z_score")
alt_val = alt.get("value") if isinstance(alt, dict) else (alt if isinstance(alt, (int, float)) else None)
matrix_data.append({"Metric": "Altman Z-Score", "Current": f"{alt_val:.2f}" if isinstance(alt_val, (int, float)) else "N/A", "Score": "N/A", "Status": "N/A"})

matrix_df = pd.DataFrame(matrix_data)
st.dataframe(matrix_df, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Quarterly Metrics & Trend")

if q_fund is not None and not q_fund.empty:
    periods = list(q_fund.columns)
    if len(periods) >= 2:
        latest_q = periods[0]
        prev_q = periods[1]

        def get_row_vals(labels):
            for l in labels:
                if l in q_fund.index:
                    return [safe_float(q_fund.loc[l, col]) for col in q_fund.columns]
            return []

        eps_vals = get_row_vals(["Diluted EPS", "Basic EPS", "EPS"])
        rev_vals = get_row_vals(["Total Revenue", "Revenue", "Sales"])
        pat_vals = get_row_vals(["Net Income", "PAT", "Net Income Common Stockholders"])

        c1, c2, c3 = st.columns(3)

        if eps_vals and len(eps_vals) >= 2:
            latest_eps = eps_vals[0]
            prev_eps = eps_vals[1]
            c1.metric("EPS (Latest Q)", f"₹{latest_eps:.2f}" if latest_eps else "N/A")
            if latest_eps and prev_eps and prev_eps != 0:
                c1.metric("EPS QoQ", f"{(latest_eps - prev_eps) / abs(prev_eps) * 100:+.1f}%")

        if rev_vals and len(rev_vals) >= 2:
            latest_rev = rev_vals[0]
            prev_rev = rev_vals[1]
            c2.metric("Revenue (Latest Q)", f"₹{latest_rev:,.0f} Cr" if latest_rev else "N/A")
            if latest_rev and prev_rev and prev_rev != 0:
                c2.metric("Revenue QoQ", f"{(latest_rev - prev_rev) / abs(prev_rev) * 100:+.1f}%")

        if pat_vals and len(pat_vals) >= 2:
            latest_pat = pat_vals[0]
            prev_pat = pat_vals[1]
            c3.metric("PAT (Latest Q)", f"₹{latest_pat:,.0f} Cr" if latest_pat else "N/A")
            if latest_pat and prev_pat and prev_pat != 0:
                c3.metric("PAT QoQ", f"{(latest_pat - prev_pat) / abs(prev_pat) * 100:+.1f}%")

    st.write("")
    st.markdown("#### Quarterly Trend (Last 4 Quarters)")
    q_trend_rows = []
    for i, p in enumerate(periods[:4]):
        q_trend_rows.append({
            "Quarter": str(p)[:7],
            "EPS": eps_vals[i] if i < len(eps_vals) else None,
            "Revenue (Cr)": rev_vals[i] if i < len(rev_vals) else None,
            "PAT (Cr)": pat_vals[i] if i < len(pat_vals) else None,
        })
    qdf = pd.DataFrame(q_trend_rows)
    if not qdf.empty:
        fig = go.Figure()
        if "Revenue (Cr)" in qdf.columns and qdf["Revenue (Cr)"].notna().any():
            fig.add_trace(go.Bar(x=qdf["Quarter"], y=qdf["Revenue (Cr)"], name="Revenue (Cr)", marker_color="#00CC96"))
        if "PAT (Cr)" in qdf.columns and qdf["PAT (Cr)"].notna().any():
            fig.add_trace(go.Scatter(x=qdf["Quarter"], y=qdf["PAT (Cr)"], name="PAT (Cr)", mode="lines+markers", line=dict(color="#AB63FA", width=3)))
        fig.update_layout(height=380, title="Quarterly Revenue & PAT Trajectory", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### Annual Growth Metrics (Last 3 Years)")

ann_rows = []
rev_val = fund.get("Revenue")
pat_val = fund.get("PAT")
eps_val = fund.get("EPS")

years = ["FY2024", "FY2023", "FY2022"]
for i, yr in enumerate(years):
    rev_growth = fmt_pct(rev_g) if (i == 0 and rev_g is not None) else "N/A"
    pat_growth = fmt_pct(pat_g) if (i == 0 and pat_g is not None) else "N/A"
    eps_growth = fmt_pct(eps_g) if (i == 0 and eps_g is not None) else "N/A"
    ann_rows.append({
        "Year": yr,
        "Revenue (Cr)": f"₹{rev_val:,.0f} Cr" if rev_val else "N/A",
        "Revenue Growth YoY": rev_growth,
        "PAT (Cr)": f"₹{pat_val:,.0f} Cr" if pat_val else "N/A",
        "PAT Growth YoY": pat_growth,
        "EPS": f"₹{eps_val:.2f}" if eps_val else "N/A",
        "EPS Growth YoY": eps_growth,
    })

adf_display = pd.DataFrame(ann_rows)
st.dataframe(adf_display, use_container_width=True, hide_index=True)

st.divider()

st.markdown("### Individual Growth vs Industry Median")
st.caption("Comparing individual company growth metrics against the industry median.")

industry_peers = {
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
    "Energy": ["RELIANCE.NS"],
    "Automotive": ["TATAMOTORS.NS"],
    "Consumer Goods": ["ITC.NS"],
}

peer_symbols = []
for sec_k, syms in industry_peers.items():
    if sector.lower() in sec_k.lower() or sec_k.lower() in sector.lower():
        peer_symbols = syms
        break

if not peer_symbols:
    peer_symbols = list(COMPANIES.values())

peer_growth = {}
for ps in peer_symbols:
    try:
        pfund = fetch_fundamentals(ps)
        if pfund and isinstance(pfund, dict):
            pg = pfund.get("EPS_YoY") or pfund.get("Sales_YoY") or pfund.get("EPS_QoQ")
            if pg is not None and not pd.isna(pg):
                peer_growth[ps] = float(pg * 100 if abs(pg) <= 1.5 else pg)
    except Exception:
        pass

if not peer_growth:
    st.info("No peer growth data available for comparison.")
    st.stop()

median_growth = float(np.median(list(peer_growth.values())))
comp_g_val = float(eps_g * 100 if eps_g and abs(eps_g) <= 1.5 else 0.0)

c1, c2, c3 = st.columns(3)
c1.metric("Company Growth YoY", f"{comp_g_val:.1f}%")
c2.metric("Industry Median Growth YoY", f"{median_growth:.1f}%")
c3.metric("vs Industry Median", f"{comp_g_val - median_growth:+.1f}pp")

fig = go.Figure()
labels = list(peer_growth.keys())
values = list(peer_growth.values())
colors = ["#00CC96" if v >= median_growth else "#EF553B" for v in values]
fig.add_trace(go.Bar(x=labels, y=values, marker_color=colors))
fig.add_hline(y=median_growth, line_dash="dash", line_color="#636EFA", annotation_text=f"Industry Median ({median_growth:.1f}%)")
fig.update_layout(height=360, yaxis_title="Growth %", xaxis_title="Company Ticker", template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)