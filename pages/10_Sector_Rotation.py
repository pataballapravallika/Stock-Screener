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
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
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
    "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "LT.NS", "MINDTREE.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "Energy": ["RELIANCE.NS", "ONGC.NS", "IOC.NS", "BPCL.NS", "GAIL.NS"],
    "Automotive": ["TATAMOTORS.NS", "MAHINDRA.NS", "MARUTI.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS"],
    "Consumer Goods": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "DABUR.NS"],
}

st.title("Sector Analysis")
st.caption("Sector fundamentals, technical strength, and rotation analysis")

company = st.selectbox("Company", list(COMPANIES.keys()))
symbol = COMPANIES[company]

@st.cache_data(ttl=3600)
def load_sector_data(symbol):
    fund = fetch_fundamentals(symbol) or {}
    sector = fund.get("Sector") or "Unknown"
    return fund, sector

fund, sector = load_sector_data(symbol)

if not fund:
    st.error("Unable to retrieve fundamentals for this ticker.")
    st.stop()

st.subheader(f"{fund.get('Company') or symbol} — Sector: {sector}")

st.divider()

st.markdown("### A. Sector Fundamentals")

peer_symbols = SECTOR_PEERS.get(sector, [s for s in COMPANIES.values() if s != symbol])

fundamental_metrics = {}
for ps in peer_symbols[:5]:
    try:
        pfund = fetch_fundamentals(ps)
        if pfund and isinstance(pfund, dict):
            fundamental_metrics[ps] = {
                "ROE": pfund.get("ROE"),
                "ROCE": pfund.get("ROCE"),
                "Revenue Growth": pfund.get("RevenueGrowth"),
                "EPS Growth": pfund.get("EarningsGrowth"),
                "Debt/Equity": pfund.get("DebtEquity"),
                "P/E": pfund.get("PE"),
            }
    except Exception:
        pass

if fundamental_metrics:
    fm_df = pd.DataFrame(fundamental_metrics).T
    display_fm = fm_df.copy()
    for col in display_fm.columns:
        display_fm[col] = display_fm[col].apply(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) and not pd.isna(v) else str(v) if v is not None else "N/A")
    st.dataframe(display_fm, use_container_width=True)

    for metric in ["ROE", "ROCE", "Revenue Growth", "EPS Growth"]:
        vals = []
        labels = []
        for sym, metrics in fundamental_metrics.items():
            v = metrics.get(metric)
            if v is not None:
                vals.append(float(v) * 100 if metric in ["ROE", "ROCE"] else v * 100)
                labels.append(sym)
        if vals:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=labels, y=vals, marker_color="steelblue"))
            fig.update_layout(height=300, yaxis_title=f"{metric} (%)", xaxis_title="Company")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Sector fundamental data not available.")

st.divider()

st.markdown("### B. Sector Technical Strength")

bench_df = fetch_prices("^CRSLDX", period="1y")

relative_strength = {}
for ps in peer_symbols[:5]:
    try:
        pdf = fetch_prices(ps, period="1y")
        if not pdf.empty and len(pdf) > 1:
            ret = (pdf["Close"].iloc[-1] / pdf["Close"].iloc[0] - 1) * 100
            relative_strength[ps] = ret
    except Exception:
        pass

if relative_strength:
    rs_df = pd.DataFrame({
        "Symbol": list(relative_strength.keys()),
        "1Y Return (%)": list(relative_strength.values()),
    })
    rs_df = rs_df.sort_values("1Y Return (%)", ascending=False)
    st.dataframe(rs_df, use_container_width=True, hide_index=True)

    fig = px.bar(rs_df, x="Symbol", y="1Y Return (%)", title="Relative Strength vs NIFTY 500")
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### C. Sector Rotation")

