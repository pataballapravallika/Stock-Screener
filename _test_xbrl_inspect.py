import requests, re

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

text = resp.text
contexts = re.findall(r'<xbrli:context id="([^"]+)"', text)
print('All contexts:', contexts)

# Find all tags with contextRef
pattern = r'<([^\s>]+)\s+[^>]*contextRef="([^"]+)"[^>]*>([^<]*)<'
import re as _re
matches = _re.findall(pattern, text)
print(f"\nTotal tagged elements: {len(matches)}")

# Group by context
from collections import defaultdict
by_context = defaultdict(list)
for tag, ctx, val in matches:
    by_context[ctx].append((tag, val))

for ctx in sorted(by_context.keys()):
    print(f"\n  Context [{ctx}]: {len(by_context[ctx])} elements")
    for tag, val in by_context[ctx][:15]:
        print(f"    {tag} = {val}")
