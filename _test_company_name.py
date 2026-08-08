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
listing = client.get_integrated_filings('RELIANCE', 'RELIANCE', size=5)
if listing and 'data' in listing:
    for row in listing['data'][:3]:
        print(f'companyName: {row.get("companyName")}')
        print(f'smName: {row.get("smName")}')
        print(f'cmName: {row.get("cmName")}')
        print(f'consolidated: {row.get("consolidated")}')
        print(f'audited: {row.get("audited")}')
        print()
