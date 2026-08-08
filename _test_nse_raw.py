import requests, json
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nseindia.com/',
}
session = requests.Session()
session.headers.update(headers)
resp = session.get('https://www.nseindia.com/', timeout=15)
print('Homepage cookies:', len(session.cookies))

# Try the quote-equity endpoint
resp2 = session.get('https://www.nseindia.com/api/quote-equity', params={'symbol': 'RELIANCE'}, timeout=25)
print('quote-equity status:', resp2.status_code)
print('Body:', resp2.text[:200])

# Try without params - use the full URL format
resp3 = session.get('https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE', timeout=25)
print()
print('get-quotes/equity status:', resp3.status_code)

# Try the equity-info endpoint
resp4 = session.get('https://www.nseindia.com/api/equity-info?symbol=RELIANCE', timeout=25)
print('equity-info status:', resp4.status_code)
