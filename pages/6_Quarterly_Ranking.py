import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from data.fetch_fundamentals import fetch_fundamentals
from fundamentals.growth import yoy_growth
from fundamentals.ratios import safe_float, compute_npm

st.set_page_config(page_title="Quarterly Ranking", layout="wide")

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

st.title("Quarterly EPS / PAT / Sales Ranking")
st.caption("Compare quarterly fundamentals and shareholding trends for the selected universe.")

selected_companies = st.multiselect("Select companies", list(COMPANIES.keys()), default=list(COMPANIES.keys()))

if not selected_companies:
    st.warning("Please select at least one company.")
    st.stop()


def _find_first_index(df, labels):
    if df is None or df.empty:
        return None
    for label in labels:
        if label in df.index:
            return label
    return None


def _extract_quarter_values(df, label):
    if df is None or df.empty or label is None:
        return []
    return [safe_float(df.loc[label, period]) for period in df.columns]


def _parse_shareholding(ticker):
    major = ticker.major_holders
    promoter_pct = None
    institutions_pct = None
    if major is not None and not major.empty:
        if "insidersPercentHeld" in major.index:
            promoter_pct = safe_float(major.loc["insidersPercentHeld", "Value"])
        if "institutionsPercentHeld" in major.index:
            institutions_pct = safe_float(major.loc["institutionsPercentHeld", "Value"])

    inst_hist = []
    try:
        inst_df = ticker.institutional_holders
        if inst_df is not None and not inst_df.empty:
            date_column = "Date Reported" if "Date Reported" in inst_df.columns else "Date"
            pct_column = "pctHeld" if "pctHeld" in inst_df.columns else None
            if pct_column is not None:
                for _, row in inst_df.iterrows():
                    date_value = row.get(date_column)
                    pct_value = safe_float(row.get(pct_column))
                    if date_value is not None and pct_value is not None:
                        inst_hist.append((str(date_value), pct_value))
    except Exception:
        pass

    inst_hist = sorted(inst_hist, key=lambda x: x[0], reverse=True)[:3]
    return promoter_pct, institutions_pct, inst_hist


def _format_percent(value):
    if value is None or np.isnan(value):
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_number(value):
    if value is None or np.isnan(value):
        return "N/A"
    return f"{int(value):,}"


def _score_company(metrics):
    score = 0
    max_score = 4
    if metrics.get("EPS_YoY") is not None and metrics["EPS_YoY"] > 0:
        score += 1
    if metrics.get("PAT_YoY") is not None and metrics["PAT_YoY"] > 0:
        score += 1
    if metrics.get("Sales_YoY") is not None and metrics["Sales_YoY"] > 0:
        score += 1
    if metrics.get("NPM_YoY") is not None and metrics["NPM_YoY"] > 0:
        score += 1
    if metrics.get("Promoter_Change") is not None:
        max_score += 1
        if metrics["Promoter_Change"] > 0:
            score += 1
    if metrics.get("Institutional_Change") is not None:
        max_score += 1
        if metrics["Institutional_Change"] > 0:
            score += 1
    return score, max_score


