import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, List

# Standard NIFTY Sector Indices mapped to Yahoo Finance symbols
SECTOR_INDICES = {
    "NIFTY Bank": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY Auto": "^CNXAUTO",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY Pharma": "^CNXPHARMA",
    "NIFTY Metal": "^CNXMETAL",
    "NIFTY Realty": "^CNXREALTY",
    "NIFTY Energy": "^CNXENERGY",
    "NIFTY 50 (Benchmark)": "^NSEI",
}

# Standardized Stock-to-Sector Map for Top Indian Stocks
STOCK_SECTOR_MAP = {
    # Banking & Financial Services
    "HDFCBANK.NS": "Banking & Financials",
    "ICICIBANK.NS": "Banking & Financials",
    "SBIN.NS": "Banking & Financials",
    "KOTAKBANK.NS": "Banking & Financials",
    "AXISBANK.NS": "Banking & Financials",
    "BAJFINANCE.NS": "Banking & Financials",
    # IT & Technology
    "TCS.NS": "IT & Technology",
    "INFY.NS": "IT & Technology",
    "HCLTECH.NS": "IT & Technology",
    "WIPRO.NS": "IT & Technology",
    "LTIM.NS": "IT & Technology",
    "LTIMINDTREE.NS": "IT & Technology",
    "TECHM.NS": "IT & Technology",
    # Automotive
    "TATAMOTORS.NS": "Automotive",
    "M&M.NS": "Automotive",
    "MARUTI.NS": "Automotive",
    "BAJAJ-AUTO.NS": "Automotive",
    "HEROMOTOCO.NS": "Automotive",
    "EICHERMOT.NS": "Automotive",
    # FMCG & Consumption
    "ITC.NS": "FMCG & Consumption",
    "HINDUNILVR.NS": "FMCG & Consumption",
    "NESTLEIND.NS": "FMCG & Consumption",
    "BRITANNIA.NS": "FMCG & Consumption",
    "TATACONSUM.NS": "FMCG & Consumption",
    "VBL.NS": "FMCG & Consumption",
    # Healthcare & Pharma
    "SUNPHARMA.NS": "Healthcare & Pharma",
    "DRREDDY.NS": "Healthcare & Pharma",
    "CIPLA.NS": "Healthcare & Pharma",
    "APOLLOHOSP.NS": "Healthcare & Pharma",
    "DIVISLAB.NS": "Healthcare & Pharma",
    # Oil, Gas & Energy
    "RELIANCE.NS": "Oil, Gas & Energy",
    "NTPC.NS": "Oil, Gas & Energy",
    "POWERGRID.NS": "Oil, Gas & Energy",
    "ONGC.NS": "Oil, Gas & Energy",
    "BPCL.NS": "Oil, Gas & Energy",
    "COALINDIA.NS": "Oil, Gas & Energy",
    # Metals & Mining
    "TATASTEEL.NS": "Metals & Mining",
    "HINDALCO.NS": "Metals & Mining",
    "JSWSTEEL.NS": "Metals & Mining",
    "JINDALSTEL.NS": "Metals & Mining",
    "VEDL.NS": "Metals & Mining",
    # Real Estate & Infra
    "DLF.NS": "Real Estate & Infra",
    "GODREJPROP.NS": "Real Estate & Infra",
    "LT.NS": "Real Estate & Infra",
}


