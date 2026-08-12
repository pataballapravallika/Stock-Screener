import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.database import init_db, get_latest_annual_reports
init_db()

for sym in ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'SBIN.NS']:
    a_reports = get_latest_annual_reports(sym, n=2)
    print(f"\n{sym}: {len(a_reports)} annual reports")
    for _, row in a_reports.iterrows():
        print(f"  FY: {row.get('financial_year')}, Assets: {row.get('assets')}, Equity: {row.get('equity')}, Liab: {row.get('liabilities')}, CA: {row.get('current_assets')}, CL: {row.get('current_liabilities')}, RE: {row.get('retained_earnings')}, EBIT: {row.get('ebit')}, Revenue: {row.get('revenue')}, Debt: {row.get('debt')}")
