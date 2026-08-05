import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from data.fetch_fundamentals import fetch_fundamentals
from data.fetch_prices import fetch_prices
from scoring.fundamental_score import safe_float

st.set_page_config(page_title="Sector Analysis", layout="wide")

# Minimal universe drawn from existing app companies; extendable later
UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "TATAMOTORS.NS", "ITC.NS", "WIPRO.NS", "HCLTECH.NS"
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

st.title("Sector Analysis")
st.caption("Median quarterly growth and median returns per sector (universe limited to app symbols)")

meta = load_metadata(UNIVERSE)
sectors = sorted(meta["sector"].unique())
selected = st.multiselect("Select sectors to analyze", sectors, default=sectors)
if not selected:
    st.warning("Please select at least one sector")
    st.stop()

# prepare per-company quarterly metrics and returns
@st.cache_data(ttl=30 * 60)
def company_quarterly_metrics(symbol):
    try:
        t = yf.Ticker(symbol)
        q = t.quarterly_financials
        res = {"symbol": symbol}
        if q is None or q.empty:
            return res
        # helper to extract label series
        def extract(label_options):
            for lab in label_options:
                if lab in q.index:
                    return [safe_float(q.loc[lab, col]) for col in q.columns]
            return []
        revenue = extract(["Total Revenue", "Revenue", "Sales", "Operating Revenue"])
        eps = extract(["Diluted EPS", "Basic EPS", "EPS"])
        pat = extract(["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"])
        res.update({"revenue": revenue, "eps": eps, "pat": pat})
        return res
    except Exception:
        return {"symbol": symbol}

@st.cache_data(ttl=30 * 60)
def company_returns(symbol):
    try:
        df = fetch_prices(symbol, period="1y")
        if df.empty:
            return {"symbol": symbol}
        close = df.set_index("Date")["Close"].sort_index()
        latest = close.iloc[-1]
        def r(days):
            if len(close) < days + 1:
                return None
            return float(latest / close.iloc[-(days + 1)] - 1)
        return {"symbol": symbol, "1M": r(21), "3M": r(63), "6M": r(126), "12M": r(252), "price": latest}
    except Exception:
        return {"symbol": symbol}

