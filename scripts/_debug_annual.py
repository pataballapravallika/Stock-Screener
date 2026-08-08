"""Debug annual storage."""
import sys
sys.path.insert(0, ".")
import os
DB = "stock_data.db"
if os.path.exists(DB):
    os.remove(DB)

from data.providers.official_reports_provider import OfficialReportsProvider
from data.database import init_db, get_latest_annual_reports, get_latest_quarterly_reports

init_db()
p = OfficialReportsProvider()

for ticker in ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SBIN.NS"]:
    print(f"\n=== {ticker} ===")
    try:
        fund = p.build_fundamentals_dict(ticker)
        print(f"  quarterly_financials: {'YES' if not fund['quarterly_financials'].empty else 'NO'}")
        print(f"  annual_financials: {'YES' if not fund['annual_financials'].empty else 'NO'}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    q = get_latest_quarterly_reports(ticker, 3)
    a = get_latest_annual_reports(ticker, 3)
    print(f"  DB quarterly: {len(q)} rows")
    print(f"  DB annual: {len(a)} rows")
