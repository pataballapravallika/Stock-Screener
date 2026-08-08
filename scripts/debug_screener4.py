import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

url = "https://www.screener.in/company/RELIANCE/consolidated/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers, timeout=30)
soup = BeautifulSoup(resp.text, "html.parser")
tables = soup.find_all("table")

print(f"Total tables: {len(tables)}")

for i, table in enumerate(tables):
    header = table.find("thead")
    if header:
        header_text = header.get_text(separator=" ", strip=True).lower()
    else:
        first_row = table.find("tr")
        header_text = first_row.get_text(separator=" ", strip=True).lower() if first_row else ""
    
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    
    print(f"\n=== Table {i} ===")
    print(f"Header text: {header_text[:200]}")
    print(f"Rows: {len(rows)}")
    
    if rows:
        max_cols = max(len(r) for r in rows)
        normalized = []
        for r in rows:
            while len(r) < max_cols:
                r.append("")
            normalized.append(r[:max_cols])
        
        if len(normalized) >= 2:
            header_row = normalized[0]
            data_rows = normalized[1:]
            try:
                df = pd.DataFrame(data_rows, columns=header_row)
                df = df.set_index(df.columns[0])
                print(f"Index labels (first 5): {list(df.index[:5])}")
                print(f"Columns: {list(df.columns)}")
                print(f"Is quarterly: {any(re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}', c, re.IGNORECASE) for c in df.columns)}")
                print(df.head(5).to_string())
            except Exception as e:
                print(f"Error: {e}")
