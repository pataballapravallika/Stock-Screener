import os, re
from lxml import etree

paths = [
    r'D:\career-projects\data\raw_filings\RELIANCE\2026-06-30\filing.xml',
    r'D:\career-projects\data\raw_filings\TCS\2026-06-30\filing.xml',
    r'D:\career-projects\data\raw_filings\HDFCBANK\2026-06-30\filing.xml',
]

for path in paths:
    print(f"\n=== {os.path.basename(path)} ({os.path.getsize(path)//1024}KB) ===")
    tree = etree.parse(path)
    root = tree.getroot()
    # Collect all elements with text
    elements = {}
    for elem in root.iter():
        if elem.text and elem.text.strip():
            ns_match = re.match(r'\{([^}]+)\}([^}]+)', elem.tag)
            if ns_match:
                ns_uri = ns_match.group(1)
                local = ns_match.group(2)
            else:
                local = elem.tag
            ctx_ref = elem.get('{http://www.w3.org/1999/xlink}href') or elem.get('contextRef')
            val = elem.text.strip()
            if val and any(c.isdigit() for c in val):
                key = local.lower()
                if key not in elements:
                    elements[key] = []
                elements[key].append((ctx_ref, val[:40]))

    keywords = ['revenue', 'profit', 'income', 'asset', 'liab', 'equity', 'borrowing', 'debt',
                'cash', 'deposit', 'advance', 'npa', 'provision', 'expenditure', 'capital',
                'ebit', 'earning', 'share', 'face', 'tax', 'operating', 'interest']
    for k in sorted(elements.keys()):
        if any(kw in k for kw in keywords):
            ctxs = [e[0] for e in elements[k] if e[0]]
            vals = [e[1] for e in elements[k]]
            print(f"  {k:55s} ctx={ctxs[:3]}  val={vals[:3]}")
