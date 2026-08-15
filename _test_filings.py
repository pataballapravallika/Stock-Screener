from nse_xbrl import NSEClient
import requests
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nseindia.com/',
}
s = requests.Session()
s.headers.update(headers)
s.get('https://www.nseindia.com/', timeout=15)
s.get('https://www.nseindia.com/market-data/live-equity-market', timeout=15)
cookie_str = '; '.join([f'{k}={v}' for k, v in s.cookies.items()])
client = NSEClient(cookie_string=cookie_str)
listing = client.get_integrated_filings('RELIANCE', 'Reliance Industries Limited', size=50)
rows = listing['data']
print('Total filings:', len(rows))
for r in rows:
    print('  type=' + str(r.get('type')) + ' cons=' + str(r.get('consolidated')) + ' qe=' + str(r.get('qe_Date')) + ' audited=' + str(r.get('audited')))