# aggregate sector-level
sector_rows = []
sector_details = {}
for sector in selected:
    members = meta[meta["sector"] == sector]["symbol"].tolist()
    metrics = []
    returns = []
    details = []
    for s in members:
        qm = company_quarterly_metrics(s)
        cr = company_returns(s)
        # compute YoY for latest quarter if possible
        eps_vals = qm.get("eps") or []
        rev_vals = qm.get("revenue") or []
        pat_vals = qm.get("pat") or []
        eps_yoy = None
        rev_yoy = None
        pat_yoy = None
        eps_qoq = None
        rev_qoq = None
        pat_qoq = None
        try:
            if len(eps_vals) >= 5 and eps_vals[0] is not None and eps_vals[4] is not None and eps_vals[4] != 0:
                eps_yoy = (eps_vals[0] - eps_vals[4]) / abs(eps_vals[4])
            if len(rev_vals) >= 5 and rev_vals[0] is not None and rev_vals[4] is not None and rev_vals[4] != 0:
                rev_yoy = (rev_vals[0] - rev_vals[4]) / abs(rev_vals[4])
            if len(pat_vals) >= 5 and pat_vals[0] is not None and pat_vals[4] is not None and pat_vals[4] != 0:
                pat_yoy = (pat_vals[0] - pat_vals[4]) / abs(pat_vals[4])
            # QoQ
            if len(eps_vals) >= 2 and eps_vals[0] is not None and eps_vals[1] is not None and eps_vals[1] != 0:
                eps_qoq = (eps_vals[0] - eps_vals[1]) / abs(eps_vals[1])
            if len(rev_vals) >= 2 and rev_vals[0] is not None and rev_vals[1] is not None and rev_vals[1] != 0:
                rev_qoq = (rev_vals[0] - rev_vals[1]) / abs(rev_vals[1])
            if len(pat_vals) >= 2 and pat_vals[0] is not None and pat_vals[1] is not None and pat_vals[1] != 0:
                pat_qoq = (pat_vals[0] - pat_vals[1]) / abs(pat_vals[1])
        except Exception:
            pass
        metrics.append({"symbol": s, "eps_yoy": eps_yoy, "rev_yoy": rev_yoy, "pat_yoy": pat_yoy, "eps_qoq": eps_qoq, "rev_qoq": rev_qoq, "pat_qoq": pat_qoq})
        returns.append(cr)
        # details table
        f = meta[meta["symbol"] == s]
        details.append({
            "Company": f["company"].iloc[0] if not f.empty else s,
            "Ticker": s,
            "Price": cr.get("price"),
            "1M": cr.get("1M"),
            "3M": cr.get("3M"),
            "6M": cr.get("6M"),
            "12M": cr.get("12M"),
            "EPS YoY": eps_yoy,
            "Sales YoY": rev_yoy,
            "PAT YoY": pat_yoy,
            "ROE": f["ROE"].iloc[0] if not f.empty else None,
            "ROCE": f["ROCE"].iloc[0] if not f.empty else None,
        })
    # medians
    def median_safe(arr):
        vals = [v for v in arr if v is not None]
        return float(np.nanmedian(vals)) if vals else None
    median_eps_yoy = median_safe([m["eps_yoy"] for m in metrics])
    median_rev_yoy = median_safe([m["rev_yoy"] for m in metrics])
    median_pat_yoy = median_safe([m["pat_yoy"] for m in metrics])
    median_eps_qoq = median_safe([m["eps_qoq"] for m in metrics])
    median_rev_qoq = median_safe([m["rev_qoq"] for m in metrics])
    median_pat_qoq = median_safe([m["pat_qoq"] for m in metrics])

    # median returns
    returns_df = pd.DataFrame(returns)
    def median_return(col):
        if col in returns_df.columns:
            vals = returns_df[col].dropna().tolist()
            return float(np.nanmedian(vals)) if vals else None
        return None

    sector_rows.append({
        "Sector": sector,
        "Companies": len(members),
        "Median EPS YoY": median_eps_yoy,
        "Median Sales YoY": median_rev_yoy,
        "Median PAT YoY": median_pat_yoy,
        "Median EPS QoQ": median_eps_qoq,
        "Median Sales QoQ": median_rev_qoq,
        "Median PAT QoQ": median_pat_qoq,
        "1M": median_return("1M"),
        "3M": median_return("3M"),
        "6M": median_return("6M"),
        "12M": median_return("12M"),
    })
    sector_details[sector] = {"members": members, "details": details}

if not sector_rows:
    st.warning("No sector data available for selected sectors.")
    st.stop()

sector_df = pd.DataFrame(sector_rows)

# ranking: normalize each metric to 0-100 by percentile
score_metrics = ["Median EPS YoY", "Median Sales YoY", "Median PAT YoY", "1M", "3M", "6M", "12M"]
for m in score_metrics:
    vals = sector_df[m].dropna()
    if vals.empty:
        sector_df[m + " Score"] = None
        continue
    # percentile rank
    ranks = sector_df[m].rank(pct=True)
    sector_df[m + " Score"] = ranks * 100

# earnings score and momentum score
sector_df["Earnings Score"] = sector_df[[c + " Score" for c in ["Median EPS YoY", "Median Sales YoY", "Median PAT YoY"]]].mean(axis=1)
sector_df["Momentum Score"] = sector_df[[c + " Score" for c in ["1M", "3M", "6M", "12M"]]].mean(axis=1)
sector_df["Combined Score"] = sector_df[["Earnings Score", "Momentum Score"]].mean(axis=1)