def _build_company_metrics(name, symbol):
    ticker = yf.Ticker(symbol)
    quarterly = ticker.quarterly_financials
    if quarterly is None or quarterly.empty:
        return None

    periods = list(quarterly.columns)
    if len(periods) < 4:
        return None

    revenue_label = _find_first_index(quarterly, ["Total Revenue", "Revenue", "Sales", "Operating Revenue"])
    eps_label = _find_first_index(quarterly, ["Diluted EPS", "Basic EPS", "EPS"])
    net_income_label = _find_first_index(quarterly, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest", "Net Income From Continuing And Discontinued Operation"])

    revenue_values = _extract_quarter_values(quarterly, revenue_label)
    eps_values = _extract_quarter_values(quarterly, eps_label)
    pat_values = _extract_quarter_values(quarterly, net_income_label)

    results = {
        "Company": name,
        "Symbol": symbol,
        "Latest Quarter": str(periods[0].date()) if hasattr(periods[0], "date") else str(periods[0]),
        "Q1 EPS": eps_values[0] if len(eps_values) > 0 else None,
        "Q2 EPS": eps_values[1] if len(eps_values) > 1 else None,
        "Q3 EPS": eps_values[2] if len(eps_values) > 2 else None,
        "Q1 PAT": pat_values[0] if len(pat_values) > 0 else None,
        "Q2 PAT": pat_values[1] if len(pat_values) > 1 else None,
        "Q3 PAT": pat_values[2] if len(pat_values) > 2 else None,
        "Q1 Sales": revenue_values[0] if len(revenue_values) > 0 else None,
        "Q2 Sales": revenue_values[1] if len(revenue_values) > 1 else None,
        "Q3 Sales": revenue_values[2] if len(revenue_values) > 2 else None,
    }

    latest_sales = results.get("Q1 Sales")
    latest_eps = results.get("Q1 EPS")
    latest_pat = results.get("Q1 PAT")
    prior_year_idx = 4 if len(periods) > 4 else None

    def _get_yoy(values, idx):
        if idx is None or idx + 4 >= len(values) or values[idx] is None or values[idx + 4] is None:
            return None
        return yoy_growth(values[idx], values[idx + 4])

    results["EPS_YoY"] = _get_yoy(eps_values, 0)
    results["PAT_YoY"] = _get_yoy(pat_values, 0)
    results["Sales_YoY"] = _get_yoy(revenue_values, 0)

    latest_npm = None
    prior_npm = None
    if latest_pat is not None and latest_sales is not None and latest_sales != 0:
        latest_npm = compute_npm(latest_pat, latest_sales)
    if prior_year_idx is not None and len(pat_values) > prior_year_idx and len(revenue_values) > prior_year_idx:
        prior_pat = pat_values[prior_year_idx]
        prior_sales = revenue_values[prior_year_idx]
        if prior_pat is not None and prior_sales is not None and prior_sales != 0:
            prior_npm = compute_npm(prior_pat, prior_sales)
    results["Q1 NPM"] = latest_npm
    results["Q2 NPM"] = compute_npm(results.get("Q2 PAT"), results.get("Q2 Sales")) if results.get("Q2 PAT") is not None and results.get("Q2 Sales") is not None else None
    results["Q3 NPM"] = compute_npm(results.get("Q3 PAT"), results.get("Q3 Sales")) if results.get("Q3 PAT") is not None and results.get("Q3 Sales") is not None else None
    results["NPM_YoY"] = yoy_growth(latest_npm, prior_npm) if latest_npm is not None and prior_npm is not None else None

    promoter_pct, institutions_pct, inst_history = _parse_shareholding(ticker)
    results["Promoter %"] = promoter_pct
    results["Institutional %"] = institutions_pct
    results["Shareholding History"] = "; ".join([f"{date}: {pct * 100:.2f}%" for date, pct in inst_history]) if inst_history else "N/A"

    if len(inst_history) >= 2:
        results["Institutional_Change"] = inst_history[0][1] - inst_history[1][1]
    else:
        results["Institutional_Change"] = None

    results["Promoter_Change"] = None
    results["Shares Outstanding"] = fetch_fundamentals(symbol).get("SharesOutstanding")
    results["Float Shares"] = fetch_fundamentals(symbol).get("FloatShares")

    score, max_score = _score_company(results)
    results["Score"] = score
    results["Max Score"] = max_score

    return results


results = []
with st.spinner("Fetching quarterly fundamentals and shareholding data..."):
    for name in selected_companies:
        symbol = COMPANIES[name]
        company_metrics = _build_company_metrics(name, symbol)
        if company_metrics is not None:
            results.append(company_metrics)

if not results:
    st.warning("Quarterly fundamentals unavailable for the selected companies.")
    st.stop()

results_df = pd.DataFrame(results)
results_df = results_df.sort_values(["Score", "Sales_YoY", "EPS_YoY", "PAT_YoY"], ascending=[False, False, False, False])
results_df.insert(0, "Rank", range(1, len(results_df) + 1))

numeric_columns = [
    "Q1 EPS", "Q2 EPS", "Q3 EPS",
    "Q1 PAT", "Q2 PAT", "Q3 PAT",
    "Q1 Sales", "Q2 Sales", "Q3 Sales",
    "Q1 NPM", "Q2 NPM", "Q3 NPM",
    "EPS_YoY", "PAT_YoY", "Sales_YoY", "NPM_YoY",
    "Promoter %", "Institutional %", "Institutional_Change", "Score", "Max Score"
]
for col in numeric_columns:
    if col in results_df.columns:
        results_df[col] = results_df[col].apply(lambda x: np.nan if x is None else x)

st.dataframe(results_df, use_container_width=True, hide_index=True)

csv = results_df.to_csv(index=False).encode("utf-8")
st.download_button("Download Quarterly Ranking Results", csv, "quarterly_ranking.csv", "text/csv")
