from nse_xbrl import NSEClient
import requests

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

# Get the first ANNUAL audited consolidated filing for HDFC BANK
listing = client.get_integrated_filings('HDFCBANK', 'HDFC Bank Limited', size=20)
annual_consolidated = None
for row in listing['data']:
    if row.get('consolidated') == 'Consolidated' and row.get('audited') == 'Audited':
        # Check date - we want recent
        annual_consolidated = row
        break

if annual_consolidated:
    xbrl_url = annual_consolidated.get('xbrl')
    xml = client.get_integrated_xbrl(xbrl_url)
    if xml:
        with open('hdfc_annual_xbrl.xml', 'w') as f:
            f.write(xml[:50000])
        
        # Parse with lxml to get all facts
        from lxml import etree
        root = etree.fromstring(xml.encode())
        
        by_context = {}
        for elem in root.iter():
            tag = elem.tag
            if not isinstance(tag, str):
                continue
            local = tag.split('}')[-1] if '}' in tag else tag
            ctx = elem.get('contextRef', '')
            text = (elem.text or '').strip()
            if ctx and text and local:
                by_context.setdefault(ctx, {})[local] = text
        
        for ctx in ['OneD', 'OneI', 'FourD', 'PY_I']:
            if ctx in by_context:
                print(f'\n=== Context: {ctx} ({len(by_context[ctx])} elements) ===')
                for k, v in sorted(by_context[ctx].items()):
                    print(f'  {k} = {v}')