sector_rank_data = []
for sec, syms in SECTOR_PEERS.items():
    sec_returns = []
    for ps in syms[:3]:
        try:
            pdf = fetch_prices(ps, period="1y")
            if not pdf.empty and len(pdf) > 1:
                ret = (pdf["Close"].iloc[-1] / pdf["Close"].iloc[0] - 1) * 100
                sec_returns.append(ret)
        except Exception:
            pass
    avg_ret = np.mean(sec_returns) if sec_returns else 0
    sector_rank_data.append({"Sector": sec, "1Y Return (%)": avg_ret})

srd_df = pd.DataFrame(sector_rank_data).sort_values("1Y Return (%)", ascending=False)
srd_df["Rank"] = range(1, len(srd_df) + 1)

st.dataframe(srd_df, use_container_width=True, hide_index=True)

fig = go.Figure()
fig.add_trace(go.Bar(
    x=srd_df["Sector"],
    y=srd_df["1Y Return (%)"],
    marker_color=["green" if v > 0 else "red" for v in srd_df["1Y Return (%)"]],
))
fig.update_layout(height=400, yaxis_title="1Y Return (%)", xaxis_title="Sector", showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.markdown("### Sector Breadth")
breadth_metrics = {
    "% Above 50 EMA": f"{np.random.uniform(40, 70):.1f}%",
    "New 52-Week Highs": f"{np.random.randint(5, 25)}",
    "Breakout Counts": f"{np.random.randint(3, 15)}",
    "RSI > 60 Stocks": f"{np.random.uniform(30, 55):.1f}%",
    "ADX > 25 Stocks": f"{np.random.uniform(35, 60):.1f}%",
}
for metric, value in breadth_metrics.items():
    st.write(f"- **{metric}**: {value}")

st.caption("Note: Breadth metrics are illustrative. For real data, connect to a market data API.")

st.divider()

st.markdown("### Sector Universe Overview")

UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "TATAMOTORS.NS", "ITC.NS", "WIPRO.NS", "HCLTECH.NS",
]

@st.cache_data(ttl=60 * 60)
def load_metadata(tickers):
    rows = []
    for t in tickers:
        try:
            f = fetch_fundamentals(t)
            rows.append({
                "symbol": t,
                "company": f.get("Company") or t,
                "sector": f.get("Sector") or "Unknown",
                "marketCap": f.get("MarketCap"),
                "sharesOutstanding": f.get("SharesOutstanding"),
                "floatShares": f.get("FloatShares"),
                "ROE": f.get("ROE"),
                "ROCE": f.get("ROCE"),
            })
        except Exception:
            rows.append({"symbol": t, "company": t, "sector": "Unknown"})
    return pd.DataFrame(rows)

meta = load_metadata(UNIVERSE)
sectors = sorted(meta["sector"].unique())
selected_sectors = st.multiselect("Select sectors to analyze", sectors, default=sectors)
if not selected_sectors:
    st.warning("Please select at least one sector.")
    st.stop()

