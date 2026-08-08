import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_utils import get_quarterly_df
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental, safe_float
from scoring.config import DEFAULT_CONFIG, score_category

st.set_page_config(page_title="Sector Analysis", layout="wide")

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

SECTOR_PEERS = {
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
    "Energy": ["RELIANCE.NS"],
    "Automotive": ["TATAMOTORS.NS"],
    "Consumer Goods": ["ITC.NS"],
}

st.title("Sector Analysis")
st.caption("Sector fundamentals, technical strength, and rotation analysis")


def match_peer_group(sec_name: str) -> str:
    sec = (sec_name or "").lower()
    if any(w in sec for w in ["tech", "software", "it"]):
        return "Technology"
    if any(w in sec for w in ["bank", "finan", "credit"]):
        return "Financial Services"
    if any(w in sec for w in ["energy", "refiner", "oil", "gas", "petro"]):
        return "Energy"
    if any(w in sec for w in ["auto", "motor", "vehicle"]):
        return "Automotive"
    if any(w in sec for w in ["consumer", "fmcg", "tobacco"]):
        return "Consumer Goods"
    return "Technology"


company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]


fund = fetch_fundamentals(symbol) or {}

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

raw_sector = fund.get("Sector")
matched_group = match_peer_group(raw_sector or symbol)
display_sector = raw_sector if raw_sector and raw_sector != "Unknown" else matched_group

peer_symbols = SECTOR_PEERS.get(matched_group, list(COMPANIES.values()))

st.subheader(f"{fund.get('Company') or symbol} — Sector: {display_sector}")

st.divider()

st.markdown("### A. Sector Fundamentals")

fundamental_metrics = {}
for ps in peer_symbols:
    try:
        pfund = fetch_fundamentals(ps)
        if pfund and isinstance(pfund, dict):
            roe = pfund.get("ROE")
            roce = pfund.get("ROCE")
            rev_g = pfund.get("Sales_YoY") or pfund.get("Sales_QoQ")
            eps_g = pfund.get("EPS_YoY") or pfund.get("PAT_YoY") or pfund.get("EPS_QoQ")
            de = pfund.get("DebtEquity")
            pe = pfund.get("PE")

            fundamental_metrics[ps] = {
                "ROE (%)": round(roe, 2) if roe is not None else None,
                "ROCE (%)": round(roce, 2) if roce is not None else None,
                "Revenue Growth (%)": round(rev_g, 2) if rev_g is not None else None,
                "EPS Growth (%)": round(eps_g, 2) if eps_g is not None else None,
                "Debt/Equity": round(de, 2) if de is not None else None,
                "P/E": round(pe, 2) if pe is not None else None,
            }
    except Exception:
        pass

