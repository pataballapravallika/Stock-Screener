import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from data.fetch_fundamentals import fetch_fundamentals
from scoring.fundamental_score import safe_float
from fundamentals.growth import yoy_growth

st.set_page_config(page_title="Sector Analysis", layout="wide")

SECTOR_COMPANIES = {
    "Technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Financials": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
    "Energy": ["RELIANCE.NS"],
    "Consumer": ["ITC.NS"],
    "Automotive": ["TATAMOTORS.NS"],
}

st.title("Sector Analysis")
st.caption("Median earnings growth, sales growth, PAT growth and relative returns vs Nifty 500.")

selected_sectors = st.multiselect("Select sectors", list(SECTOR_COMPANIES.keys()), default=list(SECTOR_COMPANIES.keys()))
if not selected_sectors:
    st.warning("Please select at least one sector.")
    st.stop()

benchmark_symbol = "^NSEI"
sector_rows = []
benchmark_df = yf.download(benchmark_symbol, period="1y", interval="1d", progress=False)
benchmark_df = benchmark_df.reset_index().rename(columns={"Date": "Date", "Close": "Benchmark Close"})
benchmark_df = benchmark_df.set_index("Date")

for sector in selected_sectors:
    symbols = SECTOR_COMPANIES[sector]
    sector_metrics = []
    returns = []

    for symbol in symbols:
        try:
            fund = fetch_fundamentals(symbol)
            ticker = yf.Ticker(symbol)
            quotes = ticker.history(period="1y", interval="1d")
            if quotes.empty:
                continue

            latest_price = quotes["Close"].iloc[-1]
            def _calc_return(days):
                if len(quotes) < days + 1:
                    return None
                return latest_price / quotes["Close"].iloc[-(days + 1)] - 1

            returns.append({
                "symbol": symbol,
                "1M": _calc_return(21),
                "3M": _calc_return(63),
                "6M": _calc_return(126),
                "12M": _calc_return(252),
            })

            q_income = ticker.quarterly_financials
            if q_income is None or q_income.empty:
                continue

            revenue_label = next((l for l in ["Total Revenue", "Revenue", "Sales", "Operating Revenue"] if l in q_income.index), None)
            eps_label = next((l for l in ["Diluted EPS", "Basic EPS", "EPS"] if l in q_income.index), None)
            pat_label = next((l for l in ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"] if l in q_income.index), None)

            revenue_values = [safe_float(q_income.loc[revenue_label, period]) for period in q_income.columns] if revenue_label else []
            eps_values = [safe_float(q_income.loc[eps_label, period]) for period in q_income.columns] if eps_label else []
            pat_values = [safe_float(q_income.loc[pat_label, period]) for period in q_income.columns] if pat_label else []

            if len(eps_values) >= 4 and len(revenue_values) >= 4 and len(pat_values) >= 4:
                eps_growth = yoy_growth(eps_values[0], eps_values[4])
                sales_growth = yoy_growth(revenue_values[0], revenue_values[4])
                pat_growth = yoy_growth(pat_values[0], pat_values[4])
                sector_metrics.append({
                    "symbol": symbol,
                    "eps_growth": eps_growth,
                    "sales_growth": sales_growth,
                    "pat_growth": pat_growth,
                })
        except Exception:
            continue

    if not sector_metrics:
        continue

    median_eps = np.nanmedian([m["eps_growth"] for m in sector_metrics if m["eps_growth"] is not None])
    median_sales = np.nanmedian([m["sales_growth"] for m in sector_metrics if m["sales_growth"] is not None])
    median_pat = np.nanmedian([m["pat_growth"] for m in sector_metrics if m["pat_growth"] is not None])

    if returns:
        returns_df = pd.DataFrame(returns)
        sector_rows.append({
            "Sector": sector,
            "Median Q EPS Growth": median_eps,
            "Median Q Sales Growth": median_sales,
            "Median Q PAT Growth": median_pat,
            "1M Return": returns_df["1M"].median(),
            "3M Return": returns_df["3M"].median(),
            "6M Return": returns_df["6M"].median(),
            "12M Return": returns_df["12M"].median(),
        })

if not sector_rows:
    st.warning("No sector metrics could be calculated from the selected universe.")
    st.stop()

sector_df = pd.DataFrame(sector_rows)
for col in ["Median Q EPS Growth", "Median Q Sales Growth", "Median Q PAT Growth", "1M Return", "3M Return", "6M Return", "12M Return"]:
    if col in sector_df.columns:
        sector_df[col] = sector_df[col].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A")

st.subheader("Sector Summary")
st.dataframe(sector_df, use_container_width=True)

st.subheader("Sector Returns vs Nifty 500")
for sector in selected_sectors:
    symbols = SECTOR_COMPANIES[sector]
    combined = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        quotes = ticker.history(period="1y", interval="1d")
        if quotes.empty:
            continue
        close = quotes["Close"].rename(symbol)
        combined.append(close)
    if not combined:
        continue
    combined_df = pd.concat(combined, axis=1)
    if combined_df.empty:
        continue

    combined_med = combined_df.median(axis=1, skipna=True)
    combined_med = combined_med.dropna()
    if combined_med.empty:
        continue

    def normalize_index(idx):
        idx = pd.to_datetime(idx)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        return idx.normalize()

    combined_med.index = normalize_index(combined_med.index)
    benchmark_index = normalize_index(benchmark_df.index)
    benchmark_close = benchmark_df.copy()
    benchmark_close.index = benchmark_index

    common_index = combined_med.index.intersection(benchmark_close.index)
    if common_index.empty:
        continue

    stock_norm = combined_med.loc[common_index] / combined_med.loc[common_index].iloc[0] * 100
    benchmark_norm = benchmark_close.loc[common_index, "Benchmark Close"] / benchmark_close.loc[common_index, "Benchmark Close"].iloc[0] * 100

    if getattr(stock_norm, "ndim", 1) > 1:
        stock_norm = stock_norm.squeeze()
    if getattr(benchmark_norm, "ndim", 1) > 1:
        benchmark_norm = benchmark_norm.squeeze()

    chart = pd.concat([
        pd.Series(stock_norm, name="Sector Median"),
        pd.Series(benchmark_norm, name="Nifty 500"),
    ], axis=1)
    if chart.empty:
        continue

    st.line_chart(chart, width="stretch")
