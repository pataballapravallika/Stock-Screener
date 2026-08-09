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
from scoring.config import DEFAULT_CONFIG, ScoringConfig, score_category, signal_badge
from data.msi_canslim import calculate_msi_ratings
from data.trendlyne_dvm import calculate_trendlyne_dvm

st.set_page_config(page_title="Ranking Engine", layout="wide")

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

st.title("Ranking Engine")
st.caption("Custom weightage, overall score, sector & industry rank, and top 100 watchlist")

st.sidebar.header("Ranking Engine Settings")
custom_weightage = st.sidebar.slider("Technical Weight", 0.0, 1.0, 0.60, 0.05)
fund_weightage = 1.0 - custom_weightage
st.sidebar.slider("Fundamental Weight", 0.0, 1.0, fund_weightage, 0.05, disabled=True)
buy_threshold = st.sidebar.slider("Buy Threshold", 50, 90, 70)
sell_threshold = st.sidebar.slider("Sell Threshold", 10, 50, 40)
include_banks = st.sidebar.checkbox("Include Banking Stocks", value=True)
signal_filter = st.multiselect("Filter Signal", ["BUY", "HOLD", "SELL"], default=["BUY", "HOLD", "SELL"])

ranking_results = []

for company, symbol in COMPANIES.items():
    if not include_banks and any(b.lower() in company.lower() for b in ["bank", "sbi"]):
        continue

    try:
        df = fetch_prices(symbol, period="1y")
        if df.empty:
            continue
        df = compute_technical_indicators(df)
        latest = df.iloc[-1]
        tech_result = score_technical(latest)

        fund = fetch_fundamentals(symbol) or {}
        sector = fund.get("Sector") or "Unknown"
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
            fund_score_result = {"percentage": score_banking(bank_data)["percentage"], "signal": score_banking(bank_data)["signal"]}
        else:
            fund_score_result = score_fundamental(fund_for_scoring)

        combined = combined_score(
            technical_result=tech_result,
            fundamental_result=fund_score_result,
            is_bank=is_bank,
        )

        overall_score = combined["combined_percentage"]
        signal = combined["combined_signal"]

        msi_data = calculate_msi_ratings(symbol, prices=df, fund=fund)
        dvm_data = calculate_trendlyne_dvm(symbol, prices=df, fund=fund)

        ranking_results.append({
            "Company": company,
            "Symbol": symbol,
            "Sector": sector,
            "Overall Score": overall_score,
            "Trendlyne DVM": dvm_data["DVMScore"],
            "Durability (D)": dvm_data["DurabilityGrade"],
            "Valuation (V)": dvm_data["ValuationGrade"],
            "Momentum (M)": dvm_data["MomentumGrade"],
            "MSI Master Score": msi_data["MasterScore"],
            "EPS Rating": msi_data["EPSRating"],
            "RS Rating": msi_data["RSRating"],
            "Buyer Demand": msi_data["BuyerDemandGrade"],
            "Tech Score": tech_result["percentage"],
            "Fund Score": fund_score_result["percentage"],
            "Signal": signal,
            "Category": score_category(overall_score),
            "Revenue Growth": fund.get("RevenueGrowth"),
            "EPS Growth": fund.get("EarningsGrowth"),
            "ROE": fund.get("ROE"),
            "ROCE": fund.get("ROCE"),
            "ROA": fund.get("ROA"),
            "Debt/Equity": fund.get("DebtEquity"),
            "Altman Z": fund.get("AltmanZScore"),
            "Piotroski": fund.get("PiotroskiFScore"),
            "Promoter %": f"{fund.get('Promoter_Pct'):.2f}%" if fund.get("Promoter_Pct") is not None else "N/A",
            "Institutional %": f"{fund.get('Institutional_Pct'):.2f}%" if fund.get("Institutional_Pct") is not None else "N/A",
        })
    except Exception:
        continue

if not ranking_results:
    st.error("No ranking data available.")
    st.stop()

rank_df = pd.DataFrame(ranking_results)
if signal_filter:
    rank_df = rank_df[rank_df["Signal"].isin(signal_filter)]
rank_df = rank_df.sort_values("Overall Score", ascending=False)
rank_df["Rank"] = range(1, len(rank_df) + 1)

st.subheader("Overall Ranking")
display_cols = ["Rank", "Company", "Symbol", "Sector", "Overall Score", "Trendlyne DVM", "Durability (D)", "Valuation (V)", "Momentum (M)",
                "MSI Master Score", "EPS Rating", "RS Rating", "Buyer Demand",
                "Tech Score", "Fund Score", "Signal", "Category", "Revenue Growth", "EPS Growth", "ROE", "ROCE", "ROA", "Debt/Equity",
                "Altman Z", "Piotroski", "Promoter %", "Institutional %"]

