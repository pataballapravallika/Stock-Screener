import requests
from bs4 import BeautifulSoup

urls_to_try = [
    "https://www.screener.in/company/RELIANCE.NS/consolidated/",
    "https://www.screener.in/company/RELIANCE.NS/",
    "https://www.screener.in/company/RELIANCE/",
    "https://screener.in/company/RELIANCE.NS/",
    "https://www.screener.in/company/RELIANCE/consolidated/",
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

for url in urls_to_try:
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        print(f"URL: {url}")
        print(f"  Status: {resp.status_code}")
        print(f"  Final URL: {resp.url}")
        print(f"  Tables: {len(BeautifulSoup(resp.text, 'html.parser').find_all('table'))}")
        print()
    except Exception as e:
        print(f"URL: {url} -> ERROR: {e}")
