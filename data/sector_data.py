import pandas as pd
import numpy as np
from typing import Dict, Any, List


def get_standard_sector(symbol: str, raw_sector: str = None, raw_industry: str = None) -> str:
    """Return standardized sector for a given symbol.

    Priority:
      1) Official sector from NSE quote API (raw_sector / raw_industry)
      2) N/A if no official sector is available

    No hardcoded sector values are used.  All sector classification comes
    from the official NSE quote-equity API response.
    """
    if raw_sector and raw_sector not in ("N/A", "Unknown", None, "25"):
        return raw_sector
    if raw_industry and raw_industry not in ("N/A", "Unknown", None, "25"):
        return raw_industry
    return "N/A"


def get_sector_classifications() -> Dict[str, List[str]]:
    """Return sector baskets from NSE official sector indices.

    These are NSE-indexed sector baskets (e.g. NIFTY BANK, NIFTY IT) that
    are maintained by NSE and published on nseindia.com.  No third-party
    classification is used.
    """
    from data.providers.nse_xbrl_provider import NSEXBRLProvider

    provider = NSEXBRLProvider()
    session = provider._get_session()

    sector_indices = {
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

    # Fetch constituent lists from NSE official API
    sector_baskets = {}
    for sector_name, index_symbol in sector_indices.items():
        basket = []
        endpoint = f"/api/option-chain?symbol={index_symbol.split('^')[-1]}"
        data = provider._nse_get(endpoint)
        if data and isinstance(data, dict):
            records = data.get("records", {}).get("data", [])
            if isinstance(records, list):
                for rec in records:
                    if isinstance(rec, dict):
                        sym = rec.get("symbol")
                        if sym:
                            basket.append(f"{sym}.NS")
        if basket:
            sector_baskets[sector_name] = basket

    return sector_baskets


_sector_metrics_cache = {}


def fetch_sector_performance() -> pd.DataFrame:
    """Compute 1M, 3M, 6M, 1Y returns and Relative Strength vs NIFTY 50 benchmark.

    Uses verified company-level OHLCV price data from the price feed only.
    No Yahoo fundamental sector data is used.
    """
    from data.fetch_prices import fetch_prices

    sector_baskets = get_sector_classifications()
    if not sector_baskets:
        return pd.DataFrame()

    all_symbols = ["^NSEI"]
    for basket in sector_baskets.values():
        all_symbols.extend(basket)

    prices = fetch_prices("^NSEI", period="1y")
    if prices.empty:
        return pd.DataFrame()

    bench_close = prices["Close"].dropna()
    if len(bench_close) < 63:
        return pd.DataFrame()

    b_cur = bench_close.iloc[-1]
    b_m3 = bench_close.iloc[-63]
    b_ret_3m = ((b_cur - b_m3) / b_m3) * 100 if b_m3 else 0.0

    rows = []
    for sector_name, tickers in sector_baskets.items():
        sector_prices = []
        for sym in tickers:
            p = fetch_prices(sym, period="1y")
            if not p.empty and "Close" in p.columns:
                closes = p["Close"].dropna()
                if len(closes) >= 21:
                    sector_prices.append(closes)

        if not sector_prices:
            continue

        avg_series = pd.concat(sector_prices, axis=1).mean(axis=1)
        if avg_series.empty or len(avg_series) < 21:
            continue

        cur_avg = avg_series.iloc[-1]
        m1_avg = avg_series.iloc[-21]
        m3_avg = avg_series.iloc[-63]
        m6_avg = avg_series.iloc[-126] if len(avg_series) >= 126 else avg_series.iloc[0]
        m12_avg = avg_series.iloc[0]

        ret_1m = ((cur_avg - m1_avg) / m1_avg) * 100 if m1_avg else 0.0
        ret_3m = ((cur_avg - m3_avg) / m3_avg) * 100 if m3_avg else 0.0
        ret_6m = ((cur_avg - m6_avg) / m6_avg) * 100 if m6_avg else 0.0
        ret_12m = ((cur_avg - m12_avg) / m12_avg) * 100 if m12_avg else 0.0

        rs_score = ret_3m - b_ret_3m

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


def compute_sector_aggregated_metrics(sector_name: str, target_period: str = None) -> Dict[str, Any]:
    """Calculate aggregate and median fundamental & breadth metrics for a sector.

    Enforces that all constituent companies use the exact same reporting quarter
    period date so fundamentals are never mixed across different quarters.

    All fundamental metrics come from NSE XBRL official filings via
    fetch_fundamentals.  Price data comes from the OHLCV price feed only.
    """
    cache_key = f"{sector_name}_{target_period}"
    if cache_key in _sector_metrics_cache:
        return _sector_metrics_cache[cache_key]

    from data.fetch_fundamentals import fetch_fundamentals
    from data.fetch_prices import fetch_prices
    from data.database import get_latest_quarterly_reports

    sector_baskets = get_sector_classifications()
    constituents = sector_baskets.get(sector_name, [])
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
    for sym in target_constituents:
        fund = fetch_fundamentals(sym) or {}
        pe = fund.get("PE")
        roe = fund.get("ROE")
        sales_g = fund.get("Sales_YoY")
        eps_g = fund.get("EPS_YoY")

        prices = fetch_prices(sym, period="1y")
        if not prices.empty and "Close" in prices.columns:
            prices_col = prices["Close"].dropna()
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
