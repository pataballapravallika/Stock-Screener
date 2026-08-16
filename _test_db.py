from data.database import get_latest_quarterly_reports, get_latest_annual_reports, get_ttm_record
import pandas as pd
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 200)
for t in ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'SBIN']:
    q = get_latest_quarterly_reports(t, limit=1)
    a = get_latest_annual_reports(t, limit=1)
    print(f'{t}: q_empty={q.empty} a_empty={a.empty}')
    if not q.empty:
        r = q.iloc[0]
        print(f'  Q: fy={r.get("financial_year")} q={r.get("quarter")} rev={r.get("revenue")} pat={r.get("pat")} eps={r.get("eps")} ebit={r.get("ebit")} src={r.get("source_type")} url={r.get("source_url")}')
    if not a.empty:
        r = a.iloc[0]
        print(f'  A: fy={r.get("financial_year")} rev={r.get("revenue")} pat={r.get("pat")} eps={r.get("eps")} src={r.get("source_type")} url={r.get("source_url")}')
