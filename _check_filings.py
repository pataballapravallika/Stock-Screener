import sqlite3, os
conn = sqlite3.connect('stock_data.db')
rows = conn.execute("SELECT ticker, report_date, period, source_type, source_url, file_path, file_hash FROM raw_filings WHERE ticker IN ('RELIANCE','TCS','INFY','HDFCBANK','SBIN') ORDER BY ticker, report_date").fetchall()
for r in rows:
    fp = r[5]
    exists = 'MISSING'
    if fp and os.path.exists(fp):
        exists = f'OK({os.path.getsize(fp)//1024}KB)'
    print(f"{r[0]:12s} {r[2]:10s} {r[1]}  type={r[5] if r[3] else 'n/a'} url={r[4][:80] if r[4] else 'n/a'} exists={exists}")
