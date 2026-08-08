import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nseindia.com/',
}
session = requests.Session()
session.headers.update(headers)
session.get('https://www.nseindia.com/', timeout=15)

url = 'https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE&subCategory=financial-results'
resp = session.get(url, timeout=15)
data = resp.json()

item = None
for i in data:
    text = i.get('attchmntText', '').lower()
    if i.get('hasXbrl') == True and 'financial results' in text and 'transcript' not in text and 'audio' not in text and 'media' not in text and 'investor' not in text and 'presentation' not in text and 'analyst' not in text and 'postal' not in text and 'board' not in text and 'clipping' not in text:
        item = i
        print('Text:', i.get('attchmntText', '')[:200])
        print('PDF URL:', i.get('attchmntFile', ''))
        print('DT:', i.get('dt', ''))
        print('Seq ID:', i.get('seq_id', ''))
        print('Has XBRL:', i.get('hasXbrl'))
        print('All keys:', list(i.keys()))
        print('All values:')
        for k, v in i.items():
            print(f'  {k}: {v}')
        break

if item:
    dt = item.get('dt', '')
    sym = item.get('symbol', '')
    pdf_url = item.get('attchmntFile', '')
    pdf_name = pdf_url.split('/')[-1]

    xbrl_urls = [
        f'https://nsearchives.nseindia.com/corporate/XBRL/{sym}_{dt}.xml',
        f'https://nsearchives.nseindia.com/corporate/{pdf_name.replace(".pdf", ".xml")}',
        f'https://nsearchives.nseindia.com/corporate/XBRL/{pdf_name.replace(".pdf", ".xml")}',
        f'https://nsearchives.nseindia.com/corporate/XBRL/{pdf_name.replace(".pdf", "")}.xml',
    ]
    print('\nAttempting XBRL URL patterns:')
    for path in xbrl_urls:
        r = session.get(path, timeout=10)
        print(f'  Status: {r.status_code} URL: {path[:100]}')
        if r.status_code == 200:
            print(f'  Content length: {len(r.text)}')
            print(f'  First 300 chars: {r.text[:300]}')
