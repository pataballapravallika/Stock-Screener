import sqlite3
conn = sqlite3.connect('stock_data.db')
count = conn.execute('SELECT COUNT(*) FROM raw_filings WHERE ticker=?', ('RELIANCE',)).fetchone()[0]
print(f'raw_filings count for RELIANCE: {count}')
rows = conn.execute('SELECT report_date, period, source_type, file_path FROM raw_filings WHERE ticker=? ORDER BY report_date DESC LIMIT 5', ('RELIANCE',)).fetchall()
for r in rows:
    print(r)
conn.close()