if fundamental_metrics:
    fm_df = pd.DataFrame(fundamental_metrics).T
    display_fm = fm_df.copy()
    for col in display_fm.columns:
        display_fm[col] = display_fm[col].apply(
            lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and not pd.isna(v) else "N/A"
        )
    st.dataframe(display_fm, use_container_width=True)

    c1, c2 = st.columns(2)
    metrics_to_chart = ["ROE (%)", "Revenue Growth (%)", "EPS Growth (%)", "ROCE (%)"]
    for idx, metric in enumerate(metrics_to_chart):
        target_col = c1 if idx % 2 == 0 else c2
        vals = []
        labels = []
        for sym_key, mdict in fundamental_metrics.items():
            v = mdict.get(metric)
            if v is not None and not pd.isna(v):
                vals.append(v)
                labels.append(sym_key)
        if vals:
            with target_col:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=labels, y=vals, marker_color="#00CC96"))
                fig.update_layout(height=280, title=metric, yaxis_title="%", template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Sector fundamental data not available.")

st.divider()

st.markdown("### B. Sector Technical Strength")

relative_strength = {}
for ps in peer_symbols:
    try:
        pdf = fetch_prices(ps, period="1y")
        if not pdf.empty and len(pdf) > 1:
            ret = (pdf["Close"].iloc[-1] / pdf["Close"].iloc[0] - 1) * 100
            relative_strength[ps] = round(ret, 2)
    except Exception:
        pass

if relative_strength:
    rs_df = pd.DataFrame({
        "Symbol": list(relative_strength.keys()),
        "1Y Return (%)": list(relative_strength.values()),
    })
    rs_df = rs_df.sort_values("1Y Return (%)", ascending=False)
    st.dataframe(rs_df, use_container_width=True, hide_index=True)

    fig = px.bar(
        rs_df,
        x="Symbol",
        y="1Y Return (%)",
        title="1-Year Relative Price Return (%)",
        color="1Y Return (%)",
        color_continuous_scale="Greens",
        template="plotly_dark",
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### C. Sector Rotation & Performance")

sector_rank_data = []
for sec_group, syms in SECTOR_PEERS.items():
    sec_returns = []
    for ps in syms:
        try:
            pdf = fetch_prices(ps, period="1y")
            if not pdf.empty and len(pdf) > 1:
                ret = (pdf["Close"].iloc[-1] / pdf["Close"].iloc[0] - 1) * 100
                sec_returns.append(ret)
        except Exception:
            pass
    avg_ret = np.mean(sec_returns) if sec_returns else 0.0
    sector_rank_data.append({"Sector": sec_group, "1Y Return (%)": round(avg_ret, 2)})

srd_df = pd.DataFrame(sector_rank_data).sort_values("1Y Return (%)", ascending=False)
srd_df["Rank"] = range(1, len(srd_df) + 1)

st.dataframe(srd_df[["Rank", "Sector", "1Y Return (%)"]], use_container_width=True, hide_index=True)

fig = go.Figure()
fig.add_trace(go.Bar(
    x=srd_df["Sector"],
    y=srd_df["1Y Return (%)"],
    marker_color=["#00CC96" if v >= 0 else "#EF553B" for v in srd_df["1Y Return (%)"]],
))
fig.update_layout(height=380, title="Sector Performance Comparison (1Y)", yaxis_title="1Y Return (%)", template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### Sector Universe Overview")

UNIVERSE = list(COMPANIES.values())


@st.cache_data(ttl=3600)
def load_universe_metadata(tickers):
    rows = []
    for t in tickers:
        try:
            f = fetch_fundamentals(t) or {}
            rows.append({
                "symbol": t,
                "company": f.get("Company") or t,
                "sector": match_peer_group(f.get("Sector")),
                "marketCap": f.get("MarketCap"),
                "ROE": f.get("ROE"),
                "ROCE": f.get("ROCE"),
            })
        except Exception:
            rows.append({"symbol": t, "company": t, "sector": "Unknown"})
    return pd.DataFrame(rows)


meta = load_universe_metadata(UNIVERSE)
available_sectors = sorted(meta["sector"].unique())
selected_sectors = st.multiselect("Select sectors to analyze", available_sectors, default=available_sectors)

if not selected_sectors:
    st.warning("Please select at least one sector.")
    st.stop()

sector_rows = []
sector_details = {}

for sec in selected_sectors:
    members = meta[meta["sector"] == sec]["symbol"].tolist()
    details = []
    returns_1m, returns_3m, returns_6m, returns_12m = [], [], [], []

    for s in members:
        try:
            f = fetch_fundamentals(s) or {}
            pdf = fetch_prices(s, period="1y")
            price = pdf["Close"].iloc[-1] if not pdf.empty else None
            ret_1m, ret_3m, ret_6m, ret_12m = None, None, None, None
            if not pdf.empty and len(pdf) > 20:
                ret_1m = (price / pdf["Close"].iloc[-21] - 1) * 100 if len(pdf) >= 21 else None
                ret_3m = (price / pdf["Close"].iloc[-63] - 1) * 100 if len(pdf) >= 63 else None
                ret_6m = (price / pdf["Close"].iloc[-126] - 1) * 100 if len(pdf) >= 126 else None
                ret_12m = (price / pdf["Close"].iloc[0] - 1) * 100

            if ret_1m: returns_1m.append(ret_1m)
            if ret_3m: returns_3m.append(ret_3m)
            if ret_6m: returns_6m.append(ret_6m)
            if ret_12m: returns_12m.append(ret_12m)

            details.append({
                "Company": f.get("Company") or s,
                "Ticker": s,
                "Price": price,
                "1M (%)": ret_1m,
                "3M (%)": ret_3m,
                "6M (%)": ret_6m,
                "12M (%)": ret_12m,
                "Sales YoY (%)": f.get("Sales_YoY"),
                "PAT YoY (%)": f.get("PAT_YoY"),
                "EPS YoY (%)": f.get("EPS_YoY"),
                "ROE (%)": f.get("ROE"),
                "ROCE (%)": f.get("ROCE"),
            })
        except Exception:
            continue

    sector_rows.append({
        "Sector": sec,
        "Companies": len(members),
        "1M Return (%)": np.mean(returns_1m) if returns_1m else 0.0,
        "3M Return (%)": np.mean(returns_3m) if returns_3m else 0.0,
        "6M Return (%)": np.mean(returns_6m) if returns_6m else 0.0,
        "12M Return (%)": np.mean(returns_12m) if returns_12m else 0.0,
    })
    sector_details[sec] = details

if sector_rows:
    st.subheader("Sector Rankings & Overview")
    sec_df = pd.DataFrame(sector_rows).sort_values("12M Return (%)", ascending=False)
    for col in ["1M Return (%)", "3M Return (%)", "6M Return (%)", "12M Return (%)"]:
        sec_df[col] = sec_df[col].apply(lambda x: f"{x:.2f}%")
    st.dataframe(sec_df, use_container_width=True, hide_index=True)

st.subheader("Sector Constituents")
sel_sec = st.selectbox("Select sector to view constituents", list(sector_details.keys()))
if sel_sec and sel_sec in sector_details:
    c_list = sector_details[sel_sec]
    if c_list:
        cdf = pd.DataFrame(c_list)
        for col in cdf.columns:
            if " (%)" in col:
                cdf[col] = cdf[col].apply(lambda v: f"{v:.2f}%" if v is not None and not pd.isna(v) else "N/A")
            elif col == "Price":
                cdf[col] = cdf[col].apply(lambda v: f"₹{v:,.2f}" if v is not None and not pd.isna(v) else "N/A")
        st.dataframe(cdf, use_container_width=True, hide_index=True)