sector_rows = []
sector_details = {}
for sector in selected_sectors:
    members = meta[meta["sector"] == sector]["symbol"].tolist()
    metrics = []
    returns = []
    details = []
    for s in members:
        try:
            qm_res = {"symbol": s}
            fund = fetch_fundamentals(s)
            q = get_quarterly_df(fund)
            if q is not None and not q.empty:
                periods = list(q.columns)
                if len(periods) >= 4:
                    def extract(label_options):
                        for lab in label_options:
                            if lab in q.index:
                                return [safe_float(q.loc[lab, col]) for col in q.columns]
                        return []
                    revenue = extract(["Total Revenue", "Revenue", "Sales", "Operating Revenue"])
                    eps = extract(["Diluted EPS", "Basic EPS", "EPS"])
                    pat = extract(["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"])
                    qm_res.update({"revenue": revenue, "eps": eps, "pat": pat})
            eps_vals = qm_res.get("eps") or []
            rev_vals = qm_res.get("revenue") or []
            pat_vals = qm_res.get("pat") or []
            def compute_yoy_qoq(values):
                yoy, qoq = [], []
                for idx in range(len(values)):
                    if idx + 4 < len(values) and values[idx] is not None and values[idx + 4] is not None and values[idx + 4] != 0:
                        yoy.append((values[idx] - values[idx + 4]) / abs(values[idx + 4]))
                    else:
                        yoy.append(None)
                    if idx + 1 < len(values) and values[idx] is not None and values[idx + 1] is not None and values[idx + 1] != 0:
                        qoq.append((values[idx] - values[idx + 1]) / abs(values[idx + 1]))
                    else:
                        qoq.append(None)
                return yoy, qoq
            eps_yoy, eps_qoq = compute_yoy_qoq(eps_vals)
            rev_yoy, rev_qoq = compute_yoy_qoq(rev_vals)
            pat_yoy, pat_qoq = compute_yoy_qoq(pat_vals)
            latest_eps_yoy = eps_yoy[0] if eps_yoy and len(eps_yoy) > 0 else None
            latest_rev_yoy = rev_yoy[0] if rev_yoy and len(rev_yoy) > 0 else None
            latest_pat_yoy = pat_yoy[0] if pat_yoy and len(pat_yoy) > 0 else None
            latest_eps_qoq = eps_qoq[0] if eps_qoq and len(eps_qoq) > 0 else None
            latest_rev_qoq = rev_qoq[0] if rev_qoq and len(rev_qoq) > 0 else None
            latest_pat_qoq = pat_qoq[0] if pat_qoq and len(pat_qoq) > 0 else None
            metrics.append({
                "symbol": s, "eps_yoy": latest_eps_yoy, "rev_yoy": latest_rev_yoy, "pat_yoy": latest_pat_yoy,
                "eps_qoq": latest_eps_qoq, "rev_qoq": latest_rev_qoq, "pat_qoq": latest_pat_qoq,
            })
            try:
                df = fetch_prices(s, period="1y")
                if not df.empty:
                    close = df.set_index("Date")["Close"].sort_index()
                    latest_price = close.iloc[-1]
                    def r(days):
                        if len(close) < days + 1:
                            return None
                        return float(latest_price / close.iloc[-(days + 1)] - 1)
                    returns.append({"symbol": s, "1M": r(21), "3M": r(63), "6M": r(126), "12M": r(252), "price": latest_price})
            except Exception:
                pass
            f = meta[meta["symbol"] == s]
            details.append({
                "Company": f["company"].iloc[0] if not f.empty else s,
                "Ticker": s,
                "Price": returns[-1].get("price") if returns else None,
                "1M": returns[-1].get("1M") if returns else None,
                "3M": returns[-1].get("3M") if returns else None,
                "6M": returns[-1].get("6M") if returns else None,
                "12M": returns[-1].get("12M") if returns else None,
                "EPS YoY": latest_eps_yoy, "Sales YoY": latest_rev_yoy, "PAT YoY": latest_pat_yoy,
                "EPS QoQ": latest_eps_qoq, "Sales QoQ": latest_rev_qoq, "PAT QoQ": latest_pat_qoq,
                "ROE": f["ROE"].iloc[0] if not f.empty else None,
                "ROCE": f["ROCE"].iloc[0] if not f.empty else None,
            })
        except Exception:
            continue
    if not metrics:
        continue
    def median_safe(arr):
        vals = [v for v in arr if v is not None]
        return float(np.nanmedian(vals)) if vals else None
    sector_rows.append({
        "Sector": sector, "Companies": len(members),
        "Median EPS Growth YoY": median_safe([m["eps_yoy"] for m in metrics]),
        "Median Sales Growth YoY": median_safe([m["rev_yoy"] for m in metrics]),
        "Median PAT Growth YoY": median_safe([m["pat_yoy"] for m in metrics]),
        "Median EPS Growth QoQ": median_safe([m["eps_qoq"] for m in metrics]),
        "Median Sales Growth QoQ": median_safe([m["rev_qoq"] for m in metrics]),
        "Median PAT Growth QoQ": median_safe([m["pat_qoq"] for m in metrics]),
    })
    returns_df = pd.DataFrame(returns)
    def median_return(col):
        if col in returns_df.columns:
            vals = returns_df[col].dropna().tolist()
            return float(np.nanmedian(vals)) if vals else None
        return None
    sector_rows[-1].update({
        "1M Return": median_return("1M"), "3M Return": median_return("3M"),
        "6M Return": median_return("6M"), "12M Return": median_return("12M"),
    })
    sector_details[sector] = {"members": members, "details": details}

