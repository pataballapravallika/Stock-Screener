from lxml import etree

filing_xml = r'D:\career-projects\data\raw_filings\TCS\2026-06-30\filing.xml'
with open(filing_xml, 'rb') as f:
    data = f.read()
parser = etree.XMLParser(recover=True, huge_tree=True)
root = etree.fromstring(data, parser)

for elem in root.iter():
    tag = elem.tag
    if not isinstance(tag, str) or '}' not in tag:
        continue
    local = tag.split('}')[-1]
    ctx = elem.get('contextRef', '')
    val = (elem.text or '').strip()
    if not ctx or not val or len(val) <= 1:
        continue
    if 'face' in local.lower() or 'share' in local.lower() or 'equity' in local.lower() or 'paidup' in local.lower():
        print(f'  {local}: ctx={ctx} val={val}')
