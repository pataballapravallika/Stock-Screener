"""Debug table detection."""
import sys
sys.path.insert(0, ".")
import re
from data.providers.official_reports_provider import OfficialReportsProvider

p = OfficialReportsProvider()

for ticker in ["RELIANCE.NS", "HDFCBANK.NS", "SBIN.NS"]:
    q, a, bs, cf = p._fetch_screener_tables(ticker)
    print(f"=== {ticker} ===")
    q_yes = q is not None and not q.empty
    a_yes = a is not None and not a.empty
    print(f"  Quarterly: {'YES' if q_yes else 'NO'} shape={q.shape if q_yes else 'N/A'}")
    print(f"  Annual: {'YES' if a_yes else 'NO'} shape={a.shape if a_yes else 'N/A'}")

    if a_yes:
        cols = [str(c).strip() for c in a.columns]
        fy_pat = re.compile(r'^(FY)?\d{2,4}$', re.IGNORECASE)
        mar_pat = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$', re.IGNORECASE)
        fy_count = sum(1 for c in cols if fy_pat.match(c))
        mar_count = sum(1 for c in cols if mar_pat.match(c))
        ttm_count = sum(1 for c in cols if c.upper() == 'TTM')
        print(f"  Col breakdown: fy={fy_count}, mar={mar_count}, ttm={ttm_count}")
        print(f"  _has_fy={p._has_fy_columns(a)}, _has_q={p._has_quarter_columns(a)}")
        print(f"  First 3 cols: {cols[:3]}")
        print(f"  Last 3 cols: {cols[-3:]}")
    print()