display_cols = [c for c in display_cols if c in rank_df.columns]
st.dataframe(
    rank_df[display_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)

st.divider()

st.subheader("Score Distribution")
fig = px.histogram(rank_df, x="Overall Score", nbins=10, color="Category",
                   title="Score Distribution by Category")
fig.update_layout(height=350)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Sector Rank")
sector_rank = rank_df.groupby("Sector").agg(
    Avg_Score=("Overall Score", "mean"),
    Count=("Overall Score", "count"),
    Top_Score=("Overall Score", "max"),
).reset_index()
sector_rank = sector_rank.sort_values("Avg_Score", ascending=False)
sector_rank["Sector Rank"] = range(1, len(sector_rank) + 1)
st.dataframe(sector_rank, use_container_width=True, hide_index=True)

st.divider()

st.subheader("Top Ranked Stocks")
st.caption("Top 10 stocks from the current universe ranked by combined score")
top_10 = rank_df.head(10)
fig = px.bar(top_10, x="Company", y="Overall Score", color="Signal",
             title="Top 10 Stocks by Combined Score")
fig.update_layout(height=400, xaxis_tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Watchlist Ranking")
watchlist = st.multiselect("Add to Watchlist", list(COMPANIES.keys()), default=rank_df.head(5)["Company"].tolist())
if watchlist:
    wl_df = rank_df[rank_df["Company"].isin(watchlist)]
    st.dataframe(wl_df[["Rank", "Company", "Symbol", "Overall Score", "Signal", "Category"]], use_container_width=True, hide_index=True)

st.divider()

st.subheader("Custom Weightage Preview")
st.write(f"Technical Weight: {custom_weightage:.0%}")
st.write(f"Fundamental Weight: {fund_weightage:.0%}")
st.write(f"Buy Threshold: {buy_threshold}")
st.write(f"Sell Threshold: {sell_threshold}")

c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["Technical", "Fundamental"], y=[custom_weightage * 100, fund_weightage * 100],
                         marker_color=["blue", "green"]))
    fig.update_layout(height=300, title="Weightage Allocation", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    signal_counts = rank_df["Signal"].value_counts()
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=signal_counts.index, values=signal_counts.values,
                         hole=0.4, marker_colors=["green", "orange", "red"]))
    fig.update_layout(height=300, title="Signal Distribution")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Quarterly EPS / PAT / Sales Ranking")
st.caption("Compare quarterly fundamentals and shareholding trends for the selected universe.")

from fundamentals.ratios import safe_float
from fundamentals.growth import yoy_growth

COMPANIES_QR = {
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

selected_companies = st.multiselect("Select companies", list(COMPANIES_QR.keys()), default=list(COMPANIES_QR.keys()), key="qr_companies")

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

qr_results = []
for name in selected_companies:
    symbol = COMPANIES_QR[name]
    fund = fetch_fundamentals(symbol)
    quarterly = get_quarterly_df(fund)
    if quarterly is None or quarterly.empty:
        continue
    periods = list(quarterly.columns)
    if len(periods) < 4:
        continue
    revenue_label = _find_first_index(quarterly, ["Total Revenue", "Revenue", "Sales", "Operating Revenue"])
    eps_label = _find_first_index(quarterly, ["Diluted EPS", "Basic EPS", "EPS"])
    net_income_label = _find_first_index(quarterly, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest", "Net Income From Continuing And Discontinued Operation"])
    revenue_values = _extract_quarter_values(quarterly, revenue_label)
    eps_values = _extract_quarter_values(quarterly, eps_label)
    pat_values = _extract_quarter_values(quarterly, net_income_label)
    results = {
        "Company": name, "Symbol": symbol,
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
        latest_npm = latest_pat / latest_sales
    if prior_year_idx is not None and len(pat_values) > prior_year_idx and len(revenue_values) > prior_year_idx:
        prior_pat = pat_values[prior_year_idx]
        prior_sales = revenue_values[prior_year_idx]
        if prior_pat is not None and prior_sales is not None and prior_sales != 0:
            prior_npm = prior_pat / prior_sales
    results["NPM_YoY"] = yoy_growth(latest_npm, prior_npm) if latest_npm is not None and prior_npm is not None else None
    promoter_pct = fund.get("Promoter_Pct")
    institutions_pct = fund.get("Institutional_Pct")
    sh_hist = fund.get("Shareholding_History") or []
    results["Promoter %"] = promoter_pct
    results["Institutional %"] = institutions_pct
    results["Shareholding History"] = "; ".join([f"{date}: {pct:.2f}%" for date, pct in sh_hist]) if sh_hist else "N/A"
    if len(sh_hist) >= 2:
        results["Institutional_Change"] = round(sh_hist[0][1] - sh_hist[-1][1], 2)
    else:
        results["Institutional_Change"] = None
    results["Promoter_Change"] = None
    results["Shares Outstanding"] = fund.get("SharesOutstanding")
    results["Float Shares"] = fund.get("FloatShares")
    score, max_score = _score_company(results)
    results["Score"] = score
    results["Max Score"] = max_score
    qr_results.append(results)

if qr_results:
    qr_df = pd.DataFrame(qr_results)
    qr_df = qr_df.sort_values(["Score", "Sales_YoY", "EPS_YoY", "PAT_YoY"], ascending=[False, False, False, False])
    qr_df.insert(0, "Rank", range(1, len(qr_df) + 1))
    numeric_columns = [
        "Q1 EPS", "Q2 EPS", "Q3 EPS", "Q1 PAT", "Q2 PAT", "Q3 PAT",
        "Q1 Sales", "Q2 Sales", "Q3 Sales", "EPS_YoY", "PAT_YoY", "Sales_YoY", "NPM_YoY",
        "Promoter %", "Institutional %", "Institutional_Change", "Score", "Max Score"
    ]
    for col in numeric_columns:
        if col in qr_df.columns:
            qr_df[col] = qr_df[col].apply(lambda x: np.nan if x is None else x)
    st.dataframe(qr_df, use_container_width=True, hide_index=True)
    csv = qr_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Quarterly Ranking Results", csv, "quarterly_ranking.csv", "text/csv")
else:
    st.info("No quarterly ranking data available for the selected companies.")