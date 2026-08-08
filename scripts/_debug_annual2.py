"""Debug _store_annual_data."""
import sys
sys.path.insert(0, ".")
import os
DB = "stock_data.db"
if os.path.exists(DB):
    os.remove(DB)

from data.providers.official_reports_provider import OfficialReportsProvider, _ReportHelpers
from data.database import init_db, save_fundamental_report, get_latest_annual_reports
import traceback

init_db()
p = OfficialReportsProvider()

for ticker in ["RELIANCE.NS"]:
    q_income, a_income, bs, cf = p._fetch_screener_tables(ticker)
    print(f"=== {ticker} ===")
    print(f"Annual shape: {a_income.shape if a_income is not None else 'None'}")
    if a_income is not None and not a_income.empty:
        print(f"Cols: {list(a_income.columns)}")
        print(f"Index (first 5): {list(a_income.index[:5])}")
        
        # Try storing
        for col in list(a_income.columns)[:3]:
            period_str = _ReportHelpers.normalize_period(col)
            fy = _ReportHelpers.derive_annual_financial_year(col)
            print(f"  Col={col!r} -> period={period_str!r}, fy={fy}")
            if fy is None:
                print(f"  SKIPPING: derive_annual_financial_year returned None")
                continue
            try:
                record = {
                    "ticker": ticker,
                    "report_date": period_str,
                    "period": "annual",
                    "quarter": None,
                    "financial_year": fy,
                    "revenue": p._extract_latest_value(a_income, "revenue", col),
                    "pat": p._extract_latest_value(a_income, "pat", col),
                }
                save_fundamental_report(record)
                print(f"  Saved: rev={record['revenue']}, pat={record['pat']}")
            except Exception as e:
                print(f"  ERROR: {e}")
                traceback.print_exc()

a = get_latest_annual_reports(ticker, 5)
print(f"\nDB annual rows: {len(a)}")
if not a.empty:
    print(a[['report_date', 'financial_year', 'revenue', 'pat']].head().to_string())
