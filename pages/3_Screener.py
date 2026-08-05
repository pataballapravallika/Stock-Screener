import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from data.fetch_prices import fetch_prices
from data.fetch_fundamentals import fetch_fundamentals
from scoring.technical_score import compute_technical_indicators, score_technical
from scoring.fundamental_score import score_fundamental
from scoring.banking_score import score_banking
from scoring.combined_score import combined_score
from scoring.config import (
    ScoringConfig,
    DEFAULT_CONFIG,
)
from scoring.technical_score import get_signal_explanation

st.title("Stock Screener")
st.caption("Rank stocks using combined technical + fundamental scoring")

with st.sidebar.expander("Screener Settings", expanded=True):
    period = st.selectbox(
        "Data Period",
        ["1y", "2y", "5y", "10y", "max"],
        index=1
    )

    min_combined = st.slider("Min Combined Score", 0, 100, 0)
    min_technical = st.slider("Min Technical Score", 0, 100, 0)
    min_fundamental = st.slider("Min Fundamental Score", 0, 100, 0)

    sector_filter = st.multiselect(
        "Filter Sector",
        ["Financial Services", "Technology", "Energy", "Consumer", "Automotive", "Healthcare", "Other"],
        default=[]
    )

    signal_filter = st.multiselect(
        "Filter Signal",
        ["BUY", "HOLD", "SELL"],
        default=["BUY", "HOLD", "SELL"]
    )

    use_fundamentals = st.checkbox("Include Fundamentals", value=True)
    include_banks = st.checkbox("Include Banking Stocks", value=True)

    technical_weight = st.slider("Technical Weight", 0.0, 1.0, DEFAULT_CONFIG.technical_weight, 0.05)
    fundamental_weight = st.slider("Fundamental Weight", 0.0, 1.0, DEFAULT_CONFIG.fundamental_weight, 0.05)

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

BANK_SECTORS = {"Financial Services", "Banking", "Finance", "Insurance"}


def analyse_stock(company, symbol, config, use_fundamentals, include_banks):
    result = {
        "Company": company,
        "Symbol": symbol,
        "Sector": "N/A",
    }

    try:
        df = fetch_prices(symbol, period=period)
    except Exception as e:
        return None

    if df.empty:
        return None

    if len(df) < 200:
        return None

    df = compute_technical_indicators(df)
    latest = df.iloc[-1]
    tech_result = score_technical(latest, config=config)

    result["Price"] = latest["Close"]
    result["RSI"] = latest["RSI"] if pd.notna(latest["RSI"]) else None
    result["52W Distance %"] = latest["Distance_52W_High"] if pd.notna(latest["Distance_52W_High"]) else None
    result["Volume Strength"] = "Strong" if pd.notna(latest.get("Volume_MA20")) and latest["Volume"] > latest["Volume_MA20"] else "Weak"
    result["Technical Score"] = tech_result["percentage"]
    result["Technical Signal"] = tech_result["signal"]

    fund = {}
    is_bank = False
    if use_fundamentals:
        try:
            fund = fetch_fundamentals(symbol)
        except Exception:
            fund = {}

        sector = fund.get("Sector") or ""
        is_bank = any(b.lower() in sector.lower() for b in BANK_SECTORS)
        result["Sector"] = sector or "N/A"

        if is_bank and not include_banks:
            return None

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
            bank_score = score_banking(bank_data, config=config)
            result["Fundamental Score"] = bank_score["percentage"]
            result["Fundamental Signal"] = bank_score["signal"]
        else:
            fund_score = score_fundamental(fund_for_scoring, config=config)
            result["Fundamental Score"] = fund_score["percentage"]
            result["Fundamental Signal"] = fund_score["signal"]

        result["Revenue Growth"] = fund.get("RevenueGrowth")
        result["EPS Growth"] = fund.get("EarningsGrowth")
        result["ROE"] = fund.get("ROE")
        result["ROCE"] = fund.get("ROCE")
        result["Debt/Equity"] = fund.get("DebtEquity")
        result["Altman Z"] = fund.get("AltmanZScore")
        result["Piotroski"] = fund.get("PiotroskiFScore")
    else:
        result["Fundamental Score"] = 0
        result["Fundamental Signal"] = "N/A"
        result["Revenue Growth"] = None
        result["EPS Growth"] = None
        result["ROE"] = None
        result["ROCE"] = None
        result["Debt/Equity"] = None
        result["Altman Z"] = None
        result["Piotroski"] = None

    scoring_config = ScoringConfig(
        technical_weight=technical_weight,
        fundamental_weight=fundamental_weight,
    )
    combined = combined_score(
        technical_result=tech_result,
        fundamental_result={"percentage": result.get("Fundamental Score", 0), "signal": result.get("Fundamental Signal", "HOLD")},
        is_bank=is_bank and use_fundamentals,
        config=scoring_config,
    )

    result["Combined Score"] = combined["combined_percentage"]
    result["Combined Signal"] = combined["combined_signal"]

    return result


if st.button("Run Screener", type="primary"):
    results = []
    progress = st.progress(0)
    total = len(COMPANIES)

    config = DEFAULT_CONFIG
    config.technical_weight = technical_weight
    config.fundamental_weight = fundamental_weight

    for i, (company, symbol) in enumerate(COMPANIES.items()):
        r = analyse_stock(company, symbol, config, use_fundamentals, include_banks)
        if r:
            results.append(r)
        progress.progress((i + 1) / total)

    if not results:
        st.warning("No results. Check symbols or data availability.")
        st.stop()

    df_result = pd.DataFrame(results)

    if min_combined > 0:
        df_result = df_result[df_result["Combined Score"] >= min_combined]
    if min_technical > 0:
        df_result = df_result[df_result["Technical Score"] >= min_technical]
    if min_fundamental > 0:
        df_result = df_result[df_result["Fundamental Score"] >= min_fundamental]
    if sector_filter:
        df_result = df_result[df_result["Sector"].isin(sector_filter)]
    if signal_filter:
        df_result = df_result[df_result["Combined Signal"].isin(signal_filter)]

    df_result = df_result.sort_values("Combined Score", ascending=False)
    df_result.insert(0, "Rank", range(1, len(df_result) + 1))

    def highlight_signal(val):
        if val == "BUY":
            return "background-color: #d4edda; color: #155724; font-weight: bold;"
        elif val == "SELL":
            return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
        else:
            return "background-color: #fff3cd; color: #856404;"

    styled = df_result.style.map(highlight_signal, subset=["Combined Signal", "Technical Signal", "Fundamental Signal"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    csv = df_result.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Screener Results",
        csv,
        "screener_results.csv",
        "text/csv",
    )
