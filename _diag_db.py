import sqlite3

conn = sqlite3.connect("data/stock_screener.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
    count = cursor.fetchone()[0]
    print(f"  {t}: {count} rows")

conn.close()

# Also check the root-level DB
print()
conn2 = sqlite3.connect("stock_data.db")
cursor2 = conn2.cursor()
cursor2.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables2 = [r[0] for r in cursor2.fetchall()]
print("Root DB tables:", tables2)
for t in tables2:
    cursor2.execute(f"SELECT COUNT(*) FROM [{t}]")
    count = cursor2.fetchone()[0]
    print(f"  {t}: {count} rows")

conn2.close()
