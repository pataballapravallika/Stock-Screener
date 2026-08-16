import re
from lxml import etree

with open(r'D:\career-projects\data\raw_filings\RELIANCE\2026-06-30\filing.xml', 'rb') as f:
    data = f.read()

parser = etree.XMLParser(recover=True, huge_tree=True)
root = etree.fromstring(data, parser)

# Find all unique tag names and their contexts
tags_seen = {}
for elem in root.iter():
    tag = elem.tag
    if not isinstance(tag, str) or '}' not in tag:
        continue
    local = tag.split('}')[-1]
    ctx = elem.get('contextRef', '')
    val = (elem.text or '').strip()
    if ctx and val and len(val) > 1 and not local.startswith('Description') and not local.startswith('Disclosure') and not local.startswith('Note') and not local.startswith('Nature') and not local.startswith('Whether') and not local.startswith('Declaration') and not local.startswith('Auditor') and not local.startswith('Validity') and not local.startswith('ClassOf') and not local.startswith('LevelOf') and not local.startswith('Reporting') and not local.startswith('IsCompany') and not local.startswith('DateOf') and not local.startswith('StartTime') and not local.startswith('EndTime') and not local.startswith('Symbol') and not local.startswith('MSEISymbol') and not local.startswith('TypeOf') and not local.startswith('NameOf') and not local.startswith('TypeOfReporting') and not local.startswith('DateOfStartOf') and not local.startswith('DateOfEnd') and not local.startswith('DateOnWhich') and not local.startswith('DateOfStartOfBoard') and not local.startswith('StartTimeOf') and not local.startswith('EndTimeOf') and not local.startswith('DeclarationOf') and not local.startswith('Is') and not local.startswith('TypeOf') and not local.startswith('Period'):
        if local not in tags_seen:
            tags_seen[local] = []
        tags_seen[local].append((ctx, val[:40]))

for tag_name in sorted(tags_seen.keys()):
    for ctx, val in tags_seen[tag_name]:
        print(f'{tag_name}: ctx={ctx} val={val}')
