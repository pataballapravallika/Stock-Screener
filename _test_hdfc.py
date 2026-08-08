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

# Check HDFC BANK - the ticker might be different
for symbol, issuer in [('HDFCBANK', 'HDFC Bank Limited'), ('HDFC', 'Housing Development Finance Corporation Limited')]:
    listing = client.get_integrated_filings(symbol, issuer, size=10)
    if listing and 'data' in listing:
        print(f'{symbol}: {len(listing["data"])} filings')
        for row in listing['data'][:5]:
            print(f'  consolidated={row.get("consolidated")}, audited={row.get("audited")}, xbrl={row.get("xbrl", "N/A")[:60]}')
    else:
        print(f'{symbol}: No listing found')
    print()

# Also check SBI with more results
symbol = 'SBIN'
issuer = 'State Bank of India'
listing = client.get_integrated_filings(symbol, issuer, size=20)
if listing and 'data' in listing:
    print(f'{symbol}: {len(listing["data"])} filings')
    for row in listing['data'][:10]:
        has_xbrl = bool(row.get("xbrl"))
        print(f'  consolidated={row.get("consolidated")}, audited={row.get("audited")}, has_xbrl={has_xbrl}')
print()

# Now try fetching 20 filings for HDFC BANK
listing = client.get_integrated_filings('HDFCBANK', 'HDFC Bank Limited', size=20)
if listing and 'data' in listing:
    print(f'HDFCBANK: {len(listing["data"])} filings')
    for row in listing['data'][:10]:
        has_xbrl = bool(row.get("xbrl"))
        print(f'  consolidated={row.get("consolidated")}, audited={row.get("audited")}, has_xbrl={has_xbrl}')
