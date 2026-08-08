import requests
from bs4 import BeautifulSoup

url = "https://www.screener.in/company/RELIANCE.NS/consolidated/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

resp = requests.get(url, headers=headers, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Content length: {len(resp.text)}")

soup = BeautifulSoup(resp.text, "html.parser")
print(f"Tables found: {len(soup.find_all('table'))}")

for i, table in enumerate(soup.find_all("table")):
    header = table.find("thead")
    if header:
        print(f"Table {i} header: {header.get_text(separator=' ', strip=True)[:200]}")
    else:
        first_row = table.find("tr")
        if first_row:
            print(f"Table {i} first row: {first_row.get_text(separator=' ', strip=True)[:200]}")