if not sector_rows:
    st.warning("No sector metrics could be calculated from the selected universe.")
    st.stop()

sector_df = pd.DataFrame(sector_rows)

st.subheader("Sector Ranking")
score_metrics = ["Median EPS Growth YoY", "Median Sales Growth YoY", "Median PAT Growth YoY", "1M Return", "3M Return", "6M Return", "12M Return"]
for m in score_metrics:
    if m not in sector_df.columns:
        continue
    vals = sector_df[m].dropna()
    if vals.empty:
        sector_df[m + " Score"] = None
        continue
    ranks = sector_df[m].rank(pct=True)
    sector_df[m + " Score"] = ranks * 100
earn_cols = [c + " Score" for c in ["Median EPS Growth YoY", "Median Sales Growth YoY", "Median PAT Growth YoY"] if c + " Score" in sector_df.columns]
mom_cols = [c + " Score" for c in ["1M Return", "3M Return", "6M Return", "12M Return"] if c + " Score" in sector_df.columns]
if earn_cols:
    sector_df["Earnings Score"] = sector_df[earn_cols].mean(axis=1)
else:
    sector_df["Earnings Score"] = None
if mom_cols:
    sector_df["Momentum Score"] = sector_df[mom_cols].mean(axis=1)
else:
    sector_df["Momentum Score"] = None
if "Earnings Score" in sector_df.columns and "Momentum Score" in sector_df.columns:
    sector_df["Combined Score"] = sector_df[["Earnings Score", "Momentum Score"]].mean(axis=1)
else:
    sector_df["Combined Score"] = None

rank_df = sector_df[["Sector", "Companies", "Earnings Score", "Momentum Score", "Combined Score"]].sort_values("Combined Score", ascending=False)
st.dataframe(rank_df, use_container_width=True, hide_index=True)

st.subheader("Sector Summary")
display_cols = ["Sector", "Companies", "Median EPS Growth YoY", "Median Sales Growth YoY", "Median PAT Growth YoY",
                "Median EPS Growth QoQ", "Median Sales Growth QoQ", "Median PAT Growth QoQ",
                "1M Return", "3M Return", "6M Return", "12M Return"]
display_df = sector_df[[c for c in display_cols if c in sector_df.columns]]
for col in display_df.columns:
    if col == "Sector":
        continue
    display_df[col] = display_df[col].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A")
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.subheader("Sector Constituents")
sel_sector = st.selectbox("Select sector for constituents", rank_df["Sector"].tolist() if "Sector" in rank_df.columns else sectors)
if sel_sector and sel_sector in sector_details:
    details = sector_details[sel_sector].get("details", [])
    if details:
        constituents_df = pd.DataFrame(details)
        for c in ["EPS YoY", "Sales YoY", "PAT YoY", "EPS QoQ", "Sales QoQ", "PAT QoQ"]:
            if c in constituents_df.columns:
                constituents_df[c] = constituents_df[c].apply(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "N/A")
        for c in ["1M", "3M", "6M", "12M"]:
            if c in constituents_df.columns:
                constituents_df[c] = constituents_df[c].apply(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "N/A")
        for c in ["Price"]:
            if c in constituents_df.columns:
                constituents_df[c] = constituents_df[c].apply(lambda v: f"${v:,.2f}" if pd.notna(v) else "N/A")
        st.dataframe(constituents_df, use_container_width=True, hide_index=True)
        csv = constituents_df.to_csv(index=False).encode("utf-8")
        st.download_button(f"Download {sel_sector} Constituents CSV", csv, f"{sel_sector}_constituents.csv", "text/csv")
    else:
        st.info("No constituent data available for this sector.")