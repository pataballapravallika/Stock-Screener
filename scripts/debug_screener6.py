import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.screener.in/company/RELIANCE/consolidated/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers, timeout=30)
soup = BeautifulSoup(resp.text, "html.parser")
tables = soup.find_all("table")

for i, table in enumerate(tables):
    first_row = table.find("tr")
    if not first_row:
        continue
    cells = first_row.find_all(["td", "th"])
    header_text = " | ".join([c.get_text(strip=True) for c in cells])
    
    if "jun 2023" in header_text.lower():
        print(f"\n=== Table {i} ===")
        print(f"First row cells ({len(cells)}): {[c.get_text(strip=True) for c in cells]}")
        
        rows = []
        for tr in table.find_all("tr"):
            row_cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(row_cells)
        
        print(f"Total rows: {len(rows)}")
        for j, row in enumerate(rows[:5]):
            print(f"  Row {j} ({len(row)} cells): {row}")
        
        # Build DataFrame like the provider does
        max_cols = max(len(r) for r in rows)
        normalized = []
        for r in rows:
            while len(r) < max_cols:
                r.append("")
            normalized.append(r[:max_cols])
        
        header = normalized[0]
        data = normalized[1:]
        df = pd.DataFrame(data, columns=header)
        df = df.set_index(df.columns[0])
        print(f"\nDataFrame shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"Index (first 5): {list(df.index[:5])}")
        print(f"\nFirst few rows:")
        print(df.head(3))
        break
