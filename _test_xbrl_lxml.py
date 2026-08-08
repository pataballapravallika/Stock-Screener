import requests, re
from collections import defaultdict
from lxml import etree

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Referer': 'https://www.nseindia.com/',
}
session = requests.Session()
session.headers.update(headers)
session.get('https://www.nseindia.com/', timeout=15)

xbrl_url = 'https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1695741_17072026075004_WEB.xml'
resp = session.get(xbrl_url, timeout=60)

root = etree.fromstring(resp.content)

# Collect all elements with contextRef
by_context = defaultdict(dict)
for elem in root.iter():
    tag = elem.tag
    if not isinstance(tag, str):
        continue
    local_name = tag.split('}')[-1] if '}' in tag else tag
    ctx = elem.get('contextRef', '')
    text = (elem.text or '').strip()
    if ctx and text and local_name:
        by_context[ctx][local_name] = text

for ctx in ['OneD', 'FourD', 'OneI', 'PY_I']:
    print(f"\n=== Context: {ctx} ({len(by_context.get(ctx, {}))} elements) ===")
    for k, v in sorted(by_context.get(ctx, {}).items()):
        print(f"  {k} = {v}")
