"""Test integrated filings and corporate announcements with curl_cffi."""
from curl_cffi import requests as cffi_requests
import time

session = cffi_requests.Session(impersonate="chrome")
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
})

print("1. Visiting NSE homepage...")
resp = session.get("https://www.nseindia.com/", timeout=15)
print(f"   Status: {resp.status_code}")
time.sleep(0.5)

print("2. Integrated Filings API...")
resp_if = session.get(
    "https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=RELIANCE&issuer=Reliance%20Industries%20Limited&period_ended=all&type=Integrated%20Filing-%20Financials&page=1&size=10",
    headers={"Accept": "application/json", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings/financial-results"},
    timeout=15,
)
print(f"   Status: {resp_if.status_code}")
if resp_if.status_code == 200:
    data = resp_if.json()
    print(f"   Success! totalCount={data.get('totalCount')}, count={len(data.get('data', []))}")
    if data.get("data"):
        first = data["data"][0]
        print(f"   Latest filing date: {first.get('period_ended')}, XBRL URL: {first.get('xbrl') or first.get('xbrlFile')}")
else:
    print(f"   Body: {resp_if.text[:200]}")

time.sleep(0.5)

print("3. nse_xbrl NSEClient with curl_cffi cookies...")
try:
    from nse_xbrl import NSEClient
    cookie_dict = session.cookies.get_dict()
    client = NSEClient(cookies=cookie_dict)
    filings = client.fetch_financials("RELIANCE", "Reliance Industries Limited", max_filings=2)
    print(f"   nse_xbrl fetched {len(filings)} filings successfully!")
    for f in filings:
        print(f"   Filing {f.period_end}: rev={getattr(f, 'q_revenue', None)}, pat={getattr(f, 'q_pat', None)}")
except Exception as e:
    print(f"   nse_xbrl error: {e}")
