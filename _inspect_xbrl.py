import re, os

path = r'D:\career-projects\data\raw_filings\RELIANCE\2026-06-30\filing.xml'
with open(path, 'r', errors='replace') as f:
    content = f.read()

# Get ALL elements with text content
all_tags = re.findall(r'<(\w+):(\w+)\s+([^>]*?)>([^<]+)</\1:(\w+)>', content)

seen = {}
for ns, tag, attrs, val, _ in all_tags:
    val_strip = val.strip()
    if not val_strip:
        continue
    ctx = re.search(r'contextRef="([^"]+)"', attrs)
    ctx_val = ctx.group(1) if ctx else "NOCTX"
    key = (tag.lower(), ctx_val)
    if key not in seen:
        seen[key] = val_strip

for (tag, ctx), val in sorted(seen.items(), key=lambda x: x[0]):
    print(f"{tag:60s} ctx={ctx:20s} val={val[:30]}")
