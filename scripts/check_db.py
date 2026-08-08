import sqlite3
conn = sqlite3.connect('stock_data.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])
for t in ['fundamental_reports', 'fundamental_ttm', 'companies']:
    count = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {count} rows')
conn.close()