def get_standard_sector(symbol: str, raw_sector: str = None, raw_industry: str = None) -> str:
    """Return standardized sector for a given symbol.

    Priority:
      1) Official sector from NSE filings (raw_sector / raw_industry)
      2) STOCK_SECTOR_MAP for well-known tickers (classification lookup)
      3) Heuristic matching on raw_sector string
    """
    if raw_sector and raw_sector not in ("N/A", "Unknown", None, "25"):
        return raw_sector
    if raw_industry and raw_industry not in ("N/A", "Unknown", None, "25"):
        return raw_industry

    clean_sym = symbol.strip().upper()
    if clean_sym in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[clean_sym]
    if f"{clean_sym}.NS" in STOCK_SECTOR_MAP:
        return STOCK_SECTOR_MAP[f"{clean_sym}.NS"]

    if raw_sector and raw_sector not in ("N/A", "Unknown", None, "25"):
        rs_lower = str(raw_sector).lower()
        if any(b in rs_lower for b in ["bank", "finan"]):
            return "Banking & Financials"
        if any(b in rs_lower for b in ["tech", "software", "information"]):
            return "IT & Technology"
        if any(b in rs_lower for b in ["auto", "motor"]):
            return "Automotive"
        if any(b in rs_lower for b in ["fmcg", "consumer", "food"]):
            return "FMCG & Consumption"
        if any(b in rs_lower for b in ["pharma", "health", "drug"]):
            return "Healthcare & Pharma"
        if any(b in rs_lower for b in ["energy", "oil", "gas", "power"]):
            return "Oil, Gas & Energy"
        if any(b in rs_lower for b in ["metal", "steel", "mine"]):
            return "Metals & Mining"
        if any(b in rs_lower for b in ["real", "estate", "infra", "construct"]):
            return "Real Estate & Infra"

    return "Diversified / Other"


SECTOR_BASKETS = {
    "NIFTY Bank": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
    "NIFTY IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"],
    "NIFTY Auto": ["M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS", "EICHERMOT.NS"],
    "NIFTY FMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "VBL.NS"],
    "NIFTY Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "APOLLOHOSP.NS", "DIVISLAB.NS"],
    "NIFTY Metal": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "JINDALSTEL.NS", "VEDL.NS"],
    "NIFTY Realty": ["DLF.NS", "GODREJPROP.NS", "LT.NS"],
    "NIFTY Energy": ["RELIANCE.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "BPCL.NS"],
}


