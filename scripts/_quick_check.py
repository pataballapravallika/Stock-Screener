"""Quick check of DB state for all 5 tickers."""
import sys
sys.path.insert(0, ".")

from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record

for ticker in ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]:
    q = get_latest_quarterly_reports(ticker, 2)
    a = get_latest_annual_reports(ticker, 2)
    ttm = get_ttm_record(ticker, "ttm")
    print(f"=== {ticker} ===")
    print(f"  Quarterly: {len(q)} rows")
    print(f"  Annual: {len(a)} rows")
    print(f"  TTM: {'YES' if ttm else 'NO'}")
    if not q.empty:
        row = q.iloc[0]
        print(f"  Latest Q: date={row.get('report_date')}, rev={row.get('revenue')}, pat={row.get('pat')}, eps={row.get('eps')}, equity={row.get('equity')}")
    if not a.empty:
        row = a.iloc[0]
        print(f"  Latest A: fy={row.get('financial_year')}, rev={row.get('revenue')}, pat={row.get('pat')}")
    print()
