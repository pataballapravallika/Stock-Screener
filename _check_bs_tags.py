import re
from lxml import etree
import os

filing_xml = r'D:\career-projects\data\raw_filings\SBIN\2026-06-30\filing.xml'
with open(filing_xml, 'rb') as f:
    data = f.read()
parser = etree.XMLParser(recover=True, huge_tree=True)
root = etree.fromstring(data, parser)

# Find ALL unique contextRefs
ctxs = set()
for elem in root.iter():
    tag = elem.tag
    if not isinstance(tag, str) or '}' not in tag:
        continue
    local = tag.split('}')[-1]
    ctx = elem.get('contextRef', '')
    if ctx:
        ctxs.add(ctx)
print('All contextRefs:', sorted(ctxs))

# Find all unique tag names
all_tags = set()
for elem in root.iter():
    tag = elem.tag
    if not isinstance(tag, str) or '}' not in tag:
        continue
    local = tag.split('}')[-1]
    all_tags.add(local)

# Search for specific financial tags
keywords = ['Cash', 'Deposit', 'Advance', 'NPA', 'Provisioning', 'CAR', 'Capital',
            'Reserve', 'Equity', 'Liabilit', 'Assets', 'Debt', 'Borrowing', 'Loan',
            'Expenditure', 'Investment', 'Operating', 'Finance', 'Revenue', 'Profit',
            'Tax', 'Earnings', 'Dividend']
print('\nAll financial tags:')
for tag_name in sorted(all_tags):
    tag_lower = tag_name.lower()
    if any(kw.lower() in tag_lower for kw in keywords):
        val = ''
        ctx = ''
        for elem in root.iter():
            t = elem.tag
            if not isinstance(t, str) or '}' not in t:
                continue
            if t.split('}')[-1] == tag_name and elem.text:
                ctx = elem.get('contextRef', '')
                val = elem.text.strip()[:50]
                if ctx and val:
                    print(f'  {tag_name}: ctx={ctx} val={val}')
                    break