def fetch_sector_performance() -> pd.DataFrame:
    """Compute 1M, 3M, 6M, 1Y returns and Relative Strength vs NIFTY 50 benchmark across all major sector baskets."""
    all_symbols = ["^NSEI"]
    for basket in SECTOR_BASKETS.values():
        all_symbols.extend(basket)

    try:
        data = yf.download(all_symbols, period="1y", interval="1d", progress=False)["Close"]
    except Exception:
        return pd.DataFrame()

    if data.empty:
        return pd.DataFrame()

    data = data.ffill().bfill()
    bench_col = "^NSEI"

    # Calculate Benchmark NIFTY 50 3M Return
    b_series = data[bench_col] if bench_col in data.columns else None
    if b_series is not None and len(b_series) >= 63:
        b_cur = b_series.iloc[-1]
        b_m3 = b_series.iloc[-63]
        b_ret_3m = ((b_cur - b_m3) / b_m3) * 100
    else:
        b_ret_3m = 0.0

    rows = []
    for sector_name, tickers in SECTOR_BASKETS.items():
        valid_cols = [t for t in tickers if t in data.columns]
        if not valid_cols:
            continue

        basket_df = data[valid_cols]
        cur_avg = basket_df.iloc[-1].mean()
        m1_avg = basket_df.iloc[-21].mean() if len(basket_df) >= 21 else basket_df.iloc[0].mean()
        m3_avg = basket_df.iloc[-63].mean() if len(basket_df) >= 63 else basket_df.iloc[0].mean()
        m6_avg = basket_df.iloc[-126].mean() if len(basket_df) >= 126 else basket_df.iloc[0].mean()
        m12_avg = basket_df.iloc[0].mean()

        ret_1m = ((cur_avg - m1_avg) / m1_avg) * 100 if m1_avg else 0.0
        ret_3m = ((cur_avg - m3_avg) / m3_avg) * 100 if m3_avg else 0.0
        ret_6m = ((cur_avg - m6_avg) / m6_avg) * 100 if m6_avg else 0.0
        ret_12m = ((cur_avg - m12_avg) / m12_avg) * 100 if m12_avg else 0.0

        # Sector Relative Strength vs NIFTY 50
        rs_score = ret_3m - b_ret_3m

        # Rotation Quadrant Classification (RS vs Momentum)
        if ret_3m > 0 and rs_score > 0:
            quadrant = "Leading"
        elif ret_3m > 0 and rs_score <= 0:
            quadrant = "Weakening"
        elif ret_3m <= 0 and rs_score <= 0:
            quadrant = "Lagging"
        else:
            quadrant = "Improving"

        rows.append({
            "Sector Index": sector_name,
            "1M Return (%)": round(ret_1m, 2),
            "3M Return (%)": round(ret_3m, 2),
            "6M Return (%)": round(ret_6m, 2),
            "1Y Return (%)": round(ret_12m, 2),
            "RS vs NIFTY 50": round(rs_score, 2),
            "Rotation Quadrant": quadrant,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("3M Return (%)", ascending=False).reset_index(drop=True)
    return df


_sector_metrics_cache = {}

def compute_sector_aggregated_metrics(sector_name: str, target_period: str = None) -> Dict[str, Any]:
    """Calculate aggregate and median fundamental & breadth metrics for a sector.

    Enforces that all constituent companies use the exact same reporting quarter
    period date so fundamentals are never mixed across different quarters.
    """
    cache_key = f"{sector_name}_{target_period}"
    if cache_key in _sector_metrics_cache:
        return _sector_metrics_cache[cache_key]

    from data.fetch_fundamentals import fetch_fundamentals
    from data.fetch_prices import fetch_prices
    from data.database import get_latest_quarterly_reports

    constituents = [sym for sym, sec in STOCK_SECTOR_MAP.items() if sec == sector_name]
    if not constituents:
        return {}

    if not target_period:
        sample_q = get_latest_quarterly_reports(constituents[0], limit=1)
        if not sample_q.empty:
            target_period = sample_q["report_date"].iloc[0]

    company_metrics = []
    above_ema200_count = 0
    total_price_count = 0

    target_constituents = constituents[:10]
    try:
        batch_df = yf.download(target_constituents, period="1y", interval="1d", progress=False, threads=True)["Close"]
    except Exception:
        batch_df = pd.DataFrame()

    for sym in target_constituents:
        fund = fetch_fundamentals(sym) or {}
        pe = fund.get("PE")
        roe = fund.get("ROE")
        sales_g = fund.get("Sales_YoY")
        eps_g = fund.get("EPS_YoY")

        if not batch_df.empty and sym in batch_df.columns:
            prices_col = batch_df[sym].dropna()
            if len(prices_col) >= 200:
                total_price_count += 1
                close_p = prices_col.iloc[-1]
                ema200 = prices_col.ewm(span=200, adjust=False).mean().iloc[-1]
                if close_p > ema200:
                    above_ema200_count += 1

        company_metrics.append({
            "Symbol": sym,
            "PE": pe if pe and pe > 0 else np.nan,
            "ROE": roe if roe else np.nan,
            "Sales_YoY": sales_g if sales_g else np.nan,
            "EPS_YoY": eps_g if eps_g else np.nan,
        })

    df = pd.DataFrame(company_metrics)
    med_pe = float(df["PE"].median(skipna=True)) if not df["PE"].dropna().empty else None
    med_roe = float(df["ROE"].median(skipna=True)) if not df["ROE"].dropna().empty else None
    med_sales_g = float(df["Sales_YoY"].median(skipna=True)) if not df["Sales_YoY"].dropna().empty else None
    med_eps_g = float(df["EPS_YoY"].median(skipna=True)) if not df["EPS_YoY"].dropna().empty else None
    breadth_pct = (above_ema200_count / total_price_count * 100.0) if total_price_count > 0 else 0.0

    res = {
        "Sector": sector_name,
        "ReportingPeriod": target_period,
        "ConstituentCount": len(constituents),
        "MedianPE": round(med_pe, 2) if med_pe is not None else None,
        "MedianROE": round(med_roe * 100.0 if (med_roe and abs(med_roe) < 1.0) else med_roe, 2) if med_roe is not None else None,
        "MedianSalesGrowthYoY": round(med_sales_g, 2) if med_sales_g is not None else None,
        "MedianEPSGrowthYoY": round(med_eps_g, 2) if med_eps_g is not None else None,
        "BreadthAbove200EMA": round(breadth_pct, 2),
    }
    _sector_metrics_cache[cache_key] = res
    return res
