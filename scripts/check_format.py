import re

files = [
    r'D:\career-projects\Stock_Screener\pages\3_Quality_Analysis.py',
    r'D:\career-projects\Stock_Screener\pages\5_Technical_Analysis.py',
]

for f in files:
    with open(f, 'r') as fh:
        content = fh.read()
    applies = re.findall(r'\.apply\(lambda v: f["\'].*?["\']\)', content)
    print(f'{f}: {len(applies)} apply(lambda patterns)')
    for a in applies:
        print(f'  {a[:100]}')