st.subheader("Sector Dashboard")
# Top summary
best = {}
for col, label in [("Median EPS YoY", "Best EPS Growth Sector"), ("Median Sales YoY", "Best Sales Growth Sector"), ("Median PAT YoY", "Best PAT Growth Sector"), ("1M", "Best 1M Sector"), ("3M", "Best 3M Sector"), ("6M", "Best 6M Sector"), ("12M", "Best 12M Sector")]:
    try:
        idx = sector_df[col].dropna().idxmax()
        best[label] = sector_df.loc[idx, "Sector"]
    except Exception:
        best[label] = "N/A"

cols = st.columns(4)
cols[0].metric("Strongest Sector", sector_df.sort_values("Combined Score", ascending=False).iloc[0]["Sector"])
cols[1].metric("Best EPS Growth Sector", best.get("Best EPS Growth Sector", "N/A"))
cols[2].metric("Best Sales Growth Sector", best.get("Best Sales Growth Sector", "N/A"))
cols[3].metric("Best PAT Growth Sector", best.get("Best PAT Growth Sector", "N/A"))

st.subheader("Sector Ranking")
rank_df = sector_df[["Sector", "Companies", "Earnings Score", "Momentum Score", "Combined Score"]].sort_values("Combined Score", ascending=False)
st.dataframe(rank_df, use_container_width=True)

st.subheader("Sector Details")
sel = st.selectbox("Select sector for details", rank_df["Sector"].tolist())
if sel:
    info = sector_details.get(sel, {})
    members = info.get("members", [])
    details = info.get("details", [])
    details_df = pd.DataFrame(details)
    # format percents
    for c in ["EPS YoY", "Sales YoY", "PAT YoY"]:
        if c in details_df.columns:
            details_df[c] = details_df[c].apply(lambda v: f"{v*100:.2f}%" if v is not None else "N/A")
    for c in ["1M", "3M", "6M", "12M"]:
        if c in details_df.columns:
            details_df[c] = details_df[c].apply(lambda v: f"{v*100:.2f}%" if v is not None else "N/A")
    st.dataframe(details_df, use_container_width=True)
    csv = details_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download sector constituents CSV", csv, f"{sel}_constituents.csv", "text/csv")

st.subheader("Median Growth Chart")
try:
    fig_df = sector_df.set_index("Sector")[ ["Median EPS YoY", "Median Sales YoY", "Median PAT YoY"] ] * 100
    # replace NaN with None so plotly ignores them
    st.bar_chart(fig_df)
except Exception:
    st.info("Unable to render median growth chart.")

st.subheader("Sector vs NIFTY 500")
# build equal-weighted sector series when selected
benchmark_symbol = "^CRSLDX"  # NIFTY 500 as requested
period_map = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y", "3Y": "3y", "5Y": "5y", "MAX": "max"}
sel_tf = st.selectbox("Timeframe for sector vs NIFTY 500", ["1M", "3M", "6M", "1Y", "3Y", "5Y"], index=3)
per = period_map.get(sel_tf, "1y")

# compute sector series
members = sector_details.get(sel, {}).get("members", [])
combined = []
for s in members:
    try:
        df = fetch_prices(s, period=per)
        if df.empty:
            continue
        ser = df.set_index("Date")["Close"].sort_index()
        combined.append(ser)
    except Exception:
        continue
if combined:
    combined_df = pd.concat(combined, axis=1).mean(axis=1)
    combined_norm = combined_df / combined_df.iloc[0] * 100
    # benchmark
    try:
        bench = fetch_prices(benchmark_symbol, period=per)
        if not bench.empty:
            bench_ser = bench.set_index("Date")["Close"].sort_index()
            bench_norm = bench_ser / bench_ser.iloc[0] * 100
            plot_df = pd.concat([combined_norm, bench_norm], axis=1)
            plot_df.columns = [f"{sel} Sector (EqWt)", "NIFTY 500"]
            st.line_chart(plot_df, width="stretch")
        else:
            st.info("NIFTY 500 benchmark data unavailable for this timeframe.")
    except Exception:
        st.info("Benchmark unavailable.")
else:
    st.info("Not enough price data to build sector series.")
