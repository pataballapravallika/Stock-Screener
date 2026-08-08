"""Debug HDFCBANK storage issue."""
import sys
sys.path.insert(0, ".")

import os
DB = "stock_data.db"
if os.path.exists(DB):
    os.remove(DB)

from data.providers.official_reports_provider import OfficialReportsProvider
from data.database import get_latest_quarterly_reports, init_db

init_db()
p = OfficialReportsProvider()

print("Fetching and storing HDFCBANK.NS...")
try:
    q_fin = p.get_quarterly_financials('HDFCBANK.NS')
    print(f"quarterly_financials shape: {q_fin.shape if q_fin is not None else 'None'}")
    print(f"quarterly_financials cols: {list(q_fin.columns) if q_fin is not None else 'N/A'}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

q = get_latest_quarterly_reports('HDFCBANK.NS', 20)
print(f"DB rows: {len(q)}")

if len(q) > 0:
    print(q[['report_date', 'revenue', 'pat', 'equity', 'current_assets']].head().to_string())
