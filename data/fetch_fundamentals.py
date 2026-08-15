from typing import Dict, Any, Optional, List
from data.providers.nse_xbrl_provider import NSEXBRLProvider
from data.database import get_latest_quarterly_reports, get_latest_annual_reports


_provider = NSEXBRLProvider()


def _is_truthy(val: Any) -> bool:
    """Safe truthiness check that handles pandas DataFrames/Series."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if hasattr(val, "empty"):
        return not val.empty
    return bool(val)


_fundamentals_cache: Dict[str, Dict[str, Any]] = {}


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals from the official NSE XBRL filing data source only.

    Primary source: NSE Integrated Filing XBRL documents (nseindia.com).

    Yahoo Finance is used ONLY for current market price (OHLCV) in
    fetch_prices / pages — never for fundamentals, ownership, or ratios.

    If a value cannot be reliably extracted from the official NSE filing,
    it is returned as N/A.  No third-party (Yahoo Finance, Trendlyne,
    MarketSmith, Screener.in, etc.) fundamental data is ever used.
    """
    clean_sym = symbol.strip().upper()
    # Normalize: strip .NS/.BO suffix for fundamentals (NSE XBRL data is keyed
    # by bare ticker in the DB).  Price lookups handle the .NS suffix separately.
    for suffix in (".NS", ".BO"):
        if clean_sym.endswith(suffix):
            clean_sym = clean_sym[:-len(suffix)]
            break
    if clean_sym in _fundamentals_cache:
        return _fundamentals_cache[clean_sym]

    res = {}
    try:
        res = _provider.build_fundamentals_dict(clean_sym)
    except Exception as e:
        print(f"NSE XBRL error {clean_sym}: {e}")
        res = {"Symbol": clean_sym}

    if not res or not res.get("Symbol"):
        res = {"Symbol": clean_sym}

    _fundamentals_cache[clean_sym] = res
    return res


def get_data_provenance(symbol: str) -> dict:
    """Return provenance info for a ticker's fundamental data.

    Returns a dict with:
      - source: "NSE Official Filing" or "N/A"
      - report_period: "QxFYxx" or "N/A"
      - report_date: "YYYY-MM-DD" or "N/A"
      - status: "Verified" or "Not Verified"
      - nse_access_blocked: bool
    """
    clean_sym = symbol.strip().upper()
    for suffix in (".NS", ".BO"):
        if clean_sym.endswith(suffix):
            clean_sym = clean_sym[:-len(suffix)]
            break

    q_df = get_latest_quarterly_reports(clean_sym, limit=1)
    a_df = get_latest_annual_reports(clean_sym, limit=1)

    source_url = "N/A"
    report_date = "N/A"
    report_period = "N/A"
    status = "Not Verified"

    if not a_df.empty:
        row = a_df.iloc[0]
        source_url = row.get("source_url") or "N/A"
        report_date = row.get("report_date") or "N/A"
        q = row.get("quarter")
        fy = row.get("financial_year")
        if q and fy:
            report_period = f"Q{q} FY{fy}"
        elif fy:
            report_period = f"FY{fy}"
        status = "Verified"
    elif not q_df.empty:
        row = q_df.iloc[0]
        source_url = row.get("source_url") or "N/A"
        report_date = row.get("report_date") or "N/A"
        q = row.get("quarter")
        fy = row.get("financial_year")
        if q and fy:
            report_period = f"Q{q} FY{fy}"
        elif fy:
            report_period = f"FY{fy}"
        status = "Cached Verified Official Data"

    source = "NSE Official Filing" if status != "Not Verified" else "N/A"

    return {
        "source": source,
        "report_period": report_period,
        "report_date": report_date,
        "source_url": source_url,
        "status": status,
        "nse_access_blocked": _provider._nse_blocked,
    }


def export_fundamentals_to_excel(symbols: List[str], filepath: str) -> bool:
    """Export fundamentals data for one or more tickers to an Excel file.

    Each ticker gets a summary row, plus separate sheets for quarterly
    financials, annual financials, quarterly balance sheet, annual balance
    sheet, and cash flow data where available.

    Args:
        symbols: List of ticker symbols (with or without .NS suffix).
        filepath: Output .xlsx file path.

    Returns:
        True if export succeeded, False otherwise.
    """
    import pandas as pd

    summary_rows = []
    sheet_data = {
        "Quarterly_Income": [],
        "Annual_Income": [],
        "Quarterly_Balance_Sheet": [],
        "Annual_Balance_Sheet": [],
        "Cash_Flow": [],
    }

    for sym in symbols:
        fund = fetch_fundamentals(sym)
        clean = fund.get("Symbol", sym).strip().upper()
        for suffix in (".NS", ".BO"):
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
                break

        summary_rows.append({
            "Ticker": clean,
            "Company": fund.get("Company") or fund.get("company_name") or clean,
            "Sector": fund.get("Sector", "N/A"),
            "Industry": fund.get("Industry", "N/A"),
            "MarketCap_Cr": fund.get("MarketCap"),
            "PE": fund.get("PE"),
            "EPS": fund.get("EPS"),
            "TTM_EPS": fund.get("TTMEPS"),
            "Revenue_Cr": fund.get("Revenue"),
            "PAT_Cr": fund.get("PAT"),
            "SharesOutstanding": fund.get("SharesOutstanding"),
            "ROE": fund.get("ROE"),
            "ROCE": fund.get("ROCE"),
            "DebtEquity": fund.get("DebtEquity"),
            "DividendYield": fund.get("DividendYieldPct"),
            "Source": fund.get("fundamentals_source", "nse_xbrl"),
        })

        for key, sheet_name in [
            ("quarterly_financials", "Quarterly_Income"),
            ("annual_financials", "Annual_Income"),
            ("quarterly_balance_sheet", "Quarterly_Balance_Sheet"),
            ("annual_balance_sheet", "Annual_Balance_Sheet"),
        ]:
            df = fund.get(key)
            if df is not None and hasattr(df, "empty") and not df.empty:
                df = df.copy()
                df.insert(0, "Ticker", clean)
                sheet_data[sheet_name].append(df)

        cf = fund.get("cash_flow") or fund.get("annual_cashflow")
        if cf is not None and hasattr(cf, "empty") and not cf.empty:
            cf = cf.copy()
            cf.insert(0, "Ticker", clean)
            sheet_data["Cash_Flow"].append(cf)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        if summary_rows:
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        for sheet_name, dfs in sheet_data.items():
            if dfs:
                combined = pd.concat(dfs, ignore_index=True)
                combined.to_excel(writer, sheet_name=sheet_name, index=False)

    return True


def clear_fundamentals_cache():
    """Clear the fundamentals cache so fresh data is fetched on next call."""
    global _fundamentals_cache
    _fundamentals_cache = {}
