from nse_xbrl import NSEClient
import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}
session = requests.Session()
session.headers.update(headers)
session.get('https://www.nseindia.com/', timeout=15)
cookie_str = '; '.join(f'{k}={v}' for k, v in session.cookies.items())

client = NSEClient(cookie_string=cookie_str)
listing = client.get_integrated_filings('RELIANCE', 'Reliance Industries Limited', size=10)
for row in listing['data'][:6]:
    print(f'consolidated: {row.get("consolidated")}, audited: {row.get("audited")}')
    print(f'  keys: {list(row.keys())}')
    print()

# Now check FilingResult is_consolidated
filings = client.fetch_financials('RELIANCE', 'Reliance Industries Limited', max_filings=6)
for f in filings:
    print(f'period: {f.period_start} -> {f.period_end}, consolidated={f.is_consolidated}, audited={f.is_audited}')
