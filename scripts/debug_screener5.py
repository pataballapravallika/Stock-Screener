import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import math

url = "https://www.screener.in/company/RELIANCE/consolidated/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers, timeout=30)
soup = BeautifulSoup(resp.text, "html.parser")
tables = soup.find_all("table")

for i, table in enumerate(tables):
    header = table.find("thead")
    if header:
        header_text = header.get_text(separator=" ", strip=True).lower()
    else:
        first_row = table.find("tr")
        header_text = first_row.get_text(separator=" ", strip=True).lower() if first_row else ""
    
    cols = [str(c) for c in table.find_all("tr")[0].find_all(["td", "th"])] if table.find_all("tr") else []
    is_q = False
    if "quarterly" in header_text or "quarter" in header_text:
        is_q = True
    else:
        for c in cols:
            if re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}', c, re.IGNORECASE):
                is_q = True
                break
    
    if not is_q:
        continue
    
    print(f"\n=== Table {i} (Quarterly) ===")
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    
    max_cols = max(len(r) for r in rows)
    normalized = []
    for r in rows:
        while len(r) < max_cols:
            r.append("")
        normalized.append(r[:max_cols])
    
    header_row = normalized[0]
    data_rows = normalized[1:]
    df = pd.DataFrame(data_rows, columns=header_row)
    df = df.set_index(df.columns[0])
    
    print(f"Index labels: {list(df.index)}")
    print(f"Columns: {list(df.columns)}")
    
    # Test extraction for revenue
    INCOME_LABEL_MAP = {
        "revenue": ["Total Revenue", "Revenue", "Sales", "Operating Revenue", "Total Sales", "Revenue from Operations"],
        "operating_profit": ["Operating Profit", "EBIT", "Operating Income", "Profit Before Interest And Tax"],
        "ebit": ["EBIT", "Operating Income", "Operating Profit", "Profit Before Interest And Tax"],
        "pat": ["Net Profit", "Net Income", "Profit After Tax", "Net Profit After Tax", "Profit For The Period", "PAT"],
        "eps": ["EPS in Rs", "Diluted EPS", "Basic EPS", "EPS", "Earnings Per Share"],
    }
    
    def find_label(df, candidates):
        index_labels = [str(idx) for idx in df.index]
        for candidate in candidates:
            for idx_label in index_labels:
                if candidate.lower() in idx_label.lower():
                    return idx_label
        return None
    
    def safe_float(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        s = str(value).strip().replace(",", "").replace("%", "").replace("₹", "").replace("$", "").replace("—", "").replace("-", "").strip()
        if not s:
            return None
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None
    
    for metric, candidates in INCOME_LABEL_MAP.items():
        label = find_label(df, candidates)
        if label:
            val = df.loc[label, df.columns[0]]
            print(f"  {metric}: label='{label}', raw='{val}', parsed={safe_float(val)}")
        else:
            print(f"  {metric}: NOT FOUND")
    
    break  # Only check first quarterly table
